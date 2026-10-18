"""Data shapes and rules for debates that a visitor starts from their own question.

Everything the model writes is parsed into these shapes before it is stored or shown, so a malformed or
over-long answer is repaired (trimmed) or rejected here, never passed to the browser as-is."""
import re  # regular expressions (pattern matching on text)
import unicodedata  # Unicode normalisation (so "é" typed two different ways is stored one way)
from typing import Literal  # a type that allows only a fixed set of values

from pydantic import BaseModel, field_validator  # BaseModel validates data; field_validator adds our own rules

# The five analysts, in the order they are shown.
PERSONAS = ("left", "right", "economist", "geopolitical", "devil")
# The four that write independently; the devil's advocate then reads their positions and challenges them.
PARALLEL = ("left", "right", "economist", "geopolitical")
# Friendly names for the five analysts.
PERSONA_LABELS = {
    "left": "Left Analyst",
    "right": "Right Analyst",
    "economist": "Economist",
    "geopolitical": "Geopolitical Analyst",
    "devil": "Devil's Advocate",
}
# The optional topic categories a visitor may pick (stored as typed here).
CATEGORIES = (
    "Politics & policy",
    "Technology & AI",
    "Economy & work",
    "Science & health",
    "Society & culture",
    "World affairs",
    "Other",
)

# What a single perspective can be doing.
PERSPECTIVE_STATES = ("pending", "generating", "completed", "failed")
# The criteria the moderator must assess, in this order (the model's own names are matched to these).
CRITERIA = (
    "Evidence quality",
    "Logical consistency",
    "Relevance to the question",
    "Treatment of counterarguments",
    "Transparency about uncertainty",
)

# Limits that keep stored and displayed text a sensible size.
MAX_SHORT = 400
MAX_LONG = 900
MAX_CLAIMS = 6
MAX_LIST_ITEMS = 5

# Control characters (except normal whitespace, which is handled separately) are removed from questions.
_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


# Cleans and checks a visitor's question. Raises ValueError with a message that is safe to show the visitor.
def normalize_question(raw: str, min_chars: int, max_chars: int) -> str:
    """Trim, collapse whitespace and validate. The wording is otherwise left exactly as written."""
    # Make equivalent Unicode spellings identical, and replace control characters with spaces.
    text = _CONTROL.sub(" ", unicodedata.normalize("NFC", raw))
    # "".split() with no argument splits on any run of whitespace, so this trims and collapses it (newlines too).
    text = " ".join(text.split())
    # Nothing left: the visitor submitted an empty or whitespace-only text.
    if not text:
        raise ValueError("Enter a question or topic to debate.")
    # Too short to be a meaningful topic.
    if len(text) < min_chars:
        raise ValueError(f"Make it at least {min_chars} characters so the analysts have something to debate.")
    # Too long for the prompts.
    if len(text) > max_chars:
        raise ValueError(f"Keep it under {max_chars} characters (yours is {len(text)}).")
    # At least two real words (letters or digits in any language).
    if len(re.findall(r"[^\W_]+", text)) < 2:
        raise ValueError("Write a full question or statement (at least two words).")
    # Mostly symbols is not a topic ("?????????", "!!!! ....").
    if sum(ch.isalnum() for ch in text) / len(text) < 0.5:
        raise ValueError("That does not look like a question or topic. Use words rather than symbols.")
    return text


# Trims text and cuts it to a length limit, adding "…" when it was cut.
def clip(value: object, limit: int) -> str:
    # Anything that is not text becomes an empty string.
    text = " ".join(value.split()) if isinstance(value, str) else ""
    # Over the limit: cut at the limit and mark the cut.
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


# One claim exactly as the model wrote it.
class ClaimOut(BaseModel):
    # The claim itself, one or two sentences.
    text: str
    # What kind of statement it is, as judged by the model (the app never upgrades "factual" to "verified").
    type: Literal["factual", "opinion", "assumption"] = "factual"
    # Ids of the provided sources the claim relies on, like ["S1"]. Unknown ids are dropped later.
    source_ids: list[str] = []

    @field_validator("text", mode="before")
    @classmethod
    def _text(cls, value: object) -> str:
        # Trim and cut; an empty claim is rejected below.
        text = clip(value, MAX_SHORT)
        if not text:
            raise ValueError("claim text is empty")
        return text

    @field_validator("type", mode="before")
    @classmethod
    def _type(cls, value: object) -> str:
        # Unknown labels become "factual" (the cautious default: it is then shown as unverified).
        label = value.strip().lower() if isinstance(value, str) else ""
        return label if label in ("factual", "opinion", "assumption") else "factual"

    @field_validator("source_ids", mode="before")
    @classmethod
    def _ids(cls, value: object) -> list[str]:
        # Keep short strings only, at most five, without repeats.
        if not isinstance(value, list):
            return []
        seen: list[str] = []
        for item in value:
            if isinstance(item, str) and 1 <= len(item.strip()) <= 12 and item.strip() not in seen:
                seen.append(item.strip())
        return seen[:5]


# One perspective exactly as the model wrote it (before sources are checked and claims get ids).
class PerspectiveOut(BaseModel):
    position_summary: str
    strongest_argument: str
    claims: list[ClaimOut] = []
    counterargument: str = ""
    assumptions: list[str] = []
    uncertainties: list[str] = []

    @field_validator("position_summary", mode="before")
    @classmethod
    def _summary(cls, value: object) -> str:
        text = clip(value, MAX_SHORT)
        if not text:
            raise ValueError("position_summary is empty")
        return text

    @field_validator("strongest_argument", mode="before")
    @classmethod
    def _argument(cls, value: object) -> str:
        text = clip(value, MAX_LONG)
        if not text:
            raise ValueError("strongest_argument is empty")
        return text

    @field_validator("counterargument", mode="before")
    @classmethod
    def _counter(cls, value: object) -> str:
        return clip(value, MAX_LONG)

    @field_validator("claims", mode="before")
    @classmethod
    def _claims(cls, value: object) -> list:
        # Take at most six; items that are not objects are ignored rather than failing the whole answer.
        if not isinstance(value, list):
            return []
        return [item for item in value if isinstance(item, dict)][:MAX_CLAIMS]

    @field_validator("assumptions", "uncertainties", mode="before")
    @classmethod
    def _strings(cls, value: object) -> list[str]:
        if not isinstance(value, list):
            return []
        cleaned = [clip(item, MAX_SHORT) for item in value]
        return [item for item in cleaned if item][:MAX_LIST_ITEMS]


# Turns the model's perspective into the record that is stored and shown: claims get ids and a status that
# is computed here, never taken from the model.
def build_content(persona: str, out: PerspectiveOut, valid_source_ids: set[str]) -> dict:
    """Returns the stored shape. Source ids the model made up are dropped; a claim never becomes 'verified'."""
    claims = []
    for index, claim in enumerate(out.claims, start=1):
        # Keep only citations that point at a source we really retrieved.
        ids = [sid for sid in claim.source_ids if sid in valid_source_ids]
        # Opinions and assumptions are labelled as such; a factual claim is "unverified" because no fact-checking
        # step exists (having a source means "cited", which is shown separately, not "verified").
        status = claim.type if claim.type in ("opinion", "assumption") else "unverified"
        claims.append({
            "id": f"{persona}-{index}",
            "text": claim.text,
            "type": claim.type,
            "status": status,
            "source_ids": ids,
        })
    return {
        "position_summary": out.position_summary,
        "strongest_argument": out.strongest_argument,
        "claims": claims,
        "counterargument": out.counterargument,
        "assumptions": out.assumptions,
        "uncertainties": out.uncertainties,
    }

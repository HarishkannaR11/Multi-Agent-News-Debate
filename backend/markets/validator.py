"""The validator: checks an agent's (or the moderator's) answer against the frozen packet, in code.

An answer passes only if every claim cites real facts and every figure it quotes appears in a cited fact. When it fails,
the reasons are returned so the pipeline can send the answer back to the agent (the retry edge). The model proposes;
this code decides."""
import re  # finds figures in text
from dataclasses import asdict, dataclass  # small record type for rejections
from typing import Literal

from pydantic import BaseModel, Field, ValidationError, field_validator  # strict shapes for the model's JSON

MIN_CLAIMS = 2
MAX_CLAIMS = 6
ATTRIBUTION_LABELS = ("domestic", "imported", "mixed", "unclear", "no_significant_move")
FIGURE_ABS_TOLERANCE = 0.051  # a figure may differ from the fact by up to half a unit in the first decimal
FIGURE_REL_TOLERANCE = 0.005  # ...or by half a percent of its value (index levels are quoted rounded)

# A number in text: optional sign, digits with thousands commas, optional decimals, optional percent sign.
NUMBER_RE = re.compile(r"(?<![\w.])([-+−]?\d[\d,]*(?:\.\d+)?)(\s*%|\s*bps|\s*crore|\s*sigma|\s*pp)?", re.IGNORECASE)
DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
# Unconditional predictions of a level ("will reach 25,000", "is going to hit 84") are not allowed.
PREDICTION_RE = re.compile(
    r"\b(?:will|going to|expected to|set to|likely to)\s+(?:\w+\s+){0,2}?(?:reach|hit|touch|rise to|fall to|drop to|"
    r"climb to|surge to|test)\b|\bprice target\b|\bforecast(?:s|ed)?\b",
    re.IGNORECASE,
)


@dataclass
class Rejection:
    code: str
    message: str
    claim: int | None = None  # 1-based claim number, or None for the answer as a whole

    def to_dict(self) -> dict:
        return asdict(self)


class ClaimIn(BaseModel):
    text: str = Field(min_length=1, max_length=400)
    kind: Literal["observation", "inference"] = "observation"
    fact_ids: list[str] = Field(default_factory=list, max_length=6)

    @field_validator("text")
    @classmethod
    def _trim(cls, value: str) -> str:
        return " ".join(value.split())


class AgentIn(BaseModel):
    stance: str = Field(min_length=1, max_length=300)
    thesis: str = Field(min_length=1, max_length=600)
    claims: list[ClaimIn] = Field(max_length=12)
    caveats: list[str] = Field(default_factory=list, max_length=6)
    attribution: str | None = None
    attribution_reasoning: str | None = Field(default=None, max_length=600)


class DriverIn(BaseModel):
    text: str = Field(min_length=1, max_length=400)
    fact_ids: list[str] = Field(default_factory=list, max_length=6)


class VerdictIn(BaseModel):
    summary: str = Field(min_length=1, max_length=700)
    attribution_view: str = Field(min_length=1, max_length=500)
    key_drivers: list[DriverIn] = Field(max_length=8)
    bull_strongest: str = Field(min_length=1, max_length=400)
    bear_strongest: str = Field(min_length=1, max_length=400)
    what_would_change: list[str] = Field(default_factory=list, max_length=6)
    data_gaps: list[str] = Field(default_factory=list, max_length=6)
    conclusion: str = Field(min_length=1, max_length=600)


# The figures in a text that need support from a fact, as (display text, value). Dates and fact ids are ignored, and
# small plain integers ("5-day", "two") are treated as wording rather than figures.
def figures(text: str) -> list[tuple[str, float]]:
    cleaned = DATE_RE.sub(" ", text)
    found: list[tuple[str, float]] = []
    for match in NUMBER_RE.finditer(cleaned):
        raw, unit = match.group(1), (match.group(2) or "").strip()
        value = float(raw.replace(",", "").replace("−", "-"))
        plain_small_int = "." not in raw and not unit and abs(value) < 100
        if plain_small_int:
            continue
        found.append((raw + (unit if unit == "%" else (" " + unit if unit else "")), value))
    return found


# Does a quoted figure match any of the numbers in the cited facts (sign ignored, rounding tolerated)?
def _supported(value: float, numbers: list[float]) -> bool:
    target = abs(value)
    return any(abs(target - abs(n)) <= max(FIGURE_ABS_TOLERANCE, FIGURE_REL_TOLERANCE * abs(n)) for n in numbers)


# Checks one text: its figures must be supported by `numbers`. Returns a message for the first unsupported figure.
def _check_figures(text: str, numbers: list[float], where: str) -> str | None:
    for shown, value in figures(text):
        if not _supported(value, numbers):
            nearest = min(numbers, key=lambda n: abs(abs(n) - abs(value))) if numbers else None
            hint = f" The closest figure in the cited facts is {nearest:g}." if nearest is not None else (
                " The cited facts contain no figures to quote."
            )
            return f"{where}: the figure {shown.strip()} does not appear in the facts it cites.{hint}"
    return None


def _prediction(text: str, where: str) -> str | None:
    if PREDICTION_RE.search(text):
        return f"{where}: specific predictions are not allowed; rewrite it as a conditional scenario (if ... then ...)."
    return None


# Validates an analyst's answer. Returns (clean answer dict or None, rejections).
def validate_agent(data: dict, role: str, facts: dict[str, dict], attribution: dict) -> tuple[dict | None, list[dict]]:
    try:
        answer = AgentIn.model_validate(data)
    except ValidationError as exc:
        first = exc.errors()[0]
        where = ".".join(str(p) for p in first["loc"]) or "answer"
        return None, [Rejection("BAD_SHAPE", f"The JSON did not match the required shape at '{where}': {first['msg']}.")
                      .to_dict()]
    rejections: list[Rejection] = []
    if not MIN_CLAIMS <= len(answer.claims) <= MAX_CLAIMS:
        rejections.append(Rejection("CLAIM_COUNT", f"Give between {MIN_CLAIMS} and {MAX_CLAIMS} claims, not "
                                                  f"{len(answer.claims)}."))
    for number, claim in enumerate(answer.claims, start=1):
        where = f"Claim {number}"
        if not claim.fact_ids:
            rejections.append(Rejection("NO_CITATION", f"{where} cites no fact. Every claim needs a fact id.", number))
            continue
        unknown = [f for f in claim.fact_ids if f not in facts]
        if unknown:
            rejections.append(Rejection("UNKNOWN_FACT", f"{where} cites {', '.join(unknown)}, which "
                                                         "does not exist in the packet.", number))
            continue
        numbers = [n for f in claim.fact_ids for n in facts[f]["numbers"]]
        problem = _check_figures(claim.text, numbers, where)
        if problem:
            rejections.append(Rejection("FIGURE_MISMATCH", problem, number))
        problem = _prediction(claim.text, where)
        if problem:
            rejections.append(Rejection("PREDICTION", problem, number))
    all_numbers = [n for f in facts.values() for n in f["numbers"]]
    for label, text in (("The stance", answer.stance), ("The thesis", answer.thesis)):
        problem = _check_figures(text, all_numbers, label) or _prediction(text, label)
        if problem:
            rejections.append(Rejection("FIGURE_MISMATCH", problem))

    if role == "skeptic":
        rejections += _check_skeptic(answer, facts, attribution)
    if rejections:
        return None, [r.to_dict() for r in rejections]
    clean = answer.model_dump()
    clean["claims"] = [{"id": f"{role}-{i}", **c} for i, c in enumerate(clean["claims"], start=1)]
    if role != "skeptic":
        clean.pop("attribution", None)
        clean.pop("attribution_reasoning", None)
    return clean, []


# The skeptic must name an attribution, cite the attribution fact, and not flatly contradict a computed reading.
def _check_skeptic(answer: AgentIn, facts: dict[str, dict], attribution: dict) -> list[Rejection]:
    out: list[Rejection] = []
    if answer.attribution not in ATTRIBUTION_LABELS:
        out.append(Rejection("MISSING_ATTRIBUTION", f"Set 'attribution' to one of: {', '.join(ATTRIBUTION_LABELS)}."))
        return out
    if not answer.attribution_reasoning:
        out.append(Rejection("MISSING_ATTRIBUTION", "Add 'attribution_reasoning' explaining your attribution."))
    attribution_ids = {fid for fid, f in facts.items() if f["series"] == "ATTRIBUTION"}
    if attribution_ids and not any(set(c.fact_ids) & attribution_ids for c in answer.claims):
        cited = ", ".join(sorted(attribution_ids))
        out.append(Rejection("NO_ATTRIBUTION_CITATION", f"Cite the attribution fact ({cited}) in at least one claim."))
    computed = attribution.get("label") if attribution.get("status") == "ok" else None
    if computed in ("imported", "domestic") and answer.attribution in ("imported", "domestic") \
            and answer.attribution != computed:
        out.append(Rejection(
            "ATTRIBUTION_CONTRADICTS",
            f"The computed attribution reads '{computed}' (imported factors {attribution['explained_pct']:+.2f} pp, "
            f"unexplained {attribution['residual_pct']:+.2f} pp) but you said '{answer.attribution}'. If you disagree, "
            "answer 'mixed' or 'unclear' and explain with cited facts why the computation may mislead.",
        ))
    return out


# Validates the moderator's verdict. Figures may match any fact; drivers must cite real facts.
# Returns (verdict or None, rejections).
def validate_verdict(
    data: dict, facts: dict[str, dict], missing: list[dict], attribution: dict
) -> tuple[dict | None, list[dict]]:
    try:
        verdict = VerdictIn.model_validate(data)
    except ValidationError as exc:
        first = exc.errors()[0]
        where = ".".join(str(p) for p in first["loc"]) or "answer"
        return None, [Rejection("BAD_SHAPE", f"The JSON did not match the required shape at '{where}': {first['msg']}.")
                      .to_dict()]
    rejections: list[Rejection] = []
    if not 1 <= len(verdict.key_drivers) <= 5:
        rejections.append(Rejection("CLAIM_COUNT", "Give between 1 and 5 key_drivers."))
    all_numbers = [n for f in facts.values() for n in f["numbers"]]
    for number, driver in enumerate(verdict.key_drivers, start=1):
        where = f"Driver {number}"
        if not driver.fact_ids or any(f not in facts for f in driver.fact_ids):
            rejections.append(Rejection("UNKNOWN_FACT", f"{where} must cite existing fact ids.", number))
            continue
        numbers = [n for f in driver.fact_ids for n in facts[f]["numbers"]]
        problem = _check_figures(driver.text, numbers, where) or _prediction(driver.text, where)
        if problem:
            rejections.append(Rejection("FIGURE_MISMATCH", problem, number))
    texts = {
        "The summary": verdict.summary, "The attribution view": verdict.attribution_view,
        "The conclusion": verdict.conclusion, "The bull point": verdict.bull_strongest,
        "The bear point": verdict.bear_strongest,
    }
    for where, text in texts.items():
        problem = _check_figures(text, all_numbers, where) or _prediction(text, where)
        if problem:
            rejections.append(Rejection("FIGURE_MISMATCH", problem))
    if rejections:
        return None, [r.to_dict() for r in rejections]
    clean = verdict.model_dump()
    # Confidence is decided here, never by the model: thin data or a weak attribution fit caps it at "low".
    weak = bool(missing) or attribution.get("status") != "ok" or attribution.get("confidence") == "low"
    clean["confidence"] = "low" if weak else "moderate"
    clean["limitations"] = [
        "AI-written commentary on a statistical snapshot; it is not investment advice.",
        "The attribution is a statistical association over about 60 days, not proof of cause.",
    ] + ([f"Data missing or stale: {', '.join(m['series'] for m in missing)}."] if missing else [])
    return clean, []

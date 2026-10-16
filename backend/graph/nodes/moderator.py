import json  # parses JSON text into Python objects
import logging  # Python's built-in logging system
import re  # regular expressions (pattern matching on text)

from ...config import PERSONA_KEYS, llm, settings  # analyst names, the shared LLM wrapper, app settings
from ..guarded import generate_guarded  # "ask the LLM, then content-check the answer, retry if blocked"
from ..state import DebateState  # the shared state shape

# A logger named after this module.
logger = logging.getLogger(__name__)

# Instructions for the moderator: read the whole debate and write a balanced verdict.
MODERATOR_SYSTEM = """You are a neutral debate moderator. You have read opening
arguments and rebuttals from five analysts with different perspectives
(progressive, conservative, macroeconomist, geopolitical, devil's advocate).
Synthesize a balanced verdict that acknowledges the strongest points from each
side without declaring one side categorically right. Max 250 words."""

# Instructions for the bias auditor: score each analyst's slant from 0 to 1 and answer with JSON only.
BIAS_SYSTEM = """You are a bias auditor. Given a debate transcript, score how
ideologically slanted each analyst's combined argument and rebuttal is on a
0-1 scale (0 = perfectly neutral/fact-based, 1 = maximally one-sided).
Respond with ONLY a JSON object mapping persona key to a float, e.g.
{"left": 0.7, "right": 0.65, "economist": 0.2, "geopolitical": 0.3, "devil": 0.4}"""

# How many times to try getting parseable bias scores.
BIAS_ATTEMPTS = 2
# Text shown instead of the verdict if every attempt was blocked by the content filter.
VERDICT_FALLBACK = (
    "The moderator's verdict could not be published because it did not pass the content checks. "
    "Read the five arguments and rebuttals above and weigh them for yourself."
)


# Turns the debate into one text transcript for the moderator to read.
def _transcript(state: DebateState) -> str:
    # Collect the lines of the transcript here.
    parts = []
    # Go through each analyst that wrote an opening argument.
    for key, argument in state["arguments"].items():
        # Add their opening.
        parts.append(f"[{key}] Opening: {argument}")
        # Look up their rebuttal, if one was accepted.
        rebuttal = state.get("rebuttals", {}).get(key)
        # Add it only if it exists.
        if rebuttal:
            parts.append(f"[{key}] Rebuttal: {rebuttal}")
    # Join everything with blank lines between entries.
    return "\n\n".join(parts)


# Safely extracts {analyst: score} from the model's reply (never trust model output as clean data).
def parse_bias_scores(raw: str) -> dict[str, float]:
    """Extract {persona: 0..1} from model output; unknown keys and non-numeric values are dropped."""
    # Find the first "{ ... }" block in the reply (the model may add extra words around it).
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    # No JSON-looking block: give up with an empty result.
    if not match:
        return {}
    try:
        # Parse that block as JSON.
        data = json.loads(match.group(0))
    # Invalid JSON: give up with an empty result.
    except json.JSONDecodeError:
        return {}
    # It must be a JSON object (a dict), not a list or number.
    if not isinstance(data, dict):
        return {}
    # The cleaned scores will be collected here.
    scores: dict[str, float] = {}
    # Look only at the five known analyst names (this ignores anything unexpected).
    for key in PERSONA_KEYS:
        # The model's value for this analyst.
        value = data.get(key)
        # Skip non-numbers; booleans are rejected explicitly because True counts as the number 1 in Python.
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        # Force the value into the range 0.0 to 1.0.
        scores[key] = min(1.0, max(0.0, float(value)))
    # Return the cleaned scores.
    return scores


# Graph step: writes the final verdict and the bias scores.
def moderator_node(state: DebateState) -> dict:
    # If no analyst argument survived the content filter, there is nothing to judge: stop with an error.
    if not state.get("arguments"):
        raise RuntimeError("No analyst argument passed the output guardrail; nothing to moderate")
    # Build the transcript the moderator will read.
    transcript = _transcript(state)

    # The message sent to the model: topic, transcript and the request.
    verdict_prompt = f"Topic: {state['topic']}\n\nFull debate transcript:\n{transcript}\n\nWrite the verdict now."
    # Ask the model and content-check the answer, retrying if it is blocked.
    verdict = generate_guarded(
        MODERATOR_SYSTEM, verdict_prompt, max_tokens=500, retries=settings.MAX_REBUTTAL_RETRIES, label="verdict"
    )
    # None means every attempt was blocked.
    if verdict is None:
        logger.warning("Verdict never passed the output guardrail; publishing the fallback text")
        # Use the fixed fallback text instead.
        verdict = VERDICT_FALLBACK

    # The message sent to the bias auditor: just the transcript.
    bias_prompt = f"Debate transcript:\n{transcript}"
    # Start with an empty result.
    scores: dict[str, float] = {}
    # Try a limited number of times to get scores we can parse.
    for _ in range(BIAS_ATTEMPTS):
        # Ask the small, fast model and parse its reply.
        scores = parse_bias_scores(llm.invoke(system=BIAS_SYSTEM, user=bias_prompt, max_tokens=200, fast=True))
        # Got usable scores: stop trying.
        if scores:
            break
    # This "else" runs only if the loop finished without hitting "break" (all attempts failed).
    else:
        logger.warning("Bias scores could not be parsed after %d attempts", BIAS_ATTEMPTS)

    # Save the verdict and scores, and mark the debate as finished.
    return {"verdict": verdict, "bias_scores": scores, "status": "done"}

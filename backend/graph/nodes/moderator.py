import json
import logging
import re

from ...config import PERSONA_KEYS, llm
from ..state import DebateState

logger = logging.getLogger(__name__)

MODERATOR_SYSTEM = """You are a neutral debate moderator. You have read opening
arguments and rebuttals from five analysts with different perspectives
(progressive, conservative, macroeconomist, geopolitical, devil's advocate).
Synthesize a balanced verdict that acknowledges the strongest points from each
side without declaring one side categorically right. Max 250 words."""

BIAS_SYSTEM = """You are a bias auditor. Given a debate transcript, score how
ideologically slanted each analyst's combined argument and rebuttal is on a
0-1 scale (0 = perfectly neutral/fact-based, 1 = maximally one-sided).
Respond with ONLY a JSON object mapping persona key to a float, e.g.
{"left": 0.7, "right": 0.65, "economist": 0.2, "geopolitical": 0.3, "devil": 0.4}"""

BIAS_ATTEMPTS = 2


def _transcript(state: DebateState) -> str:
    parts = []
    for key, argument in state["arguments"].items():
        parts.append(f"[{key}] Opening: {argument}")
        rebuttal = state.get("rebuttals", {}).get(key)
        if rebuttal:
            parts.append(f"[{key}] Rebuttal: {rebuttal}")
    return "\n\n".join(parts)


def parse_bias_scores(raw: str) -> dict[str, float]:
    """Extract {persona: 0..1} from model output; unknown keys and non-numeric values are dropped."""
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        return {}
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return {}
    if not isinstance(data, dict):
        return {}
    scores: dict[str, float] = {}
    for key in PERSONA_KEYS:
        value = data.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        scores[key] = min(1.0, max(0.0, float(value)))
    return scores


def moderator_node(state: DebateState) -> dict:
    transcript = _transcript(state)

    verdict_prompt = f"Topic: {state['topic']}\n\nFull debate transcript:\n{transcript}\n\nWrite the verdict now."
    verdict = llm.invoke(system=MODERATOR_SYSTEM, user=verdict_prompt, max_tokens=500)

    bias_prompt = f"Debate transcript:\n{transcript}"
    scores: dict[str, float] = {}
    for _ in range(BIAS_ATTEMPTS):
        scores = parse_bias_scores(llm.invoke(system=BIAS_SYSTEM, user=bias_prompt, max_tokens=200, fast=True))
        if scores:
            break
    else:
        logger.warning("Bias scores could not be parsed after %d attempts", BIAS_ATTEMPTS)

    return {"verdict": verdict, "bias_scores": scores, "status": "done"}

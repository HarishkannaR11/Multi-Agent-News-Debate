import json
import re

from ..state import DebateState
from ...config import llm

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


def _transcript(state: DebateState) -> str:
    parts = []
    for key, argument in state["arguments"].items():
        parts.append(f"[{key}] Opening: {argument}")
        rebuttal = state.get("rebuttals", {}).get(key)
        if rebuttal:
            parts.append(f"[{key}] Rebuttal: {rebuttal}")
    return "\n\n".join(parts)


def moderator_node(state: DebateState) -> DebateState:
    transcript = _transcript(state)

    verdict_prompt = f"Topic: {state['topic']}\n\nFull debate transcript:\n{transcript}\n\nWrite the verdict now."
    state["verdict"] = llm.invoke(system=MODERATOR_SYSTEM, user=verdict_prompt, max_tokens=500)

    bias_prompt = f"Debate transcript:\n{transcript}"
    raw_scores = llm.invoke(system=BIAS_SYSTEM, user=bias_prompt, max_tokens=200)
    match = re.search(r"\{.*\}", raw_scores, re.DOTALL)
    try:
        state["bias_scores"] = json.loads(match.group(0)) if match else {}
    except (json.JSONDecodeError, AttributeError):
        state["bias_scores"] = {}

    state["status"] = "done"
    return state

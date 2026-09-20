from ..guardrails.output_guard import output_guard
from ..state import DebateState
from ...config import llm
from .agents import PERSONAS

MAX_REBUTTAL_RETRIES = 2


def rebuttal_node(state: DebateState) -> DebateState:
    state["round"] = 2
    state["status"] = "rebuttal"

    rebuttals = {}
    for persona_key, system in PERSONAS.items():
        others = {k: v for k, v in state["arguments"].items() if k != persona_key}
        prompt = f"""News topic: {state['topic']}

Your opening argument:
{state['arguments'].get(persona_key, '')}

Other analysts' opening arguments:
{others}

Write a rebuttal that defends or sharpens your position against the weakest
points in the other arguments. Max 150 words."""
        rebuttals[persona_key] = llm.invoke(system=system, user=prompt, max_tokens=350)
    state["rebuttals"] = rebuttals

    combined = "\n\n".join(rebuttals.values())
    try:
        output_guard.validate(combined)
        passed = True
    except Exception:
        passed = False

    retries = state.get("_rebuttal_retries", 0)
    if not passed and retries < MAX_REBUTTAL_RETRIES:
        state["_rebuttal_retries"] = retries + 1
        state["guardrail_output_pass"] = False
    else:
        state["guardrail_output_pass"] = True

    return state

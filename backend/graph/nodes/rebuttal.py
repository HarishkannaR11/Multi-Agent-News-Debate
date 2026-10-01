import logging
from concurrent.futures import ThreadPoolExecutor

from ...config import llm, settings
from ..guardrails.output_guard import check_output
from ..prompts import UNTRUSTED_NOTE, format_arguments
from ..state import DebateState
from .agents import PERSONAS

logger = logging.getLogger(__name__)


def _generate(persona_key: str, state: DebateState) -> str:
    prompt = f"""News topic: {state['topic']}

Your opening argument:
{state['arguments'].get(persona_key, '')}

Other analysts' opening arguments:
{format_arguments(state['arguments'], exclude=persona_key)}

Write a rebuttal that defends or sharpens your position against the weakest
points in the other arguments. Max 150 words."""
    return llm.invoke(system=PERSONAS[persona_key] + UNTRUSTED_NOTE, user=prompt, max_tokens=350)


def rebuttal_node(state: DebateState) -> dict:
    """Generate rebuttals and screen each through the output guardrail.

    Rebuttals that pass are kept between attempts; only failing ones are regenerated.
    Once retries are exhausted, rebuttals that still fail are dropped (never published)
    and the debate moves on to the moderator with what passed.
    """
    kept = dict(state.get("rebuttals") or {})
    todo = [key for key in PERSONAS if key in state["arguments"] and key not in kept]

    with ThreadPoolExecutor(max_workers=max(1, len(todo))) as pool:
        drafts = dict(zip(todo, pool.map(lambda key: _generate(key, state), todo), strict=True))

    failed = []
    for key, draft in drafts.items():
        result = check_output(draft)
        if result.passed:
            kept[key] = result.text
        else:
            logger.warning("Rebuttal %r failed output guardrail: %s", key, result.reason)
            failed.append(key)

    retries = state.get("rebuttal_retries", 0)
    retry = bool(failed) and retries < settings.MAX_REBUTTAL_RETRIES
    if failed and not retry:
        logger.warning("Dropping rebuttals that never passed the guardrail: %s", failed)

    return {
        "round": 2,
        "status": "rebuttal",
        "rebuttals": kept,
        "rebuttal_retries": retries + 1 if retry else retries,
        "guardrail_output_pass": not retry,
    }

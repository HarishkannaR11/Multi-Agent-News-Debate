import logging  # Python's built-in logging system
from concurrent.futures import ThreadPoolExecutor  # runs several tasks at the same time in threads

from ...config import llm, settings  # the shared LLM wrapper and app settings
from ..guardrails.output_guard import check_output  # content filter for text the AI wrote
from ..prompts import UNTRUSTED_NOTE, format_arguments  # prompt-safety and formatting helpers
from ..state import DebateState  # the shared state shape
from .agents import PERSONAS  # the five analyst system prompts

# A logger named after this module.
logger = logging.getLogger(__name__)


# Writes ONE analyst's rebuttal (one LLM call).
def _generate(persona_key: str, state: DebateState) -> str:
    # The message sent to the model: topic, this analyst's own opening, the others' openings, and the task.
    prompt = f"""News topic: {state['topic']}

Your opening argument:
{state['arguments'].get(persona_key, '')}

Other analysts' opening arguments:
{format_arguments(state['arguments'], exclude=persona_key)}

Write a rebuttal that defends or sharpens your position against the weakest
points in the other arguments. Max 150 words."""
    # Call the main model with this analyst's instructions (plus the security note) and return the text.
    return llm.invoke(system=PERSONAS[persona_key] + UNTRUSTED_NOTE, user=prompt, max_tokens=350)


# Graph step: every analyst rebuts the others; the content filter checks each rebuttal.
def rebuttal_node(state: DebateState) -> dict:
    """Generate rebuttals and screen each through the output guardrail.

    Rebuttals that pass are kept between attempts; only failing ones are regenerated.
    Once retries are exhausted, rebuttals that still fail are dropped (never published)
    and the debate moves on to the moderator with what passed.
    """
    # Rebuttals that already passed on an earlier loop (so we do not redo them).
    kept = dict(state.get("rebuttals") or {})
    # Analysts that have an opening argument but no accepted rebuttal yet.
    todo = [key for key in PERSONAS if key in state["arguments"] and key not in kept]

    # Run the LLM calls in parallel threads (they mostly wait on the network); at least one worker.
    with ThreadPoolExecutor(max_workers=max(1, len(todo))) as pool:
        # Pair each analyst name with its rebuttal text; strict=True checks both lists are the same length.
        drafts = dict(zip(todo, pool.map(lambda key: _generate(key, state), todo), strict=True))

    # Names of analysts whose rebuttal was blocked this round.
    failed = []
    # Check each draft, one at a time (the content-filter model is not meant for concurrent use).
    for key, draft in drafts.items():
        # Run the output content filter.
        result = check_output(draft)
        # Approved: keep the cleaned text (e.g. personal data redacted).
        if result.passed:
            kept[key] = result.text
        # Blocked: log why and remember to retry this analyst.
        else:
            logger.warning("Rebuttal %r failed output guardrail: %s", key, result.reason)
            failed.append(key)

    # How many retry rounds have already been used.
    retries = state.get("rebuttal_retries", 0)
    # Retry only if something was blocked AND we still have retries left.
    retry = bool(failed) and retries < settings.MAX_REBUTTAL_RETRIES
    # Blocked and out of retries: these rebuttals are dropped and never shown.
    if failed and not retry:
        logger.warning("Dropping rebuttals that never passed the guardrail: %s", failed)

    # Return the state update.
    return {
        # We are now in round 2 (rebuttals).
        "round": 2,
        # Current stage.
        "status": "rebuttal",
        # All accepted rebuttals so far.
        "rebuttals": kept,
        # Increase the retry counter only if we are going to loop again.
        "rebuttal_retries": retries + 1 if retry else retries,
        # True means "done, go to the moderator"; False sends the graph back to this step.
        "guardrail_output_pass": not retry,
    }

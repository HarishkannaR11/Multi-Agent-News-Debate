import logging

from ..config import llm
from .guardrails.output_guard import check_output

logger = logging.getLogger(__name__)


def generate_guarded(
    system: str, user: str, *, max_tokens: int, retries: int, label: str, fast: bool = False
) -> str | None:
    """Call the LLM and screen the reply through the output guardrail.

    A reply that fails is regenerated up to `retries` times. Returns the validated text (PII
    redacted), or None if every attempt was blocked, so the caller decides how to degrade.
    A guardrail that cannot run raises GuardUnavailable rather than letting text through.
    """
    for attempt in range(1, retries + 2):
        result = check_output(llm.invoke(system=system, user=user, max_tokens=max_tokens, fast=fast))
        if result.passed:
            return result.text
        logger.warning("%s blocked by output guardrail (attempt %d/%d): %s", label, attempt, retries + 1, result.reason)
    return None

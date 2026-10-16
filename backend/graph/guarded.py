import logging  # Python's built-in logging system

from ..config import llm  # the shared wrapper used for every LLM call
from .guardrails.output_guard import check_output  # the content filter for model output

# A logger named after this module, so log lines show where they came from.
logger = logging.getLogger(__name__)


# Asks the LLM for text and only returns it if the content filter approves; retries if it does not.
def generate_guarded(
    system: str, user: str, *, max_tokens: int, retries: int, label: str, fast: bool = False
) -> str | None:
    """Call the LLM and screen the reply through the output guardrail.

    A reply that fails is regenerated up to `retries` times. Returns the validated text (PII
    redacted), or None if every attempt was blocked, so the caller decides how to degrade.
    A guardrail that cannot run raises GuardUnavailable rather than letting text through.
    """
    # Try once, plus "retries" more times: attempts are numbered 1, 2, 3, ...
    for attempt in range(1, retries + 2):
        # Ask the LLM, then immediately run its answer through the content filter.
        result = check_output(llm.invoke(system=system, user=user, max_tokens=max_tokens, fast=fast))
        # If the filter approved it...
        if result.passed:
            # ...return the cleaned text (e.g. with personal data redacted).
            return result.text
        # Otherwise record why it was blocked and which attempt this was.
        logger.warning("%s blocked by output guardrail (attempt %d/%d): %s", label, attempt, retries + 1, result.reason)
    # Every attempt was blocked: return None so the caller can choose a fallback.
    return None

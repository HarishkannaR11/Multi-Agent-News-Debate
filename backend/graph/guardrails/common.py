import logging  # Python's built-in logging system
from collections.abc import Callable  # type for "a function we can call"
from dataclasses import dataclass  # decorator that auto-generates a simple data-holding class
from typing import Any  # the "anything" type, used where the library's types are unknown

from ...config import settings  # the shared app settings

# A logger named after this module.
logger = logging.getLogger(__name__)


# Logs a warning if the Guardrails library is sending usage data to a third party.
def _warn_if_telemetry_enabled() -> None:
    """Guardrails reports usage metadata to a third-party endpoint unless disabled.

    It is controlled only by ~/.guardrailsrc (read once, at import), so it cannot be switched
    off reliably from inside the app; the Docker image writes that file. Locally run
    `printf 'enable_metrics=false\\n' > ~/.guardrailsrc` or `guardrails configure --disable-metrics`.
    """
    # Wrap in try so a changed library layout never breaks validation just because of a warning.
    try:
        # Import the library's own settings object.
        from guardrails.settings import settings as guardrails_settings

        # Is the "enable_metrics" switch on?
        enabled = guardrails_settings.rc.enable_metrics is True
    # If anything went wrong reading it (library internals moved), quietly skip the warning.
    except Exception:  # internals moved; don't break validation over a warning
        return
    # Telemetry is on: tell the operator how to turn it off.
    if enabled:
        logger.warning(
            "Guardrails telemetry is ENABLED and reports usage metadata to a third party. "
            "Disable it with `enable_metrics=false` in ~/.guardrailsrc."
        )


# Error raised when the content filter itself cannot run (not when text is merely blocked).
class GuardUnavailable(RuntimeError):
    """The guardrail itself could not run (missing model, hub validator, import error).

    Callers must treat this as a failure, never as a pass: silently skipping a
    broken guardrail is how unchecked content reaches users.
    """


# The outcome of one content check: did it pass, what text to use, and why it failed.
@dataclass
class GuardResult:
    # True if the text is allowed.
    passed: bool
    text: str          # validated/fixed text (PII redacted, truncated); original text on failure
    # Explanation when the text was blocked (empty otherwise).
    reason: str = ""


# A content filter that is built only the first time it is used (loading its models is slow and heavy).
class LazyGuard:
    """Builds a guardrails Guard on first use so importing the app doesn't load
    torch/transformers models (which adds ~30s and hundreds of MB to boot)."""

    # Remember the filter's name and the function that builds it; do not build it yet.
    def __init__(self, name: str, factory: Callable[[], Any]) -> None:
        # A label used in log messages, e.g. "input" or "output".
        self.name = name
        # The function that creates the real Guard object when first needed.
        self._factory = factory
        # The built Guard; None until the first check.
        self._guard: Any = None

    # Runs the content check on some text and reports the result.
    def check(self, text: str) -> GuardResult:
        # If filtering is switched off in settings, allow everything.
        if not settings.GUARDRAILS_ENABLED:
            return GuardResult(True, text, "guardrails disabled")

        # Anything unexpected inside this block means the filter itself is broken.
        try:
            # Build the guard the first time only.
            if self._guard is None:
                # Warn first if the library would send telemetry.
                _warn_if_telemetry_enabled()
                # Create the real Guard (this loads the models).
                self._guard = self._factory()
            # Import the library's "content was blocked" error type.
            from guardrails.errors import ValidationError

            # Inner try: separates "text was blocked" from "the filter is broken".
            try:
                # Run the actual check on the text.
                outcome = self._guard.validate(text)
            # The library says the text violates a rule: that is a normal "blocked" result.
            except ValidationError as exc:
                return GuardResult(False, text, str(exc))
        # Anything else (missing model, import error, ...) means the filter cannot run.
        except Exception as exc:  # setup/import/model-download failures
            # Record the full error for the operator.
            logger.exception("%s guardrail unavailable", self.name)
            # Fail closed: raise instead of letting unchecked text through.
            raise GuardUnavailable(f"{self.name} guardrail unavailable: {exc}") from exc

        # Some validators return a failed outcome instead of raising; treat that as blocked too.
        if not getattr(outcome, "validation_passed", True):
            return GuardResult(False, text, str(getattr(outcome, "error", "") or "validation failed"))
        # Passed: return the validated text (which may have been fixed, e.g. PII redacted), or the original.
        return GuardResult(True, getattr(outcome, "validated_output", None) or text)

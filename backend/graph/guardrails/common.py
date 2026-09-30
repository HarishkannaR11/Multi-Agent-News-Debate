import logging
from dataclasses import dataclass
from typing import Callable

from ...config import settings

logger = logging.getLogger(__name__)


class GuardUnavailable(RuntimeError):
    """The guardrail itself could not run (missing model, hub validator, import error).

    Callers must treat this as a failure, never as a pass: silently skipping a
    broken guardrail is how unchecked content reaches users.
    """


@dataclass
class GuardResult:
    passed: bool
    text: str          # validated/fixed text (PII redacted, truncated); original text on failure
    reason: str = ""


class LazyGuard:
    """Builds a guardrails Guard on first use so importing the app doesn't load
    torch/transformers models (which adds ~30s and hundreds of MB to boot)."""

    def __init__(self, name: str, factory: Callable[[], object]) -> None:
        self.name = name
        self._factory = factory
        self._guard = None

    def check(self, text: str) -> GuardResult:
        if not settings.GUARDRAILS_ENABLED:
            return GuardResult(True, text, "guardrails disabled")

        try:
            if self._guard is None:
                self._guard = self._factory()
            from guardrails.errors import ValidationError

            try:
                outcome = self._guard.validate(text)
            except ValidationError as exc:
                return GuardResult(False, text, str(exc))
        except Exception as exc:  # setup/import/model-download failures
            logger.exception("%s guardrail unavailable", self.name)
            raise GuardUnavailable(f"{self.name} guardrail unavailable: {exc}") from exc

        if not getattr(outcome, "validation_passed", True):
            return GuardResult(False, text, str(getattr(outcome, "error", "") or "validation failed"))
        return GuardResult(True, getattr(outcome, "validated_output", None) or text)

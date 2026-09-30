from .common import GuardResult, LazyGuard


def _build():
    from guardrails import Guard
    from guardrails_ai.detect_pii import DetectPII
    from guardrails_ai.toxic_language import ToxicLanguage

    return Guard().use(
        ToxicLanguage(threshold=0.4, on_fail="exception"),
        DetectPII(on_fail="fix"),
    )


_guard = LazyGuard("output", _build)


def check_output(text: str) -> GuardResult:
    """Screen model output; the returned text has PII redacted."""
    return _guard.check(text)

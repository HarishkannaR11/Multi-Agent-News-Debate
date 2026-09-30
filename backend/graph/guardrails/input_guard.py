from .common import GuardResult, LazyGuard


def _build():
    from guardrails import Guard
    from guardrails_ai.toxic_language import ToxicLanguage
    from guardrails_ai.valid_length import ValidLength

    return Guard().use(
        ToxicLanguage(threshold=0.3, on_fail="exception"),
        ValidLength(max=2000, on_fail="fix"),
    )


_guard = LazyGuard("input", _build)


def check_input(text: str) -> GuardResult:
    """Screen untrusted text (news articles, user opinions) before it reaches a prompt."""
    return _guard.check(text)

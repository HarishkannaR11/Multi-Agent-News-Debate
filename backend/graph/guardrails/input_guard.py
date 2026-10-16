from .common import GuardResult, LazyGuard  # the result type and the lazy-loading filter wrapper


# Builds the real filter for INCOMING text (news articles and user opinions).
def _build():
    # Imports are inside the function so the heavy libraries load only when the filter is first used.
    from guardrails import Guard  # the Guardrails container that runs validators
    from guardrails_ai.toxic_language import ToxicLanguage  # validator that detects toxic/abusive text
    from guardrails_ai.valid_length import ValidLength  # validator that limits text length

    # Combine two rules into one guard.
    return Guard().use(
        # Block text scoring above 0.3 toxicity (raise an exception so we can detect it).
        ToxicLanguage(threshold=0.3, on_fail="exception"),
        # Text longer than 2000 characters is automatically shortened ("fix").
        ValidLength(max=2000, on_fail="fix"),
    )


# Create the input filter object (not built yet; it builds on first use).
_guard = LazyGuard("input", _build)


# Public function other modules call to check incoming text.
def check_input(text: str) -> GuardResult:
    """Screen untrusted text (news articles, user opinions) before it reaches a prompt."""
    # Run the check and return its result.
    return _guard.check(text)

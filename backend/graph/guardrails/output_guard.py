from .common import GuardResult, LazyGuard  # the result type and the lazy-loading filter wrapper


# Builds the real filter for OUTGOING text (what the AI writes).
def _build():
    # Imports are inside the function so the heavy libraries load only when the filter is first used.
    from guardrails import Guard  # the Guardrails container that runs validators
    from guardrails_ai.detect_pii import DetectPII  # validator that finds personal data (emails, phones, names)
    from guardrails_ai.toxic_language import ToxicLanguage  # validator that detects toxic/abusive text

    # Combine two rules into one guard.
    return Guard().use(
        # Block text scoring above 0.4 toxicity (a slightly looser limit than for input).
        ToxicLanguage(threshold=0.4, on_fail="exception"),
        # Personal data is replaced with tags like <EMAIL_ADDRESS> instead of blocking the whole text.
        DetectPII(on_fail="fix"),
    )


# Create the output filter object (not built yet; it builds on first use).
_guard = LazyGuard("output", _build)


# Public function other modules call to check text the AI wrote.
def check_output(text: str) -> GuardResult:
    """Screen model output; the returned text has PII redacted."""
    # Run the check and return its result.
    return _guard.check(text)

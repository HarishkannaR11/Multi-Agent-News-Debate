from guardrails import Guard
from guardrails_ai.toxic_language import ToxicLanguage
from guardrails_ai.valid_length import ValidLength

input_guard = Guard().use(
    ToxicLanguage(threshold=0.3, on_fail="exception"),
    ValidLength(max=2000, on_fail="fix"),
)

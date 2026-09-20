from guardrails import Guard
from guardrails_ai.toxic_language import ToxicLanguage
from guardrails_ai.detect_pii import DetectPII

output_guard = Guard().use(
    ToxicLanguage(threshold=0.4, on_fail="exception"),
    DetectPII(on_fail="fix"),
)

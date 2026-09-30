"""Download the guardrail models at image build time.

The Guardrails validators fetch a toxicity model (detoxify/torch) and a spaCy model on first
use. Doing that at build time keeps container start fast and lets the runtime task run
without outbound access to model hosts. Standalone on purpose (no `backend` imports) so the
Docker layer that runs it is cached until the dependencies change, not on every code edit.
"""
from guardrails import Guard
from guardrails_ai.detect_pii import DetectPII
from guardrails_ai.toxic_language import ToxicLanguage

SAMPLE = "The committee will vote on the budget proposal on Tuesday."

Guard().use(ToxicLanguage(threshold=0.3, on_fail="exception")).validate(SAMPLE)
Guard().use(DetectPII(on_fail="fix")).validate(SAMPLE)
print("guardrail models ready")

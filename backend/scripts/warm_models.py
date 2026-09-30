"""Download the guardrail models at image build time.

The Guardrails validators fetch a toxicity model (detoxify/torch), NLTK tokenizer data and a
spaCy model. Doing that at build time keeps container start fast and lets the runtime task run
without outbound access to model hosts. Standalone on purpose (no `backend` imports) so the
Docker layer that runs it is cached until the dependencies change, not on every code edit.

`guardrails hub install` would normally fetch these; we install the validators from PyPI, which
skips their post-install step, so it is reproduced here.
"""
import os

import nltk

# The validator's own downloader targets ~/nltk_data of whoever runs it (root, at build time),
# which the unprivileged runtime user cannot see, and fetches `punkt` although current NLTK
# needs `punkt_tab`. Put both in the shared NLTK_DATA directory explicitly.
nltk_dir = os.environ["NLTK_DATA"]
os.makedirs(nltk_dir, exist_ok=True)
for package in ("punkt_tab", "punkt"):
    if not nltk.download(package, download_dir=nltk_dir, quiet=True):
        raise SystemExit(f"could not download NLTK package {package!r}")

from guardrails import Guard  # noqa: E402  (after NLTK data is in place)
from guardrails_ai.detect_pii import DetectPII  # noqa: E402
from guardrails_ai.toxic_language import ToxicLanguage  # noqa: E402

SAMPLE = "The committee will vote on the budget proposal on Tuesday."

Guard().use(ToxicLanguage(threshold=0.3, on_fail="exception")).validate(SAMPLE)
Guard().use(DetectPII(on_fail="fix")).validate(SAMPLE)
print("guardrail models ready")

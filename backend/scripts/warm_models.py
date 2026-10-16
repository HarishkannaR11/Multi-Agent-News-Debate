"""Download the guardrail models at image build time.

The Guardrails validators fetch a toxicity model (detoxify/torch), NLTK tokenizer data and a
spaCy model. Doing that at build time keeps container start fast and lets the runtime task run
without outbound access to model hosts. Standalone on purpose (no `backend` imports) so the
Docker layer that runs it is cached until the dependencies change, not on every code edit.

`guardrails hub install` would normally fetch these; we install the validators from PyPI, which
skips their post-install step, so it is reproduced here.
"""
import os  # standard library: environment variables and folders

import nltk  # natural-language toolkit: we need its sentence-splitting data

# The validator's own downloader targets ~/nltk_data of whoever runs it (root, at build time),
# which the unprivileged runtime user cannot see, and fetches `punkt` although current NLTK
# needs `punkt_tab`. Put both in the shared NLTK_DATA directory explicitly.
# The shared folder where NLTK data must live (set by the Dockerfile); crash if it is not set.
nltk_dir = os.environ["NLTK_DATA"]
# Create that folder if it does not exist yet.
os.makedirs(nltk_dir, exist_ok=True)
# Download both data packages the toxicity validator may need.
for package in ("punkt_tab", "punkt"):
    # If a download fails, stop the whole build with a clear message.
    if not nltk.download(package, download_dir=nltk_dir, quiet=True):
        raise SystemExit(f"could not download NLTK package {package!r}")

# The PII detector's URL recogniser downloads the public-suffix list on first use and caches it
# under TLDEXTRACT_CACHE. Prime that cache now so the runtime never needs the network for it.
# (noqa: E402 tells the linter that this import is deliberately placed after code.)
import tldextract  # noqa: E402

# Run one lookup so the library downloads and caches its domain list now.
tldextract.extract("https://www.example.co.uk/path")

# These imports come after the NLTK data is in place, so they are deliberately not at the top of the file.
from guardrails import Guard  # noqa: E402  (after NLTK data is in place)
from guardrails_ai.detect_pii import DetectPII  # noqa: E402
from guardrails_ai.toxic_language import ToxicLanguage  # noqa: E402

# A harmless sentence used to make each validator load its model.
SAMPLE = "The committee will vote on the budget proposal on Tuesday."

# Build the toxicity guard and run it once, which downloads and loads the toxicity model.
Guard().use(ToxicLanguage(threshold=0.3, on_fail="exception")).validate(SAMPLE)
# Build the personal-data guard and run it once, which downloads and loads the spaCy model.
Guard().use(DetectPII(on_fail="fix")).validate(SAMPLE)
# Print a message the build log will show on success.
print("guardrail models ready")

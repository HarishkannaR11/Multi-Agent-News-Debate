# syntax=docker/dockerfile:1
# Build from the repo root:  docker build -f backend/Dockerfile -t counterpoint-backend .

# Start from the official slim Python 3.11 image (a small Debian-based system with Python installed).
FROM python:3.11-slim

# Environment variables that exist while building AND when the container runs:
#   PYTHONUNBUFFERED=1        print logs immediately instead of holding them in a buffer
#   PYTHONDONTWRITEBYTECODE=1 do not create .pyc cache files (keeps the image smaller)
#   PIP_NO_CACHE_DIR=1        do not keep pip's download cache (smaller image)
#   PIP_DISABLE_PIP_VERSION_CHECK=1  do not make pip check the internet for a newer pip
#   HF_HOME / TORCH_HOME      folders where the AI models (HuggingFace / PyTorch) are stored
#   NLTK_DATA                 folder for the NLTK text-splitting data
#   TLDEXTRACT_CACHE          folder for the cached list of domain suffixes (.com, .co.uk ...)
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HF_HOME=/opt/models/hf \
    TORCH_HOME=/opt/models/torch \
    NLTK_DATA=/opt/models/nltk \
    TLDEXTRACT_CACHE=/opt/models/tldextract

# All following commands run from /app inside the image (the folder is created if needed).
WORKDIR /app

# Dependencies first so code edits don't invalidate these layers.
# CPU-only torch is installed separately (the default wheel drags in ~3 GB of CUDA libraries).
# Copy only the two requirements files into backend/ (Docker caches this step until they change).
COPY backend/requirements-torch.txt backend/requirements.txt backend/
# Install CPU-only torch first, then every other Python library (&& means "only continue if the first succeeded").
RUN pip install -r backend/requirements-torch.txt \
 && pip install -r backend/requirements.txt

# Guardrails sends usage telemetry to a third-party endpoint unless told not to. It only honours
# ~/.guardrailsrc, read once at import, so write it before anything imports guardrails
# (root for the build step below, `app` further down for runtime).
# Create the model folders, and write a config file switching the telemetry off for the root user.
RUN mkdir -p /opt/models/nltk /opt/models/tldextract \
 && printf 'enable_metrics=false\n' > /root/.guardrailsrc

# Fetch guardrail models now (fails the build if they can't be downloaded).
# Copy just the download script (not the whole code), so this slow layer is not rebuilt on every code edit.
COPY backend/scripts/warm_models.py backend/scripts/warm_models.py
# Run it: downloads and stores the toxicity model, spaCy model and NLTK data inside the image.
RUN python backend/scripts/warm_models.py

# Now copy all the backend code (this changes often, so it comes after the slow steps above).
COPY backend backend

# Declared this late on purpose: changing them (see deploy/huggingface) only invalidates the layers
# below, not the multi-GB dependency and model layers above.
# Build-time options with defaults: the id of the user the app runs as, and the port it listens on.
ARG APP_UID=10001
ARG PORT=8000
# Keep the chosen port in an environment variable so it is available when the container runs.
ENV PORT=${PORT}

# Run unprivileged. The app only needs to read the code and write to the model caches.
# Create a system user named "app", write the telemetry-off file for that user, and give it ownership of the model folders.
RUN useradd --system --uid ${APP_UID} --create-home app \
 && printf 'enable_metrics=false\n' > /home/app/.guardrailsrc \
 && chown -R app /opt/models /home/app/.guardrailsrc
# From here on, everything (including the running app) uses that user instead of root.
USER app

# Log in JSON format (easy for log tools to parse).
ENV LOG_FORMAT=json
# Document which port the app listens on (this does not publish it by itself).
EXPOSE ${PORT}

# stdlib only, so the image needs no curl. Start period covers loading the torch models.
# Docker runs this check every 30s; a 5s timeout; failures in the first 90s are ignored; 3 failures = "unhealthy".
# The command is a tiny Python program that requests /health and exits 0 only if the answer is HTTP 200.
HEALTHCHECK --interval=30s --timeout=5s --start-period=90s --retries=3 \
  CMD ["python", "-c", "import os, sys, urllib.request as u; sys.exit(0 if u.urlopen(f\"http://127.0.0.1:{os.environ['PORT']}/health\", timeout=4).status == 200 else 1)"]

# One worker on purpose: the in-process scheduler and guardrail models are per-process.
# (The Redis lock keeps the daily job idempotent if you run more than one task.)
# Start the web server through "sh -c" so ${PORT} is expanded; "exec" lets uvicorn receive stop signals directly.
CMD ["sh", "-c", "exec uvicorn backend.main:app --host 0.0.0.0 --port ${PORT} --workers 1"]

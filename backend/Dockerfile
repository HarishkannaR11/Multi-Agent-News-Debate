# syntax=docker/dockerfile:1
# Build from the repo root:  docker build -f backend/Dockerfile -t counterpoint-backend .
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HF_HOME=/opt/models/hf \
    TORCH_HOME=/opt/models/torch \
    NLTK_DATA=/opt/models/nltk \
    TLDEXTRACT_CACHE=/opt/models/tldextract

WORKDIR /app

# Dependencies first so code edits don't invalidate these layers.
# CPU-only torch is installed separately (the default wheel drags in ~3 GB of CUDA libraries).
COPY backend/requirements-torch.txt backend/requirements.txt backend/
RUN pip install -r backend/requirements-torch.txt \
 && pip install -r backend/requirements.txt

# Guardrails sends usage telemetry to a third-party endpoint unless told not to. It only honours
# ~/.guardrailsrc, read once at import, so write it before anything imports guardrails
# (root for the build step below, `app` further down for runtime).
RUN mkdir -p /opt/models/nltk /opt/models/tldextract \
 && printf 'enable_metrics=false\n' > /root/.guardrailsrc

# Fetch guardrail models now (fails the build if they can't be downloaded).
COPY backend/scripts/warm_models.py backend/scripts/warm_models.py
RUN python backend/scripts/warm_models.py

COPY backend backend

# Declared this late on purpose: changing them (see deploy/huggingface) only invalidates the layers
# below, not the multi-GB dependency and model layers above.
ARG APP_UID=10001
ARG PORT=8000
ENV PORT=${PORT}

# Run unprivileged. The app only needs to read the code and write to the model caches.
RUN useradd --system --uid ${APP_UID} --create-home app \
 && printf 'enable_metrics=false\n' > /home/app/.guardrailsrc \
 && chown -R app /opt/models /home/app/.guardrailsrc
USER app

ENV LOG_FORMAT=json
EXPOSE ${PORT}

# stdlib only, so the image needs no curl. Start period covers loading the torch models.
HEALTHCHECK --interval=30s --timeout=5s --start-period=90s --retries=3 \
  CMD ["python", "-c", "import os, sys, urllib.request as u; sys.exit(0 if u.urlopen(f\"http://127.0.0.1:{os.environ['PORT']}/health\", timeout=4).status == 200 else 1)"]

# One worker on purpose: the in-process scheduler and guardrail models are per-process.
# (The Redis lock keeps the daily job idempotent if you run more than one task.)
CMD ["sh", "-c", "exec uvicorn backend.main:app --host 0.0.0.0 --port ${PORT} --workers 1"]

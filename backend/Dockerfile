# syntax=docker/dockerfile:1
# Build from the repo root:  docker build -f backend/Dockerfile -t counterpoint-backend .
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HF_HOME=/opt/models/hf \
    TORCH_HOME=/opt/models/torch \
    NLTK_DATA=/opt/models/nltk

WORKDIR /app

# Dependencies first so code edits don't invalidate these layers.
# CPU-only torch is installed separately (the default wheel drags in ~3 GB of CUDA libraries).
COPY backend/requirements-torch.txt backend/requirements.txt backend/
RUN pip install -r backend/requirements-torch.txt \
 && pip install -r backend/requirements.txt

# Fetch guardrail models now (fails the build if they can't be downloaded).
COPY backend/scripts/warm_models.py backend/scripts/warm_models.py
RUN python backend/scripts/warm_models.py

COPY backend backend

# Run unprivileged. The app only needs to read the code and write to the model caches.
RUN useradd --system --uid 10001 --create-home app \
 && chown -R app /opt/models
USER app

ENV LOG_FORMAT=json
EXPOSE 8000

# stdlib only, so the image needs no curl. Start period covers loading the torch models.
HEALTHCHECK --interval=30s --timeout=5s --start-period=90s --retries=3 \
  CMD ["python", "-c", "import urllib.request, sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4).status == 200 else 1)"]

# One worker on purpose: the in-process scheduler and guardrail models are per-process.
# (The Redis lock keeps the daily job idempotent if you run more than one task.)
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]

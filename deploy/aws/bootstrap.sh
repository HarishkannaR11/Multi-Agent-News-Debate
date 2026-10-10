#!/usr/bin/env bash
# Install Docker if needed, write the app's .env from AWS Secrets Manager, build and start the stack.
# Runs on first boot (from the instance's user data) and is safe to re-run.
#
# env: SECRET_ID    Secrets Manager secret holding a JSON object of KEY=value pairs for the app
#      AWS_REGION   region of that secret
#      APP_DIR      checkout of this repository (default /opt/counterpoint/app)
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/counterpoint/app}"
SECRET_ID="${SECRET_ID:?set SECRET_ID}"
AWS_REGION="${AWS_REGION:?set AWS_REGION}"
COMPOSE_DIR="$APP_DIR/deploy/aws"
ENV_FILE="$COMPOSE_DIR/.env"

log() { echo "[bootstrap $(date -u +%H:%M:%S)] $*"; }

install_packages() {
  if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
    return
  fi
  log "installing Docker and tools"
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -y
  apt-get install -y docker.io docker-compose-v2 docker-buildx git curl jq python3-boto3
  systemctl enable --now docker
}

add_swap() {
  # Insurance: the content-filter models use ~2 GB; a little swap turns an out-of-memory kill
  # during a spike into a slow request.
  if [ ! -f /swapfile ]; then
    log "creating 2 GB swap"
    fallocate -l 2G /swapfile
    chmod 600 /swapfile
    mkswap /swapfile >/dev/null
    swapon /swapfile
    grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
  fi
}

write_env() {
  log "writing $ENV_FILE from Secrets Manager (not logged)"
  python3 - "$SECRET_ID" "$AWS_REGION" "$ENV_FILE" <<'PY'
import json
import os
import sys

import boto3

secret_id, region, path = sys.argv[1:4]
client = boto3.client("secretsmanager", region_name=region)
data = json.loads(client.get_secret_value(SecretId=secret_id)["SecretString"])
fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
os.fchmod(fd, 0o600)  # the mode above only applies when the file is created; enforce it on re-runs too
with os.fdopen(fd, "w") as handle:
    for key, value in data.items():
        handle.write(f"{key}={value}\n")
PY
}

install_packages
add_swap
write_env

log "building and starting the stack (the first build takes 10-15 minutes)"
cd "$COMPOSE_DIR"
docker compose up -d --build

log "waiting for the backend to report ready"
for _ in $(seq 1 60); do
  if curl -fsS --max-time 5 http://127.0.0.1/health/ready 2>/dev/null | jq -e '.status == "ready"' >/dev/null 2>&1; then
    log "ready"
    exit 0
  fi
  sleep 5
done
log "backend did not become ready in 5 minutes; check: docker compose -f $COMPOSE_DIR/docker-compose.yml logs backend"
exit 1

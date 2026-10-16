#!/usr/bin/env bash
# Install Docker if needed, write the app's .env from AWS Secrets Manager, build and start the stack.
# Runs on first boot (from the instance's user data) and is safe to re-run.
#
# env: SECRET_ID    Secrets Manager secret holding a JSON object of KEY=value pairs for the app
#      AWS_REGION   region of that secret
#      APP_DIR      checkout of this repository (default /opt/counterpoint/app)

# Safety switches: -e stop at the first failing command, -u treat an unset variable as an error,
# -o pipefail make a pipeline fail if any command inside it fails.
set -euo pipefail

# Where the repository is checked out; use the APP_DIR env var if set, otherwise the default path.
APP_DIR="${APP_DIR:-/opt/counterpoint/app}"
# The name of the Secrets Manager secret; stop with the message "set SECRET_ID" if it is missing.
SECRET_ID="${SECRET_ID:?set SECRET_ID}"
# The AWS region the secret lives in; stop with a message if it is missing.
AWS_REGION="${AWS_REGION:?set AWS_REGION}"
# The folder holding docker-compose.yml and the Caddyfile.
COMPOSE_DIR="$APP_DIR/deploy/aws"
# The file the app's settings will be written to (docker compose reads it).
ENV_FILE="$COMPOSE_DIR/.env"

# Prints a message prefixed with the script name and the current UTC time (hours:minutes:seconds).
log() { echo "[bootstrap $(date -u +%H:%M:%S)] $*"; }

# Installs Docker and helper tools, unless Docker and the "compose" plugin are already there.
install_packages() {
  # If both the docker command and "docker compose" work, there is nothing to do.
  if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
    # Leave the function early.
    return
  fi
  log "installing Docker and tools"
  # Tell apt never to ask questions (nobody is at the keyboard on first boot).
  export DEBIAN_FRONTEND=noninteractive
  # Refresh the list of available packages.
  apt-get update -y
  # Install Docker, the compose plugin, the image builder, git, curl, jq (JSON tool) and boto3 (AWS library for Python).
  apt-get install -y docker.io docker-compose-v2 docker-buildx git curl jq python3-boto3
  # Start Docker now and on every future boot.
  systemctl enable --now docker
}

# Creates a 2 GB swap file (disk space used as emergency memory).
add_swap() {
  # Insurance: the content-filter models use ~2 GB; a little swap turns an out-of-memory kill
  # during a spike into a slow request.
  # Only create it if it does not already exist (so re-running the script is safe).
  if [ ! -f /swapfile ]; then
    log "creating 2 GB swap"
    # Reserve a 2 GB file.
    fallocate -l 2G /swapfile
    # Make it readable by root only (swap can contain secrets from memory).
    chmod 600 /swapfile
    # Format it as swap space (hide the normal output).
    mkswap /swapfile >/dev/null
    # Start using it now.
    swapon /swapfile
    # Add it to /etc/fstab so it is used after a reboot, unless a line for it is already there.
    grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
  fi
}

# Reads the secret from AWS Secrets Manager and writes it to the .env file.
write_env() {
  log "writing $ENV_FILE from Secrets Manager (not logged)"
  # Run an inline Python program (everything up to the PY line below) and pass it the three values as arguments.
  # The quotes around 'PY' stop the shell from changing anything inside the program.
  python3 - "$SECRET_ID" "$AWS_REGION" "$ENV_FILE" <<'PY'
# JSON parsing, file/permission tools, and command-line arguments.
import json
import os
import sys

# The AWS SDK for Python.
import boto3

# The three arguments given on the command line.
secret_id, region, path = sys.argv[1:4]
# A client for the Secrets Manager service (it uses the instance's IAM role; no keys are stored).
client = boto3.client("secretsmanager", region_name=region)
# Fetch the secret text and parse it into a dictionary of settings.
data = json.loads(client.get_secret_value(SecretId=secret_id)["SecretString"])
# Open the file for writing (create it, or empty it if it exists) with permissions 600: owner can read/write only.
fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
os.fchmod(fd, 0o600)  # the mode above only applies when the file is created; enforce it on re-runs too
# Wrap the file descriptor in a normal file object, and close it automatically at the end.
with os.fdopen(fd, "w") as handle:
    # Write one KEY=value line per setting.
    for key, value in data.items():
        handle.write(f"{key}={value}\n")
PY
}

# The main sequence: install tools, add swap, then write the settings file.
install_packages
add_swap
write_env

log "building and starting the stack (the first build takes 10-15 minutes)"
# Go to the folder with docker-compose.yml (the script stops if this fails).
cd "$COMPOSE_DIR"
# Build the images and start all containers in the background (-d).
docker compose up -d --build

log "waiting for the backend to report ready"
# Try up to 60 times (seq makes the numbers 1..60; "_" means we ignore the value).
for _ in $(seq 1 60); do
  # Ask the health endpoint for its status; jq succeeds only if the JSON says "ready". All output is hidden.
  if curl -fsS --max-time 5 http://127.0.0.1/health/ready 2>/dev/null | jq -e '.status == "ready"' >/dev/null 2>&1; then
    log "ready"
    # Success: stop the script with exit code 0.
    exit 0
  fi
  # Wait 5 seconds before the next try.
  sleep 5
done
# 60 tries x 5 seconds = 5 minutes without success: explain how to investigate, and exit with an error.
log "backend did not become ready in 5 minutes; check: docker compose -f $COMPOSE_DIR/docker-compose.yml logs backend"
exit 1

#!/usr/bin/env bash
# Generate today's debate right now (the built-in scheduler also does this daily).
#   sudo /opt/counterpoint/app/deploy/aws/run-daily.sh            # no-op if today's debate exists
#   sudo FORCE=true /opt/counterpoint/app/deploy/aws/run-daily.sh # generate again

# Stop on the first error, on unset variables, and on failures inside pipelines.
set -euo pipefail
# The repository checkout (override with the APP_DIR env var).
APP_DIR="${APP_DIR:-/opt/counterpoint/app}"
# Read the admin password from the stack's .env: find the ADMIN_TOKEN= line, and keep everything after the first "=".
ADMIN_TOKEN="$(grep -E '^ADMIN_TOKEN=' "$APP_DIR/deploy/aws/.env" | cut -d= -f2-)"
# Make it visible to the script we run next.
export ADMIN_TOKEN
# Talk to the backend through the local Caddy router.
export BACKEND_URL="http://127.0.0.1"
# Replace this script with the shared trigger script (it also picks up the FORCE variable if you set it).
exec "$APP_DIR/deploy/scripts/trigger_daily.sh"

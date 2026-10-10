#!/usr/bin/env bash
# Generate today's debate right now (the built-in scheduler also does this daily).
#   sudo /opt/counterpoint/app/deploy/aws/run-daily.sh            # no-op if today's debate exists
#   sudo FORCE=true /opt/counterpoint/app/deploy/aws/run-daily.sh # generate again
set -euo pipefail
APP_DIR="${APP_DIR:-/opt/counterpoint/app}"
ADMIN_TOKEN="$(grep -E '^ADMIN_TOKEN=' "$APP_DIR/deploy/aws/.env" | cut -d= -f2-)"
export ADMIN_TOKEN
export BACKEND_URL="http://127.0.0.1"
exec "$APP_DIR/deploy/scripts/trigger_daily.sh"

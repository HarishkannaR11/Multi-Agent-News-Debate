#!/usr/bin/env bash
# Pull the latest code and rebuild/restart the stack (also refreshes the app's secrets).
#   sudo SECRET_ID=... AWS_REGION=... /opt/counterpoint/app/deploy/aws/update.sh
# The CloudFormation template saves SECRET_ID and AWS_REGION in /etc/counterpoint.env for you.
set -euo pipefail
APP_DIR="${APP_DIR:-/opt/counterpoint/app}"
# shellcheck disable=SC1091
[ -f /etc/counterpoint.env ] && . /etc/counterpoint.env
git -C "$APP_DIR" pull --ff-only
exec "$APP_DIR/deploy/aws/bootstrap.sh"

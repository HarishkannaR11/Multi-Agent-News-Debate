#!/usr/bin/env bash
# Pull the latest code and rebuild/restart the stack (also refreshes the app's secrets).
#   sudo SECRET_ID=... AWS_REGION=... /opt/counterpoint/app/deploy/aws/update.sh
# The CloudFormation template saves SECRET_ID and AWS_REGION in /etc/counterpoint.env for you.

# Stop on the first error, on unset variables, and on failures inside pipelines.
set -euo pipefail
# The repository checkout (override with the APP_DIR env var).
APP_DIR="${APP_DIR:-/opt/counterpoint/app}"
# Load SECRET_ID and AWS_REGION from the file CloudFormation created, if it exists ("." means "run this file here").
# The next line is a note for the shellcheck linter: it cannot follow a file path that is only known at run time.
# shellcheck disable=SC1091
[ -f /etc/counterpoint.env ] && . /etc/counterpoint.env
# Download the newest commits; --ff-only refuses to pull if it would need a merge.
git -C "$APP_DIR" pull --ff-only
# Replace this script with bootstrap.sh, which rewrites the settings and rebuilds/restarts the stack.
exec "$APP_DIR/deploy/aws/bootstrap.sh"

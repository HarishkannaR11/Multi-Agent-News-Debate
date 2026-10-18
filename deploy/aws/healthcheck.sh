#!/usr/bin/env bash
# Publishes one CloudWatch metric, Counterpoint/Healthy (1 = fine, 0 = a problem), every few minutes.
# A CloudWatch alarm (see cloudformation.yaml) emails you when it stays at 0. bootstrap.sh installs a
# cron entry that runs this script; it is safe to run by hand too:
#   sudo /opt/counterpoint/app/deploy/aws/healthcheck.sh
#
# It reports 0 when
#   * the backend does not answer {"status":"ready"} (backend down, or Redis unreachable), or
#   * the newest debate is older than MAX_AGE_HOURS (the daily job is not producing debates).
#
# env: AWS_REGION       region to publish the metric in (read from /etc/counterpoint.env by cron)
#      MAX_AGE_HOURS    how old the newest debate may be (default 36)
#      BASE_URL         backend address (default http://127.0.0.1)

# Stop on the first error, on unset variables, and on failures inside pipelines.
set -euo pipefail

# The settings, each with a default.
base="${BASE_URL:-http://127.0.0.1}"
max_age_hours="${MAX_AGE_HOURS:-36}"
region="${AWS_REGION:?set AWS_REGION}"

# Start by assuming everything is fine; each failed check below changes this and says why.
healthy=1
reason="ok"

# Check 1: the backend reports ready (Redis reachable, app running).
if ! curl -fsS --max-time 10 "$base/health/ready" 2>/dev/null | jq -e '.status == "ready"' >/dev/null 2>&1; then
  healthy=0
  reason="backend is not ready"
else
  # Check 2: the newest debate is recent enough.
  newest="$(curl -fsS --max-time 10 "$base/api/debates?limit=1" 2>/dev/null | jq -r '.[0].created_at // ""' || true)"
  # Seconds since this server booted (the first field of /proc/uptime, without the decimals).
  uptime_s="$(cut -d. -f1 /proc/uptime)"
  if [ -n "$newest" ]; then
    # Age of the newest debate in seconds: now minus its creation time.
    age_s=$(( $(date +%s) - $(date -d "$newest" +%s) ))
    if [ "$age_s" -gt $(( max_age_hours * 3600 )) ]; then
      healthy=0
      reason="newest debate is $(( age_s / 3600 )) hours old"
    fi
  elif [ "$uptime_s" -gt $(( max_age_hours * 3600 )) ]; then
    # No debate at all, although the server has been up longer than the allowed age.
    healthy=0
    reason="no debate exists"
  fi
fi

# Print the result (cron mails or discards this; Session Manager users see it).
echo "[healthcheck $(date -u +%H:%M:%S)] healthy=$healthy ($reason)"

# Send the number to CloudWatch with a short Python program (boto3 uses the instance's IAM role).
python3 - "$region" "$healthy" <<'PY'
# Command-line arguments and the AWS SDK for Python.
import sys

import boto3

# The region and the 1/0 value given on the command line.
region, value = sys.argv[1], float(sys.argv[2])
# Publish one data point named Healthy in the Counterpoint namespace.
boto3.client("cloudwatch", region_name=region).put_metric_data(
    Namespace="Counterpoint",
    MetricData=[{"MetricName": "Healthy", "Value": value, "Unit": "Count"}],
)
PY

#!/usr/bin/env bash
# Wake the backend, ask it to generate today's debate, and wait until a fresh debate is saved.
#
# Free hosts put idle services to sleep, so the in-process scheduler can't be relied on. A GitHub
# Actions cron runs this instead: it wakes the service, triggers POST /internal/run-daily (which is
# idempotent), and exits non-zero (-> GitHub emails you) if no new debate appears in time.
#
# env: BACKEND_URL, ADMIN_TOKEN (required)
#      FORCE=true            generate again even if today's debate already exists
#      WAKE_TIMEOUT=600      seconds to wait for a sleeping service to become ready
#      RUN_TIMEOUT=900       seconds to wait for the debate to be saved
#      POLL_SECONDS=10

# Stop on the first error, on unset variables, and on failures inside pipelines.
set -euo pipefail

# Required settings: stop with the given message if either is missing.
: "${BACKEND_URL:?set BACKEND_URL}"
: "${ADMIN_TOKEN:?set ADMIN_TOKEN}"
# The backend address without a trailing slash.
base="${BACKEND_URL%/}"
# Optional settings, each with a default.
force="${FORCE:-false}"
wake_timeout="${WAKE_TIMEOUT:-600}"
run_timeout="${RUN_TIMEOUT:-900}"
poll="${POLL_SECONDS:-10}"

# Prints a GitHub Actions error annotation and stops the script with an error code.
fail() { echo "::error::$*" >&2; exit 1; }

# Only a JSON {"status":"ready"} counts: a sleeping host may answer 200 with its own HTML page.
# Succeeds (exit code 0) only when the readiness endpoint returns JSON with status "ready".
ready() {
  curl -fsS --max-time 20 "$base/health/ready" 2>/dev/null | jq -e '.status == "ready"' >/dev/null 2>&1
}

# Prints the creation time of the newest debate (an empty string if there are none).
newest_created_at() {
  curl -fsS --max-time 30 "$base/api/debates?limit=1" | jq -r '.[0].created_at // ""'
}

echo "Waiting for $base to be ready (up to ${wake_timeout}s)..."
# The time (seconds since 1970) after which we give up.
deadline=$(( $(date +%s) + wake_timeout ))
# Repeat until ready() succeeds.
until ready; do
  # If the deadline has passed, stop with an error.
  [ "$(date +%s)" -lt "$deadline" ] || fail "backend not ready after ${wake_timeout}s (is the Space asleep, or Redis unreachable?)"
  # Wait before trying again.
  sleep "$poll"
done
echo "Backend is ready."

# Remember the newest debate's timestamp, so we can recognise a new one later.
before="$(newest_created_at)"

# Ask the backend to start the daily run, sending the admin token.
# -w appends a newline and the HTTP status code to the end of the output, so we can split body and code below.
response="$(curl -sS --max-time 60 -X POST -H "X-Admin-Token: ${ADMIN_TOKEN}" \
  -w '\n%{http_code}' "$base/internal/run-daily?force=${force}")"
# The status code is the text after the last newline...
code="${response##*$'\n'}"
# ...and the body is everything before it.
body="${response%$'\n'*}"

# Decide what to do based on the status code.
case "$code" in
  # 202: the run started; keep going and wait for the result.
  202) echo "Run accepted: $body" ;;
  # 200: today's debate already exists, so there is nothing to do; finish successfully.
  200) echo "Nothing to do: $body"; exit 0 ;;
  # 401: the token we sent is wrong.
  401) fail "admin token rejected (ADMIN_TOKEN secret differs from the backend's)" ;;
  # 503: the backend has no admin token configured, so the endpoint is switched off.
  503) fail "admin endpoint disabled on the backend (set ADMIN_TOKEN there)" ;;
  # Anything else is unexpected.
  *)   fail "unexpected HTTP $code from run-daily: $body" ;;
esac

echo "Waiting for the debate to be saved (up to ${run_timeout}s)..."
# A new deadline for the generation itself.
deadline=$(( $(date +%s) + run_timeout ))
# Loop forever (":" is a command that always succeeds); the loop is left through exit.
while :; do
  # Look at the newest debate's timestamp ("|| true" so a temporary network error does not stop the script).
  now_created="$(newest_created_at || true)"
  # A non-empty timestamp that differs from the one before means a new debate was saved.
  if [ -n "$now_created" ] && [ "$now_created" != "$before" ]; then
    # Fetch its topic to print a friendly message.
    topic="$(curl -fsS --max-time 30 "$base/api/debate/latest" | jq -r '.topic')"
    echo "Debate saved: $topic"
    # Success.
    exit 0
  fi
  # Out of time: stop with an error telling the operator where to look.
  [ "$(date +%s)" -lt "$deadline" ] || fail "no new debate within ${run_timeout}s; check the backend logs (Groq key/quota, news API key)"
  sleep "$poll"
done

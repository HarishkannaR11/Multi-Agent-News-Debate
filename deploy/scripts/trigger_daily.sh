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
set -euo pipefail

: "${BACKEND_URL:?set BACKEND_URL}"
: "${ADMIN_TOKEN:?set ADMIN_TOKEN}"
base="${BACKEND_URL%/}"
force="${FORCE:-false}"
wake_timeout="${WAKE_TIMEOUT:-600}"
run_timeout="${RUN_TIMEOUT:-900}"
poll="${POLL_SECONDS:-10}"

fail() { echo "::error::$*" >&2; exit 1; }

# Only a JSON {"status":"ready"} counts: a sleeping host may answer 200 with its own HTML page.
ready() {
  curl -fsS --max-time 20 "$base/health/ready" 2>/dev/null | jq -e '.status == "ready"' >/dev/null 2>&1
}

newest_created_at() {
  curl -fsS --max-time 30 "$base/api/debates?limit=1" | jq -r '.[0].created_at // ""'
}

echo "Waiting for $base to be ready (up to ${wake_timeout}s)..."
deadline=$(( $(date +%s) + wake_timeout ))
until ready; do
  [ "$(date +%s)" -lt "$deadline" ] || fail "backend not ready after ${wake_timeout}s (is the Space asleep, or Redis unreachable?)"
  sleep "$poll"
done
echo "Backend is ready."

before="$(newest_created_at)"

response="$(curl -sS --max-time 60 -X POST -H "X-Admin-Token: ${ADMIN_TOKEN}" \
  -w '\n%{http_code}' "$base/internal/run-daily?force=${force}")"
code="${response##*$'\n'}"
body="${response%$'\n'*}"

case "$code" in
  202) echo "Run accepted: $body" ;;
  200) echo "Nothing to do: $body"; exit 0 ;;
  401) fail "admin token rejected (ADMIN_TOKEN secret differs from the backend's)" ;;
  503) fail "admin endpoint disabled on the backend (set ADMIN_TOKEN there)" ;;
  *)   fail "unexpected HTTP $code from run-daily: $body" ;;
esac

echo "Waiting for the debate to be saved (up to ${run_timeout}s)..."
deadline=$(( $(date +%s) + run_timeout ))
while :; do
  now_created="$(newest_created_at || true)"
  if [ -n "$now_created" ] && [ "$now_created" != "$before" ]; then
    topic="$(curl -fsS --max-time 30 "$base/api/debate/latest" | jq -r '.topic')"
    echo "Debate saved: $topic"
    exit 0
  fi
  [ "$(date +%s)" -lt "$deadline" ] || fail "no new debate within ${run_timeout}s; check the backend logs (Groq key/quota, news API key)"
  sleep "$poll"
done

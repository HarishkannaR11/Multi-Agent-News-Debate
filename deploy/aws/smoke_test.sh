#!/usr/bin/env bash
# Checks a running stack from the outside, through the Caddy router (what CloudFront will hit).
#   deploy/aws/smoke_test.sh [base-url]        default http://127.0.0.1
# Expects the stack's .env to set ADMIN_TOKEN, OPINION_RATE_LIMIT=2 and OPINION_GLOBAL_LIMIT_PER_HOUR=0
# (that is how CI starts it). Needs curl, jq, python3 with the `websockets` package.
set -euo pipefail

base="${1:-http://127.0.0.1}"
fail() { echo "FAIL: $*" >&2; exit 1; }
status() { curl -s -o /dev/null -w '%{http_code}' "$@"; }

echo "1. backend becomes ready (health route is proxied to the API)"
for i in $(seq 1 60); do
  if curl -fsS --max-time 5 "$base/health/ready" 2>/dev/null | jq -e '.status == "ready"' >/dev/null 2>&1; then break; fi
  [ "$i" -lt 60 ] || fail "backend not ready after 3 minutes"
  sleep 3
done

echo "2. frontend is served on / and its static assets load"
html="$(curl -fsS "$base/")"
grep -q "The Debate" <<<"$html" || fail "home page does not contain the site title"
asset="$(grep -o '/_next/static/[^"]*\.css' <<<"$html" | head -1)"
[ -n "$asset" ] || fail "no CSS asset referenced by the home page"
[ "$(status "$base$asset")" = "200" ] || fail "static asset $asset not served"

echo "3. API routes reach the backend, and the admin route is protected"
[ "$(curl -fsS "$base/api/debates")" = "[]" ] || fail "/api/debates should be [] on a fresh stack"
[ "$(status -X POST "$base/internal/run-daily")" = "401" ] || fail "run-daily without a token should be 401"

echo "4. WebSocket upgrades work through the router"
python3 - "$base" <<'PY'
import asyncio
import json
import sys

import websockets


async def main(base: str) -> None:
    url = base.replace("http", "ws", 1) + "/ws/debate/latest"
    async with websockets.connect(url) as ws:
        message = json.loads(await asyncio.wait_for(ws.recv(), 10))
    assert message.get("error") == "not_found", message


asyncio.run(main(sys.argv[1]))
PY

echo "5. per-client rate limiting survives the proxy chain (X-Forwarded-For is preserved)"
hit() {  # no debate exists, so an allowed request is a 404; a rate-limited one is a 429
  status -X POST -H "X-Forwarded-For: $1" -H 'Content-Type: application/json' \
    -d '{"user_id":"ci","opinion":"hello"}' "$base/api/opinion/latest"
}
[ "$(hit 203.0.113.9)" = "404" ] || fail "first request from client A should be allowed (404)"
[ "$(hit 203.0.113.9)" = "404" ] || fail "second request from client A should be allowed (404)"
[ "$(hit 203.0.113.9)" = "429" ] || fail "third request from client A should be rate limited (429)"
[ "$(hit 203.0.113.10)" = "404" ] || fail "client B must not share client A's rate-limit bucket"

echo "all stack checks passed"

#!/usr/bin/env bash
# Checks a running stack from the outside, through the Caddy router (what CloudFront will hit).
#   deploy/aws/smoke_test.sh [base-url]        default http://127.0.0.1
# Expects the stack's .env to set ADMIN_TOKEN, OPINION_RATE_LIMIT=2 and OPINION_GLOBAL_LIMIT_PER_HOUR=0
# (that is how CI starts it). Needs curl, jq, python3 with the `websockets` package.

# Stop on the first error, on unset variables, and on failures inside pipelines.
set -euo pipefail

# The address to test: the first argument, or the local router by default.
base="${1:-http://127.0.0.1}"
# Prints "FAIL: <message>" to the error stream and stops the script with an error code.
fail() { echo "FAIL: $*" >&2; exit 1; }
# Runs curl silently and prints only the HTTP status code (e.g. 200); extra arguments are passed on to curl.
status() { curl -s -o /dev/null -w '%{http_code}' "$@"; }

echo "1. backend becomes ready (health route is proxied to the API)"
# Try up to 60 times, 3 seconds apart (3 minutes).
for i in $(seq 1 60); do
  # If the health endpoint answers with JSON saying "ready", leave the loop.
  if curl -fsS --max-time 5 "$base/health/ready" 2>/dev/null | jq -e '.status == "ready"' >/dev/null 2>&1; then break; fi
  # On the last attempt, give up with an error.
  [ "$i" -lt 60 ] || fail "backend not ready after 3 minutes"
  sleep 3
done

echo "2. frontend is served on / and its static assets load"
# Download the home page HTML.
html="$(curl -fsS "$base/")"
# It must contain the site title.
grep -q "The Debate" <<<"$html" || fail "home page does not contain the site title"
# Find the first CSS file the page refers to (-o prints only the matching part).
asset="$(grep -o '/_next/static/[^"]*\.css' <<<"$html" | head -1)"
# There must be one.
[ -n "$asset" ] || fail "no CSS asset referenced by the home page"
# And downloading it must return HTTP 200.
[ "$(status "$base$asset")" = "200" ] || fail "static asset $asset not served"

echo "3. API routes reach the backend, and the admin route is protected"
# A fresh stack has no debates, so the list is an empty JSON array.
[ "$(curl -fsS "$base/api/debates")" = "[]" ] || fail "/api/debates should be [] on a fresh stack"
# Calling the admin route without the token must be refused with 401.
[ "$(status -X POST "$base/internal/run-daily")" = "401" ] || fail "run-daily without a token should be 401"

echo "4. WebSocket upgrades work through the router"
# Run an inline Python program (up to the PY line below), giving it the base address as its argument.
python3 - "$base" <<'PY'
# Async tools, JSON parsing, and command-line arguments.
import asyncio
import json
import sys

# A WebSocket client library.
import websockets


# Opens a WebSocket to the router and checks the first message.
async def main(base: str) -> None:
    # Change "http..." to "ws..." (https becomes wss) and add the WebSocket path.
    url = base.replace("http", "ws", 1) + "/ws/debate/latest"
    # Connect; the "async with" closes the connection automatically at the end.
    async with websockets.connect(url) as ws:
        # Wait up to 10 seconds for the first message and parse it.
        message = json.loads(await asyncio.wait_for(ws.recv(), 10))
    # No debate exists on a fresh stack, so the server must answer with its "not_found" error message.
    # Getting that message proves the WebSocket upgrade worked through the proxy.
    assert message.get("error") == "not_found", message


# Run the async function with the base address from the command line.
asyncio.run(main(sys.argv[1]))
PY

echo "5. per-client rate limiting survives the proxy chain (X-Forwarded-For is preserved)"
# Sends an opinion pretending to come from the client address given as the first argument; prints the status code.
hit() {  # no debate exists, so an allowed request is a 404; a rate-limited one is a 429
  status -X POST -H "X-Forwarded-For: $1" -H 'Content-Type: application/json' \
    -d '{"user_id":"ci","opinion":"hello"}' "$base/api/opinion/latest"
}
# The limit is 2 per client: the first two are allowed (404 because no debate exists).
[ "$(hit 203.0.113.9)" = "404" ] || fail "first request from client A should be allowed (404)"
[ "$(hit 203.0.113.9)" = "404" ] || fail "second request from client A should be allowed (404)"
# The third from the same client is blocked with 429.
[ "$(hit 203.0.113.9)" = "429" ] || fail "third request from client A should be rate limited (429)"
# A different client address starts with a fresh allowance.
[ "$(hit 203.0.113.10)" = "404" ] || fail "client B must not share client A's rate-limit bucket"

echo "all stack checks passed"

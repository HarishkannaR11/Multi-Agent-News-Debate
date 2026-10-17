#!/usr/bin/env bash
# Non-destructive check of the public site, run from your own computer (not on the server).
# It proves the pieces that only exist behind CloudFront work: HTTPS, the API, and WebSockets.
#   deploy/aws/check_site.sh https://dxxxxxxxxxxxx.cloudfront.net
# Needs curl, jq and python3 with the `websockets` package (pip install websockets).
# Unlike smoke_test.sh it creates nothing, so it is safe on a live site.

# Stop on the first error, on unset variables, and on failures inside pipelines.
set -euo pipefail

# The site address (without a trailing slash); stop with a usage message if it is missing.
base="${1:?usage: check_site.sh https://<your-cloudfront-domain>}"
base="${base%/}"
# Prints "FAIL: <message>" to the error stream and stops the script with an error code.
fail() { echo "FAIL: $*" >&2; exit 1; }
# Runs curl silently and prints only the HTTP status code; extra arguments are passed on to curl.
status() { curl -s -o /dev/null -w '%{http_code}' "$@"; }

echo "1. HTTPS works and the backend is ready"
curl -fsS --max-time 20 "$base/health/ready" | jq -e '.status == "ready"' >/dev/null || fail "backend is not ready"

echo "2. plain http redirects to https"
http_base="http://${base#https://}"
[ "$(status "$http_base/")" = "301" ] || [ "$(status "$http_base/")" = "302" ] || fail "http did not redirect to https"

echo "3. the website is served"
curl -fsS --max-time 20 "$base/" | grep -q "The Debate" || fail "home page does not contain the site title"

echo "4. the API answers with a JSON list, and the admin route is protected"
curl -fsS --max-time 20 "$base/api/debates" | jq -e 'type == "array"' >/dev/null || fail "/api/debates is not a JSON list"
[ "$(status -X POST "$base/internal/run-daily")" = "401" ] || fail "run-daily without a token should be 401"

echo "5. WebSockets work through CloudFront"
# Run an inline Python program (up to the PY line below), giving it the site address as its argument.
python3 - "$base" <<'PY'
# Async tools, JSON parsing, and command-line arguments.
import asyncio
import json
import sys

# A WebSocket client library.
import websockets


# Opens a secure WebSocket to the site and reads what the server sends.
async def main(base: str) -> None:
    # "https://host" becomes "wss://host/ws/debate/latest".
    url = base.replace("http", "ws", 1) + "/ws/debate/latest"
    async with websockets.connect(url) as ws:
        # The first message is either a debate stage or a "not_found" error (no debate generated yet).
        # Both prove the connection upgrade worked through CloudFront.
        message = json.loads(await asyncio.wait_for(ws.recv(), 15))
    assert message.get("status") == "debating" or message.get("error") == "not_found", message
    print("   first message:", message.get("status") or message.get("error"))


# Run the async function with the site address from the command line.
asyncio.run(main(sys.argv[1]))
PY

echo "all site checks passed"

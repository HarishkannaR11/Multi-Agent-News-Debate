from fastapi import HTTPException, Request  # HTTPException = error response; Request = the incoming HTTP request

from ..config import settings  # the shared app settings
from ..services.redis_service import rate_limit_allow  # counts requests in Redis and says if still allowed


# Works out which IP address the request really came from.
def client_ip(request: Request) -> str:
    # Only trust the X-Forwarded-For header if we are behind a proxy we control.
    if settings.TRUST_PROXY_HEADERS:
        # Split the header's comma-separated list of addresses into a clean list.
        hops = [h.strip() for h in request.headers.get("x-forwarded-for", "").split(",") if h.strip()]
        # Make sure the list is long enough to pick the entry we want.
        if len(hops) >= settings.TRUSTED_PROXY_HOPS:
            # Take the Nth entry from the RIGHT: entries further left can be faked by the client.
            return hops[-settings.TRUSTED_PROXY_HOPS]
    # Otherwise use the address of the connection itself (or "unknown" if there is none).
    return request.client.host if request.client else "unknown"


# FastAPI "dependency": runs before the opinion endpoint and rejects the request if the caller is over the limit.
async def enforce_opinion_rate_limit(request: Request) -> None:
    # First check this client's own limit (e.g. 10 requests per 60 seconds).
    allowed = await rate_limit_allow(
        f"opinion:{client_ip(request)}", settings.OPINION_RATE_LIMIT, settings.OPINION_RATE_WINDOW_SECONDS
    )
    # Over the limit: reply "429 Too Many Requests".
    if not allowed:
        raise HTTPException(status_code=429, detail="Too many requests. Try again shortly.")
    # Then check the site-wide hourly cap (0 means the cap is switched off).
    if settings.OPINION_GLOBAL_LIMIT_PER_HOUR and not await rate_limit_allow(
        "opinion:global", settings.OPINION_GLOBAL_LIMIT_PER_HOUR, 3600
    ):
        # Everyone combined is over the cap: reply "429" with a different message.
        raise HTTPException(status_code=429, detail="The debate agents are busy right now. Try again later.")

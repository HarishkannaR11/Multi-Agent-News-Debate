from fastapi import HTTPException, Request

from ..config import settings
from ..services.redis_service import rate_limit_allow


def client_ip(request: Request) -> str:
    if settings.TRUST_PROXY_HEADERS:
        hops = [h.strip() for h in request.headers.get("x-forwarded-for", "").split(",") if h.strip()]
        if len(hops) >= settings.TRUSTED_PROXY_HOPS:
            return hops[-settings.TRUSTED_PROXY_HOPS]
    return request.client.host if request.client else "unknown"


async def enforce_opinion_rate_limit(request: Request) -> None:
    allowed = await rate_limit_allow(
        f"opinion:{client_ip(request)}", settings.OPINION_RATE_LIMIT, settings.OPINION_RATE_WINDOW_SECONDS
    )
    if not allowed:
        raise HTTPException(status_code=429, detail="Too many requests. Try again shortly.")
    if settings.OPINION_GLOBAL_LIMIT_PER_HOUR and not await rate_limit_allow(
        "opinion:global", settings.OPINION_GLOBAL_LIMIT_PER_HOUR, 3600
    ):
        raise HTTPException(status_code=429, detail="The debate agents are busy right now. Try again later.")

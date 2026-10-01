import hmac

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Response

from ..config import settings
from ..scheduler import generate_debate
from ..services.redis_service import acquire_daily_lock
from ..timeutil import today_iso

router = APIRouter(prefix="/internal", tags=["admin"])


@router.post("/run-daily", status_code=202)
async def run_daily(
    background: BackgroundTasks, response: Response, force: bool = False, x_admin_token: str = Header(default="")
):
    """Generate today's debate. For EventBridge/cron or a manual kick-off.

    Idempotent: returns 200 'already_ran' if today's debate exists or is running,
    unless force=true.
    """
    if not settings.ADMIN_TOKEN:
        raise HTTPException(status_code=503, detail="Admin endpoint disabled (ADMIN_TOKEN not set)")
    if not hmac.compare_digest(x_admin_token.encode(), settings.ADMIN_TOKEN.encode()):
        raise HTTPException(status_code=401, detail="Invalid admin token")

    date = today_iso()
    if not force and not await acquire_daily_lock(date):
        response.status_code = 200
        return {"status": "already_ran", "date": date}
    background.add_task(generate_debate, date)
    return {"status": "accepted", "date": date}

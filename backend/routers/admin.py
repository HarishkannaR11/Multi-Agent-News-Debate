import hmac  # tools for secure comparison of secrets

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Response  # FastAPI building blocks

from ..config import settings  # the shared app settings
from ..scheduler import generate_debate  # the function that runs the debate workflow and saves it
from ..services.redis_service import acquire_daily_lock  # claims today's run (only one caller wins)
from ..timeutil import today_iso  # today's date as text

# A group of endpoints that all start with "/internal" and are labelled "admin" in the API docs.
router = APIRouter(prefix="/internal", tags=["admin"])


# POST /internal/run-daily : generate today's debate. 202 = "accepted, working on it".
@router.post("/run-daily", status_code=202)
async def run_daily(
    # Lets us run work after the response has been sent.
    background: BackgroundTasks,
    # Lets us change the response status code.
    response: Response,
    # ?force=true skips the "already ran today" check.
    force: bool = False,
    # The secret sent in the "X-Admin-Token" header (empty string if missing).
    x_admin_token: str = Header(default=""),
):
    """Generate today's debate. For EventBridge/cron or a manual kick-off.

    Idempotent: returns 200 'already_ran' if today's debate exists or is running,
    unless force=true.
    """
    # If no admin token is configured, the endpoint is switched off entirely.
    if not settings.ADMIN_TOKEN:
        raise HTTPException(status_code=503, detail="Admin endpoint disabled (ADMIN_TOKEN not set)")
    # Compare the sent token with the real one in constant time (so timing cannot leak the secret).
    if not hmac.compare_digest(x_admin_token.encode(), settings.ADMIN_TOKEN.encode()):
        raise HTTPException(status_code=401, detail="Invalid admin token")

    # Today's date as text.
    date = today_iso()
    # Unless forced, try to claim today's run; if someone already has it, report that and stop.
    if not force and not await acquire_daily_lock(date):
        # 200 (not 202) because nothing new was started.
        response.status_code = 200
        return {"status": "already_ran", "date": date}
    # Schedule the debate generation to run in the background after we reply.
    background.add_task(generate_debate, date)
    # Reply immediately: the caller does not wait for the 13 LLM calls.
    return {"status": "accepted", "date": date}

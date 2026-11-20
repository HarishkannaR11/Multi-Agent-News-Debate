import re  # checks the date in the address

from fastapi import APIRouter, HTTPException, Query  # FastAPI building blocks

from ..config import settings
from ..markets import pipeline, store

# Read-only endpoints for the daily market debate. Starting a run is admin-only (see routers/admin.py).
router = APIRouter(prefix="/api", tags=["markets"])

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
# How many daily points of each series the page needs (it draws small trend lines).
CHART_POINTS = 40


def _enabled() -> None:
    if not settings.MARKETS_ENABLED:
        raise HTTPException(status_code=503, detail="The Markets feature is switched off on this server.")


# GET /api/markets : the market days, newest first, as small summaries.
@router.get("/markets")
async def list_market_days(limit: int = Query(20, ge=1, le=60), offset: int = Query(0, ge=0)):
    _enabled()
    dates = await store.list_dates(limit, offset)
    return {"items": await store.summaries(dates), "total": await store.count(), "offset": offset, "limit": limit}


# GET /api/markets/{date} : one day in full. "latest" means the newest stored day.
@router.get("/markets/{date}")
async def get_market_day(date: str):
    _enabled()
    if date == "latest":
        found = await store.latest_date()
        if found is None:
            raise HTTPException(status_code=404, detail="No market day has been generated yet")
        date = found
    if not _DATE_RE.match(date):
        raise HTTPException(status_code=404, detail="Market day not found")
    record = await store.get(date)
    if record is None:
        raise HTTPException(status_code=404, detail="Market day not found")
    record = await pipeline.reconcile_stalled(record)
    # Trim the trend data to what the page draws; the full packet stays in Redis, fingerprinted.
    for series in record["packet"].get("series", {}).values():
        series["points"] = series["points"][-CHART_POINTS:]
    return record

from fastapi import APIRouter, HTTPException, Query  # endpoint group, error response, URL option

from ..services.redis_service import get_debate, list_debates, parse_debate_id, resolve_debate_id  # Redis helpers
from ..userdebate.pipeline import reconcile_stalled  # repairs a visitor debate whose job died

# A group of endpoints that all start with "/api" and are labelled "debates" in the API docs.
router = APIRouter(prefix="/api", tags=["debates"])


# GET /api/debates : list debate summaries.
@router.get("/debates")
# limit = how many to return (1-100, default 30); offset = how many to skip (for paging).
async def get_debates(limit: int = Query(30, ge=1, le=100), offset: int = Query(0, ge=0)):
    # Fetch that page of summaries from Redis and return it as JSON.
    return await list_debates(offset=offset, limit=limit)


# GET /api/debate/{debate_id} : return one full debate.
@router.get("/debate/{debate_id}")
async def get_debate_by_id(debate_id: str):
    """debate_id is '{date}:{slug}', a bare 'YYYY-MM-DD', or 'latest'."""
    # Turn the client's id ("latest", a date, or a full id) into a real stored id.
    resolved = await resolve_debate_id(debate_id)
    # Split the resolved id into (date, slug), if there is one.
    parsed = parse_debate_id(resolved) if resolved else None
    # Load the debate from Redis, if we have a valid id.
    debate = await get_debate(*parsed) if parsed else None
    # If anything was missing, reply with a 404 "not found" error.
    if not resolved or not debate:
        raise HTTPException(status_code=404, detail="Debate not found")
    # A visitor's debate that says "generating" but has no live job (server restarted) becomes retryable here.
    debate = await reconcile_stalled(resolved, debate)
    # Return the debate with its id added at the start.
    return {"id": resolved, **debate}

from fastapi import APIRouter, HTTPException, Query

from ..services.redis_service import get_debate, list_debates, parse_debate_id, resolve_debate_id

router = APIRouter(prefix="/api", tags=["debates"])


@router.get("/debates")
async def get_debates(limit: int = Query(30, ge=1, le=100), offset: int = Query(0, ge=0)):
    return await list_debates(offset=offset, limit=limit)


@router.get("/debate/{debate_id}")
async def get_debate_by_id(debate_id: str):
    """debate_id is '{date}:{slug}', a bare 'YYYY-MM-DD', or 'latest'."""
    resolved = await resolve_debate_id(debate_id)
    parsed = parse_debate_id(resolved) if resolved else None
    debate = await get_debate(*parsed) if parsed else None
    if not resolved or not debate:
        raise HTTPException(status_code=404, detail="Debate not found")
    return {"id": resolved, **debate}

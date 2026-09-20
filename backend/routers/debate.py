from fastapi import APIRouter, HTTPException

from ..services.redis_service import list_debates, get_debate

router = APIRouter(prefix="/api", tags=["debates"])


@router.get("/debates")
async def get_debates():
    return await list_debates()


@router.get("/debate/{debate_id}")
async def get_debate_by_id(debate_id: str):
    date, topic_slug = debate_id.split(":", 1)
    debate = await get_debate(date, topic_slug)
    if not debate:
        raise HTTPException(status_code=404, detail="Debate not found")
    return {"id": debate_id, **debate}

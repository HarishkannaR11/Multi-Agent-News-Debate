from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..graph.nodes.opinion import handle_opinion
from ..services.redis_service import append_opinion, get_debate

router = APIRouter(prefix="/api", tags=["opinion"])


class OpinionRequest(BaseModel):
    user_id: str
    opinion: str


@router.post("/opinion/{debate_id}")
async def submit_opinion(debate_id: str, body: OpinionRequest):
    date, topic_slug = debate_id.split(":", 1)
    debate = await get_debate(date, topic_slug)
    if not debate:
        raise HTTPException(status_code=404, detail="Debate not found")

    result = handle_opinion(debate, body.opinion)
    entry = {
        "user_opinion": body.opinion,
        "agent_response": result["response"],
        "followup": result["followup"],
        "mode": result["mode"],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    await append_opinion(date, topic_slug, body.user_id, entry)
    return entry

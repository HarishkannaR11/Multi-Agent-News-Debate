import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from ..config import settings
from ..graph.guardrails.common import GuardUnavailable
from ..graph.guardrails.input_guard import check_input
from ..graph.guardrails.output_guard import check_output
from ..graph.nodes.opinion import handle_opinion
from ..services.redis_service import (
    append_opinion,
    get_debate,
    get_opinions,
    parse_debate_id,
    resolve_debate_id,
)
from .deps import enforce_opinion_rate_limit

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["opinion"])

USER_ID_PATTERN = r"^[A-Za-z0-9_-]{1,64}$"


class OpinionRequest(BaseModel):
    user_id: str = Field(pattern=USER_ID_PATTERN)
    opinion: str = Field(min_length=1, max_length=settings.MAX_OPINION_CHARS)


async def _load(debate_id: str) -> tuple[str, str, str, dict]:
    resolved = await resolve_debate_id(debate_id)
    parsed = parse_debate_id(resolved) if resolved else None
    debate = await get_debate(*parsed) if parsed else None
    if not resolved or not parsed or not debate:
        raise HTTPException(status_code=404, detail="Debate not found")
    return resolved, parsed[0], parsed[1], debate


@router.post("/opinion/{debate_id}", dependencies=[Depends(enforce_opinion_rate_limit)])
async def submit_opinion(debate_id: str, body: OpinionRequest):
    _, date, topic_slug, debate = await _load(debate_id)
    opinion = body.opinion.strip()
    if not opinion:
        raise HTTPException(status_code=422, detail="Opinion is empty")

    try:
        screened = await run_in_threadpool(check_input, opinion)
        if not screened.passed:
            raise HTTPException(status_code=422, detail="Your opinion was rejected by the content filter.")

        try:
            result = await run_in_threadpool(handle_opinion, debate, screened.text)
        except Exception:
            # Raise an HTTPException rather than letting a 500 escape: an unhandled 500 is
            # generated outside the CORS middleware, so a cross-origin browser sees a
            # network error instead of this message.
            logger.exception("Opinion LLM call failed")
            raise HTTPException(
                status_code=502, detail="The debate agents are unavailable. Try again later."
            ) from None
        reply = await run_in_threadpool(check_output, result["response"])
        if not reply.passed:
            raise HTTPException(
                status_code=502, detail="The response was blocked by the content filter. Try rephrasing."
            )
    except GuardUnavailable as exc:
        raise HTTPException(status_code=503, detail="Content filter unavailable. Try again later.") from exc

    entry = {
        "user_opinion": opinion,
        "agent_response": reply.text,
        "followup": result["followup"],
        "mode": result["mode"],
        "timestamp": datetime.now(UTC).isoformat(),
    }
    await append_opinion(date, topic_slug, body.user_id, entry)
    return entry


@router.get("/opinions/{debate_id}")
async def list_user_opinions(debate_id: str, user_id: str = Query(pattern=USER_ID_PATTERN)):
    _, date, topic_slug, _ = await _load(debate_id)
    return await get_opinions(date, topic_slug, user_id)

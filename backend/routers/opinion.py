import logging  # Python's built-in logging system
from datetime import UTC, datetime  # date/time class and the UTC timezone

from fastapi import APIRouter, Depends, HTTPException, Query  # FastAPI building blocks
from pydantic import BaseModel, Field  # BaseModel validates incoming JSON; Field adds rules to a field
from starlette.concurrency import run_in_threadpool  # runs slow blocking code in a worker thread

from ..config import settings  # the shared app settings
from ..graph.guardrails.common import GuardUnavailable  # error meaning "the content filter is broken"
from ..graph.guardrails.input_guard import check_input  # content filter for incoming text
from ..graph.guardrails.output_guard import check_output  # content filter for text the AI wrote
from ..graph.nodes.opinion import handle_opinion  # asks the LLM to respond to the user's opinion
from ..services.redis_service import (  # Redis helpers
    append_opinion,  # save an opinion
    get_debate,  # load a debate
    get_opinions,  # load a user's saved opinions
    parse_debate_id,  # split "date:slug" into parts
    resolve_debate_id,  # turn "latest"/a date/a full id into a real id
)
from .deps import enforce_opinion_rate_limit  # the rate-limit check

# A logger named after this module.
logger = logging.getLogger(__name__)

# A group of endpoints that all start with "/api" and are labelled "opinion" in the API docs.
router = APIRouter(prefix="/api", tags=["opinion"])

# A user id may contain only letters, digits, "_" and "-", and be 1 to 64 characters long.
USER_ID_PATTERN = r"^[A-Za-z0-9_-]{1,64}$"


# The shape (and rules) of the JSON a client must send when submitting an opinion.
class OpinionRequest(BaseModel):
    # Must match the pattern above.
    user_id: str = Field(pattern=USER_ID_PATTERN)
    # Must be 1 to MAX_OPINION_CHARS characters.
    opinion: str = Field(min_length=1, max_length=settings.MAX_OPINION_CHARS)


# Finds a debate from an id, or replies with a 404 error. Returns (resolved id, date, slug, debate).
async def _load(debate_id: str) -> tuple[str, str, str, dict]:
    # Turn the client's id ("latest", a date, or a full id) into a real stored id.
    resolved = await resolve_debate_id(debate_id)
    # Split it into (date, slug), if there is one.
    parsed = parse_debate_id(resolved) if resolved else None
    # Load the debate from Redis, if we have a valid id.
    debate = await get_debate(*parsed) if parsed else None
    # Anything missing means "not found".
    if not resolved or not parsed or not debate:
        raise HTTPException(status_code=404, detail="Debate not found")
    # Return everything the caller needs.
    return resolved, parsed[0], parsed[1], debate


# POST /api/opinion/{debate_id} : the rate-limit check runs first (dependencies=...).
@router.post("/opinion/{debate_id}", dependencies=[Depends(enforce_opinion_rate_limit)])
async def submit_opinion(debate_id: str, body: OpinionRequest):
    # Load the debate (404 if missing); we only need its date, slug and content.
    _, date, topic_slug, debate = await _load(debate_id)
    # Trim spaces from the opinion.
    opinion = body.opinion.strip()
    # An opinion that is only spaces is not allowed.
    if not opinion:
        raise HTTPException(status_code=422, detail="Opinion is empty")

    # Wrap the steps below so a broken content filter can be turned into a clean 503.
    try:
        # Check the user's text with the content filter, in a worker thread so the server stays responsive.
        screened = await run_in_threadpool(check_input, opinion)
        # Blocked: reply "422 Unprocessable".
        if not screened.passed:
            raise HTTPException(status_code=422, detail="Your opinion was rejected by the content filter.")

        # Inner try: turn any LLM failure into a clean error message.
        try:
            # Ask the LLM to respond (in a worker thread because the call blocks).
            result = await run_in_threadpool(handle_opinion, debate, screened.text)
        # The LLM call failed for any reason.
        except Exception:
            # Raise an HTTPException rather than letting a 500 escape: an unhandled 500 is
            # generated outside the CORS middleware, so a cross-origin browser sees a
            # network error instead of this message.
            # Record the full error for the operator.
            logger.exception("Opinion LLM call failed")
            # Reply "502 Bad Gateway" with a friendly message ("from None" hides the internal error chain).
            raise HTTPException(
                status_code=502, detail="The debate agents are unavailable. Try again later."
            ) from None
        # Check the AI's reply with the output content filter (also in a worker thread).
        reply = await run_in_threadpool(check_output, result["response"])
        # Blocked: reply "502" with a hint to rephrase.
        if not reply.passed:
            raise HTTPException(
                status_code=502, detail="The response was blocked by the content filter. Try rephrasing."
            )
    # The content filter itself could not run: fail closed with "503 Service Unavailable".
    except GuardUnavailable as exc:
        raise HTTPException(status_code=503, detail="Content filter unavailable. Try again later.") from exc

    # The record we save and return.
    entry = {
        # What the user wrote.
        "user_opinion": opinion,
        # The AI's reply (with personal data redacted by the filter).
        "agent_response": reply.text,
        # The follow-up question.
        "followup": result["followup"],
        # AGREE, CHALLENGE or EXPAND.
        "mode": result["mode"],
        # When this happened, in UTC.
        "timestamp": datetime.now(UTC).isoformat(),
    }
    # Save it to Redis under this user's list for this debate.
    await append_opinion(date, topic_slug, body.user_id, entry)
    # Send it back to the browser.
    return entry


# GET /api/opinions/{debate_id}?user_id=... : a user's earlier opinions on a debate.
@router.get("/opinions/{debate_id}")
async def list_user_opinions(debate_id: str, user_id: str = Query(pattern=USER_ID_PATTERN)):
    # Load the debate to get its date and slug (404 if missing).
    _, date, topic_slug, _ = await _load(debate_id)
    # Return that user's saved opinions.
    return await get_opinions(date, topic_slug, user_id)

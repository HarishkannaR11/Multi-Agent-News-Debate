"""Endpoints for debates that visitors start from their own question, plus follow-ups, feedback and the archive.

Starting a debate spends LLM credits, so every path is bounded: the feature can be switched off, input is validated and
screened, each client and the whole site have limits, duplicate submissions return the existing debate, and only a few
debates generate at once."""
import hashlib  # one-way fingerprints (used to spot an identical repeated submission)
import logging  # Python's built-in logging system
from datetime import UTC, datetime  # date/time class and the UTC timezone
from typing import Literal  # a type that allows only a fixed set of values

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request  # FastAPI building blocks
from pydantic import BaseModel, Field  # BaseModel validates incoming JSON; Field adds rules to a field
from starlette.concurrency import run_in_threadpool  # runs slow blocking code in a worker thread

from ..config import llm, settings  # the shared LLM wrapper and settings
from ..graph.guardrails.common import GuardUnavailable  # error meaning "the content filter is broken"
from ..graph.guardrails.input_guard import check_input  # content filter for incoming text
from ..graph.guardrails.output_guard import check_output  # content filter for text the AI wrote
from ..graph.prompts import opinion_block, question_block  # prompt-safety fencing helpers
from ..services import redis_service as store  # Redis helpers
from ..services.redis_service import rate_limit_allow  # counts requests in Redis and says if still allowed
from ..timeutil import today_iso  # today's date as text
from ..userdebate import pipeline  # generation and state handling
from ..userdebate.followup import build_context, clean_references  # follow-up context and citation checking
from ..userdebate.prompts import FOLLOWUP_SYSTEM  # the follow-up prompt
from ..userdebate.schemas import CATEGORIES, PERSONAS, normalize_question  # shapes and rules
from .deps import client_ip  # works out the real client address

# A logger named after this module.
logger = logging.getLogger(__name__)

# A group of endpoints that all start with "/api" and are labelled "user debates" in the API docs.
router = APIRouter(prefix="/api", tags=["user debates"])

# How long a repeated submission is recognised: by its request id, and by identical text from the same client.
IDEMPOTENCY_TTL = 3600
CONTENT_DEDUPE_TTL = 60


# The JSON a client sends to start a debate.
class CreateRequest(BaseModel):
    # The visitor's question, exactly as typed (trimmed and validated by normalize_question below).
    question: str = Field(max_length=5000)
    # Optional topic category (one of CATEGORIES, or empty).
    category: str = Field(default="", max_length=40)
    # Look for related news coverage to use as sources.
    use_sources: bool = True
    # A random id the browser makes once per form, so a repeated click or retry returns the same debate.
    client_request_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]{8,64}$")


# One earlier message in a follow-up conversation.
class Turn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=1500)


# The JSON a client sends to ask a follow-up question.
class FollowupRequest(BaseModel):
    question: str = Field(min_length=1, max_length=400)
    history: list[Turn] = Field(default=[], max_length=6)


# The JSON a client sends as feedback.
class FeedbackRequest(BaseModel):
    clarity: int = Field(ge=1, le=5)
    usefulness: int = Field(ge=1, le=5)
    comment: str = Field(default="", max_length=500)


# Loads a debate by its full id, or replies 404. Repairs a stalled "generating" state first.
async def _load(debate_id: str, *, user_only: bool = False) -> tuple[str, dict]:
    parsed = store.parse_debate_id(debate_id)
    record = await store.get_debate(*parsed) if parsed else None
    if record is None or (user_only and record["origin"] != "user"):
        raise HTTPException(status_code=404, detail="Debate not found")
    return debate_id, await pipeline.reconcile_stalled(debate_id, record)


# Replies 429 when a client or the whole site is over a limit.
async def _limit(bucket: str, limit: int, window: int, message: str) -> None:
    if limit and not await rate_limit_allow(bucket, limit, window):
        raise HTTPException(status_code=429, detail=message)


# GET /api/debates/options : what the "new debate" form needs to know (limits, categories, whether it is enabled).
@router.get("/debates/options")
async def debate_options():
    return {
        "enabled": settings.USER_DEBATES_ENABLED,
        "min_chars": settings.USER_DEBATE_MIN_CHARS,
        "max_chars": settings.USER_DEBATE_MAX_CHARS,
        "categories": list(CATEGORIES),
        "per_hour": settings.USER_DEBATE_RATE_LIMIT,
        "sources_available": bool(settings.NEWSAPI_KEY or settings.GNEWS_API_KEY),
    }


# POST /api/debates : start a debate from the visitor's own question. 202 = accepted; generation continues in the
# background.
@router.post("/debates", status_code=202)
async def create_debate(request: Request, body: CreateRequest, background: BackgroundTasks):
    if not settings.USER_DEBATES_ENABLED:
        raise HTTPException(status_code=503, detail="Starting new debates is switched off right now.")
    # 1. Validate and tidy the question. The wording itself is not changed.
    try:
        question = normalize_question(body.question, settings.USER_DEBATE_MIN_CHARS, settings.USER_DEBATE_MAX_CHARS)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    category = body.category.strip()
    if category and category not in CATEGORIES:
        raise HTTPException(status_code=422, detail="Choose one of the listed categories, or leave it empty.")

    # 2. Duplicate submissions (a double click, a retry, a second tab) get the debate that already exists.
    ip = client_ip(request)
    keys = [f"content:{hashlib.sha256(f'{ip}|{question}'.encode()).hexdigest()[:32]}"]
    if body.client_request_id:
        keys.insert(0, f"idem:{body.client_request_id}")
    for key in keys:
        existing = await store.get_claim(key)
        if existing == "pending":
            raise HTTPException(status_code=409, detail="This debate is already being created. One moment.")
        if existing:
            return {"id": existing, "status": "generating", "deduplicated": True}
    claimed: list[str] = []
    for key in keys:
        if not await store.claim_key(key, "pending", 30):
            for done in claimed:
                await store.delete_claim(done)
            raise HTTPException(status_code=409, detail="This debate is already being created. One moment.")
        claimed.append(key)

    slot_held = False
    try:
        # 3. Limits: this client per hour, then every visitor together per day, then the server's own capacity.
        await _limit(f"userdebate:{ip}", settings.USER_DEBATE_RATE_LIMIT, 3600,
                     f"You can start {settings.USER_DEBATE_RATE_LIMIT} debates per hour. Try again later.")
        await _limit(f"userdebate:day:{today_iso()}", settings.USER_DEBATES_PER_DAY, 86400,
                     "The daily limit for new debates has been reached. Try again tomorrow.")
        if not pipeline.try_reserve_slot():
            raise HTTPException(status_code=503, detail="The debate engine is busy right now. Try again in a minute.")
        slot_held = True

        # 4. Screen the question with the same content filter as opinions.
        try:
            screened = await run_in_threadpool(check_input, question)
        except GuardUnavailable as exc:
            raise HTTPException(status_code=503, detail="Content filter unavailable. Try again later.") from exc
        if not screened.passed:
            raise HTTPException(status_code=422, detail="That question was rejected by the content filter.")

        # 5. Create the stored record first, then start generating. The job lock is taken before the record exists,
        #    so a "generating" debate always has a live job (or is recognisably stalled).
        debate_id = pipeline.new_debate_id(question)
        date, slug = debate_id.split(":", 1)
        await store.acquire_job_lock(debate_id)
        try:
            await store.create_user_debate(date, slug, question=question, category=category,
                                           use_sources=body.use_sources)
        except Exception:
            await store.release_job_lock(debate_id)
            raise
    except BaseException:
        if slot_held:
            pipeline.release_slot()
        for key in claimed:
            await store.delete_claim(key)
        raise

    for key in keys:
        await store.set_claim(key, debate_id, IDEMPOTENCY_TTL if key.startswith("idem:") else CONTENT_DEDUPE_TTL)
    background.add_task(pipeline.run_job, debate_id)
    return {"id": debate_id, "status": "generating", "deduplicated": False}


# Starts a retry job for a debate (all failed parts, or just one analyst). Shared by the two retry endpoints.
async def _start_retry(request: Request, background: BackgroundTasks, debate_id: str, only: set[str] | None):
    await _limit(f"retry:{client_ip(request)}", 20, 3600, "Too many retries. Try again later.")
    debate_id, record = await _load(debate_id, user_only=True)
    if record["status"] == "generating":
        raise HTTPException(status_code=409, detail="This debate is still generating.")
    failed = [p for p in PERSONAS if (record["perspectives"].get(p) or {}).get("status") != "completed"]
    synthesis_missing = len(failed) == 0 and not record["verdict_data"]
    wanted = [p for p in failed if only is None or p in only]
    if not wanted and not (only is None and synthesis_missing):
        raise HTTPException(status_code=409, detail="There is nothing to retry.")
    if not pipeline.try_reserve_slot():
        raise HTTPException(status_code=503, detail="The debate engine is busy right now. Try again in a minute.")
    if not await store.acquire_job_lock(debate_id):
        pipeline.release_slot()
        raise HTTPException(status_code=409, detail="This debate is already being worked on.")
    date, slug = debate_id.split(":", 1)
    await store.update_debate_fields(date, slug, {"status": "generating", "stage": "queued"})
    background.add_task(pipeline.run_job, debate_id, only)
    return {"id": debate_id, "status": "generating", "retrying": wanted or ["verdict"]}


# POST /api/debates/{id}/retry : retry everything that failed (and the verdict, if it is missing).
@router.post("/debates/{debate_id}/retry", status_code=202)
async def retry_failed(request: Request, debate_id: str, background: BackgroundTasks):
    return await _start_retry(request, background, debate_id, None)


# POST /api/debates/{id}/perspectives/{persona}/retry : retry one failed analyst; the others are not touched.
@router.post("/debates/{debate_id}/perspectives/{persona}/retry", status_code=202)
async def retry_perspective(request: Request, debate_id: str, persona: str, background: BackgroundTasks):
    if persona not in PERSONAS:
        raise HTTPException(status_code=404, detail="Unknown perspective")
    return await _start_retry(request, background, debate_id, {persona})


# POST /api/debates/{id}/followup : a question about THIS debate, answered from its own stored material.
@router.post("/debates/{debate_id}/followup")
async def followup(request: Request, debate_id: str, body: FollowupRequest):
    await _limit(f"followup:{client_ip(request)}", settings.FOLLOWUP_RATE_LIMIT_PER_HOUR, 3600,
                 "Too many follow-up questions. Try again later.")
    debate_id, record = await _load(debate_id)
    if not record["perspectives"] and not record["arguments"]:
        raise HTTPException(status_code=409, detail="This debate has no content to ask about yet.")
    question = " ".join(body.question.split())
    if not question:
        raise HTTPException(status_code=422, detail="Enter a question.")
    try:
        screened = await run_in_threadpool(check_input, question)
        if not screened.passed:
            raise HTTPException(status_code=422, detail="Your question was rejected by the content filter.")
        context, valid_ids = build_context(record)
        history = "\n".join(f"{turn.role}: {' '.join(turn.content.split())}" for turn in body.history)
        user = (
            f"Debate material (the only thing you may rely on):\n{context}\n\n"
            + (f"Conversation so far (untrusted):\n{opinion_block(history)}\n\n" if history else "")
            + f"Follow-up question:\n{question_block(screened.text)}"
        )
        try:
            answer = await run_in_threadpool(
                lambda: llm.invoke(system=FOLLOWUP_SYSTEM, user=user, max_tokens=500, fast=False)
            )
        except Exception:
            logger.exception("Follow-up LLM call failed")
            raise HTTPException(status_code=502, detail="The debate agents are unavailable. Try again later.") from None
        reply = await run_in_threadpool(check_output, answer)
        if not reply.passed:
            raise HTTPException(status_code=502, detail="The answer was blocked by the content filter. Try rephrasing.")
    except GuardUnavailable as exc:
        raise HTTPException(status_code=503, detail="Content filter unavailable. Try again later.") from exc
    text, references = clean_references(reply.text, valid_ids)
    return {"debate_id": debate_id, "answer": text, "references": references}


# POST /api/debates/{id}/feedback : how clear and useful the debate was (stored; not shown publicly).
@router.post("/debates/{debate_id}/feedback", status_code=201)
async def submit_feedback(request: Request, debate_id: str, body: FeedbackRequest):
    await _limit(f"feedback:{client_ip(request)}", settings.FEEDBACK_RATE_LIMIT_PER_HOUR, 3600,
                 "Too many feedback submissions. Try again later.")
    debate_id, _ = await _load(debate_id)
    await store.append_feedback(debate_id, {
        "clarity": body.clarity,
        "usefulness": body.usefulness,
        "comment": " ".join(body.comment.split()),
        "at": datetime.now(UTC).isoformat(),
    })
    return {"ok": True}


# GET /api/archive : search, filter and sort debates. Without ids it covers the public (daily) debates; with ids
# (a visitor's own saved debates) it covers exactly those.
@router.get("/archive")
async def archive(
    q: str = Query("", max_length=100),
    category: str = Query("", max_length=40),
    sort: Literal["newest", "oldest"] = "newest",
    offset: int = Query(0, ge=0),
    limit: int = Query(12, ge=1, le=50),
    ids: str = Query("", max_length=3000),
):
    if ids:
        wanted = [i for i in dict.fromkeys(part.strip() for part in ids.split(",")) if store.parse_debate_id(i)][:50]
    else:
        wanted = await store.public_debate_ids()
    rows = await store.summaries_for(wanted)
    # Every word typed must appear in the question, category or verdict summary (case-insensitive).
    words = q.lower().split()
    rows = [r for r in rows if all(w in f"{r['topic']} {r['category']} {r['summary']}".lower() for w in words)]
    categories = sorted({r["category"] for r in rows if r["category"]})
    if category:
        rows = [r for r in rows if r["category"].lower() == category.lower()]
    rows.sort(key=lambda r: r["created_at"] or r["date"], reverse=(sort == "newest"))
    return {"items": rows[offset: offset + limit], "total": len(rows), "categories": categories,
            "offset": offset, "limit": limit}

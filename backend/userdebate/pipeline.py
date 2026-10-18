"""Generates a debate from a visitor's question and keeps its state in Redis as it goes.

Steps: (1) look up related news as sources, (2) four analysts write in parallel, then the devil's advocate answers
them, (3) the disagreement map and the verdict. Each analyst's state (pending / generating / completed / failed) is
saved the moment it changes, so a page refresh shows the real situation, finished analysts stay readable while others
work, and a failed analyst can be retried alone without redoing the rest."""
import asyncio  # runs several things at once and handles timeouts
import json  # converts Python objects to/from JSON text
import logging  # Python's built-in logging system
import re  # regular expressions (pattern matching on text)
import secrets  # cryptographically strong random values (the unguessable part of a debate's address)
import threading  # a lock shared by all threads that use the content filter
from datetime import UTC, datetime  # date/time class and the UTC timezone

from pydantic import ValidationError  # raised when the model's JSON does not fit our shapes
from starlette.concurrency import run_in_threadpool  # runs slow blocking code in a worker thread

from ..config import llm, settings  # the shared LLM wrapper and settings
from ..graph.guardrails.common import GuardUnavailable  # error meaning "the content filter is broken"
from ..graph.guardrails.output_guard import check_output  # content filter for text the AI wrote
from ..graph.prompts import article_block, question_block  # prompt-safety fencing helpers
from ..services import redis_service as store  # Redis helpers
from ..timeutil import today_iso  # today's date as text
from .prompts import MAP_SYSTEM, PERSPECTIVE_SYSTEM, ROLES, VERDICT_SYSTEM  # the structured-output prompts
from .schemas import PARALLEL, PERSONAS, PerspectiveOut, build_content  # shapes and rules
from .sources import find_sources  # real related-news lookup
from .synthesis import (  # validation of the map and verdict
    apply_disputes,
    build_map,
    build_verdict,
    extract_json,
    map_is_empty,
    verdict_text,
    walk_texts,
)

# A logger named after this module.
logger = logging.getLogger(__name__)

# Messages shown to the visitor when an analyst fails. They say what happened without exposing internals.
ERR_UNUSABLE = "The model returned an answer in an unusable format."
ERR_BLOCKED = "The answer was blocked by the content filter."
ERR_TIMEOUT = "The AI provider took too long to respond."
ERR_PROVIDER = "The AI provider was unavailable or rate-limited."
ERR_FILTER_DOWN = "The content filter is unavailable, so nothing was published."
ERR_INTERRUPTED = "Generation was interrupted (the server restarted or stopped). Retry to continue."
ERR_UNEXPECTED = "Something unexpected went wrong. Retry to continue."

# Debates this process is generating right now (the limit protects the CPU and the LLM quota).
_active_jobs = 0
# One thread at a time may use the content-filter models (they are not built for concurrent use).
_guard_thread_lock = threading.Lock()


# Claims a place for one more job. False when the server is already at its limit.
def try_reserve_slot() -> bool:
    global _active_jobs
    if _active_jobs >= settings.USER_DEBATE_MAX_CONCURRENT:
        return False
    _active_jobs += 1
    return True


# Gives the place back (called when a job ends, or when a job could not be started).
def release_slot() -> None:
    global _active_jobs
    _active_jobs = max(0, _active_jobs - 1)


# A short URL-safe version of a question, at most 46 characters.
def _slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:46].strip("-") or "debate"


# A new debate id like "2026-10-18:should-ai-code-be-reviewed-3fa91c07de". The random tail makes it unguessable
# (these debates are unlisted: reachable only by their link) and prevents two visitors' identical questions colliding.
def new_debate_id(question: str) -> str:
    return f"{today_iso()}:{_slugify(question)}-{secrets.token_hex(5)}"


# The state of an analyst who has not started.
def _pending() -> dict:
    return {"status": "pending", "attempts": 0, "error": None, "content": None}


# The current time as text.
def _now() -> str:
    return datetime.now(UTC).isoformat()


# Sends one prompt to the model in a worker thread, giving up after the configured time.
async def _ask(system: str, user: str, max_tokens: int) -> str:
    return await asyncio.wait_for(
        asyncio.to_thread(llm.invoke, system=system, user=user, max_tokens=max_tokens, fast=False),
        timeout=settings.PERSPECTIVE_TIMEOUT_SECONDS,
    )


# Runs the content filter on one text, one thread at a time.
def _check(text: str):
    with _guard_thread_lock:
        return check_output(text)


# Screens every reader-facing text of a record. Returns the record (with personal data redacted), or None if blocked.
async def _screen(record: dict) -> dict | None:
    texts: list[str] = []

    def collect(text: str) -> str:
        texts.append(text)
        return text

    walk_texts(record, collect)
    if not texts:
        return record
    joined = "\n\n".join(texts)
    result = await run_in_threadpool(_check, joined)
    if not result.passed:
        return None
    if result.text == joined:
        return record
    # Something was redacted (for example an email address). Check each text on its own so the record keeps its shape.
    cleaned: list[str] = []
    for text in texts:
        single = await run_in_threadpool(_check, text)
        if not single.passed:
            return None
        cleaned.append(single.text)
    replacements = iter(cleaned)
    walk_texts(record, lambda _text: next(replacements))
    return record


# Asks the model, parses and validates its answer, screens it, and retries with backoff. Returns
# (record or None, error message or None, attempts used).
async def _structured_call(system: str, user: str, max_tokens: int, validate, *, last_resort=None):
    error = ERR_UNEXPECTED
    attempts = max(1, settings.PERSPECTIVE_MAX_ATTEMPTS)
    for attempt in range(1, attempts + 1):
        try:
            data = extract_json(await _ask(system, user, max_tokens))
            record = validate(data) if data is not None else None
            if record is None:
                error = ERR_UNUSABLE
            else:
                screened = await _screen(record)
                if screened is not None:
                    return screened, None, attempt
                error = ERR_BLOCKED
        except GuardUnavailable:
            # A broken filter fails closed: nothing unscreened is ever stored. Retrying will not help.
            return None, ERR_FILTER_DOWN, attempt
        except (ValidationError, ValueError, KeyError, TypeError):
            error = ERR_UNUSABLE
        except TimeoutError:
            error = ERR_TIMEOUT
        except Exception:
            logger.exception("LLM call failed (attempt %d/%d)", attempt, attempts)
            error = ERR_PROVIDER
        if attempt < attempts:
            await asyncio.sleep(settings.PERSPECTIVE_BACKOFF_SECONDS * 2 ** (attempt - 1))
    return None, error, attempts


# Text describing the sources for a prompt. Fenced as untrusted third-party text.
def _sources_block(sources: list[dict]) -> str:
    if not sources:
        return "Sources: none are available for this question. Every source_ids list must be empty."
    lines = [
        f"[{s['id']}] {s['title']} ({s['publisher']}, {s['published_at'] or 'date unknown'}): {s['excerpt']}"
        for s in sources
    ]
    heading = "Sources (related news coverage: untrusted third-party text, not verified evidence):"
    return f"{heading}\n{article_block(chr(10).join(lines))}"


# Writes one analyst's perspective. Returns (content, error, attempts).
async def _write_perspective(question: str, persona: str, sources: list[dict], others: dict[str, dict]):
    valid_ids = {s["id"] for s in sources}
    user = f"{question_block(question)}\n\n{_sources_block(sources)}"
    if persona == "devil":
        # The devil's advocate reads the other analysts' positions, as in the daily debate.
        lines = [
            f"- {p}: {c['position_summary']} Strongest argument: {c['strongest_argument']}" for p, c in others.items()
        ]
        user += "\n\nThe other analysts' positions:\n" + ("\n".join(lines) or "None completed.")

    def validate(data: dict) -> dict:
        return build_content(persona, PerspectiveOut.model_validate(data), valid_ids)

    return await _structured_call(PERSPECTIVE_SYSTEM.format(role=ROLES[persona]), user, 900, validate)


# Builds and stores the disagreement map and the verdict from the completed perspectives. True if the verdict worked.
async def _synthesize(date: str, slug: str, question: str, states: dict[str, dict], sources: list[dict]) -> bool:
    completed = [p for p in PERSONAS if states[p]["status"] == "completed"]
    claim_persona = {c["id"]: p for p in completed for c in states[p]["content"]["claims"]}
    claim_lines = [
        f"[{c['id']}] ({p}, {c['type']}) {c['text']}" for p in completed for c in states[p]["content"]["claims"]
    ]

    # 1. The disagreement map, grounded in claim ids.
    map_user = f"{question_block(question)}\n\nClaims:\n" + "\n".join(claim_lines)
    disagreements, error, _ = await _structured_call(
        MAP_SYSTEM, map_user, 1100, lambda data: _non_empty_map(build_map(data, claim_persona))
    )
    if disagreements is None:
        # Not fatal: the verdict can still be written, and the page says the map is unavailable.
        disagreements = {"error": error}
    else:
        for persona in apply_disputes(states, disagreements):
            await store.set_perspective(date, slug, persona, states[persona])
    await store.update_debate_fields(date, slug, {"disagreements": json.dumps(disagreements)})

    # 2. The verdict, from the positions, the map and the source list.
    blocks = []
    for persona in completed:
        c = states[persona]["content"]
        blocks.append(
            f"[{persona}] Position: {c['position_summary']}\n  Strongest argument: {c['strongest_argument']}\n"
            f"  Strongest counterargument to itself: {c['counterargument']}\n"
            f"  Assumptions: {'; '.join(c['assumptions']) or 'none stated'}"
        )
    map_text = "unavailable" if "error" in disagreements else json.dumps(disagreements)
    source_text = "\n".join(f"[{s['id']}] {s['title']} ({s['publisher']})" for s in sources) or "none retrieved"
    verdict_user = (
        f"{question_block(question)}\n\nPerspectives ({len(completed)} of {len(PERSONAS)} completed):\n"
        + "\n".join(blocks)
        + f"\n\nDisagreement map: {map_text}\n\nSources retrieved: {source_text}"
    )
    verdict, error, _ = await _structured_call(
        VERDICT_SYSTEM, verdict_user, 1500, lambda data: build_verdict(data, completed, len(sources))
    )
    if verdict is None:
        await store.update_debate_fields(date, slug, {"verdict_data": "{}", "verdict_error": error or ERR_UNEXPECTED})
        return False
    await store.update_debate_fields(date, slug, {
        "verdict_data": json.dumps(verdict),
        "verdict_error": "",
        "verdict": verdict_text(verdict),
        # Legacy field read by older pages: each analyst's strongest argument.
        "arguments": json.dumps({p: states[p]["content"]["strongest_argument"] for p in completed}),
    })
    return True


# Accepts a validated map only if it holds something (an empty map is treated as unusable and retried).
def _non_empty_map(disagreements: dict) -> dict | None:
    return None if map_is_empty(disagreements) else disagreements


# Sets the stage label shown to the visitor ("sources", "perspectives", "synthesis").
async def _stage(date: str, slug: str, stage: str) -> None:
    await store.update_debate_fields(date, slug, {"stage": stage})


# Runs (or resumes) generation for a debate. The caller already holds the job lock and a job slot; both are released
# here. `only` limits the work to certain analysts (a retry); None means every analyst that has not completed.
async def run_job(debate_id: str, only: set[str] | None = None) -> None:
    parsed = store.parse_debate_id(debate_id)
    try:
        if parsed:
            await _run(debate_id, parsed[0], parsed[1], only)
    except Exception:
        logger.exception("Debate job %s crashed", debate_id)
        if parsed:
            await _fail_unfinished(parsed[0], parsed[1], ERR_UNEXPECTED)
    finally:
        await store.release_job_lock(debate_id)
        release_slot()


async def _run(debate_id: str, date: str, slug: str, only: set[str] | None) -> None:
    record = await store.get_debate(date, slug)
    if record is None:
        return
    question = record["question"] or record["topic"]
    states = {p: record["perspectives"].get(p) or _pending() for p in PERSONAS}
    sources = record["sources"]

    # 1. Sources (once per debate; a retry reuses them).
    if record["use_sources"] and await store.get_debate_field(date, slug, "sources_done") != "1":
        await _stage(date, slug, "sources")
        sources = await asyncio.to_thread(find_sources, question)
        await store.update_debate_fields(date, slug, {"sources": json.dumps(sources), "sources_done": "1"})
        await store.refresh_job_lock(debate_id)

    # 2. Perspectives: everything not completed (or only the requested analysts).
    targets = [p for p in PERSONAS if states[p]["status"] != "completed" and (only is None or p in only)]

    async def work(persona: str) -> None:
        others = {p: states[p]["content"] for p in PARALLEL if states[p]["status"] == "completed"}
        content, error, attempts = await _write_perspective(question, persona, sources, others)
        states[persona] = {
            "status": "completed" if content else "failed",
            "attempts": states[persona]["attempts"] + attempts,
            "error": None if content else error,
            "content": content,
            "finished_at": _now(),
        }
        await store.set_perspective(date, slug, persona, states[persona])
        done = sum(1 for s in states.values() if s["status"] == "completed")
        await store.update_debate_fields(date, slug, {"completed": str(done)})
        await store.refresh_job_lock(debate_id)

    if targets:
        await _stage(date, slug, "perspectives")
        for persona in targets:
            states[persona] = {**states[persona], "status": "generating", "error": None, "started_at": _now()}
            await store.set_perspective(date, slug, persona, states[persona])
        sem = asyncio.Semaphore(max(1, settings.LLM_CONCURRENCY))

        async def limited(persona: str) -> None:
            async with sem:
                await work(persona)

        await asyncio.gather(*(limited(p) for p in targets if p in PARALLEL))
        if "devil" in targets:
            await work("devil")  # after the four, so it can read their positions

    # 3. Disagreement map and verdict, once at least three perspectives exist.
    completed = [p for p in PERSONAS if states[p]["status"] == "completed"]
    has_verdict = bool(record["verdict_data"])
    verdict_ok = has_verdict and not targets
    if len(completed) >= 3 and (targets or not has_verdict):
        await _stage(date, slug, "synthesis")
        verdict_ok = await _synthesize(date, slug, question, states, sources)

    # Finished: "done" only when all five completed AND the verdict exists; otherwise "partial" or "failed".
    status = "done" if len(completed) == len(PERSONAS) and verdict_ok else ("failed" if not completed else "partial")
    finished = {"status": status, "stage": "finished", "completed": str(len(completed))}
    await store.update_debate_fields(date, slug, finished)


# Marks every analyst that never finished as failed, and sets the final status. Used after a crash or a restart.
async def _fail_unfinished(date: str, slug: str, message: str) -> None:
    record = await store.get_debate(date, slug)
    if record is None:
        return
    completed = 0
    for persona in PERSONAS:
        state = record["perspectives"].get(persona) or _pending()
        if state["status"] in ("pending", "generating"):
            await store.set_perspective(date, slug, persona, {**state, "status": "failed", "error": message})
        elif state["status"] == "completed":
            completed += 1
    status = "failed" if completed == 0 else "partial"
    await store.update_debate_fields(date, slug, {"status": status, "stage": "finished", "completed": str(completed)})


# If a debate says "generating" but no job is alive (the server restarted or crashed), repair it now so the visitor
# sees a retryable state instead of a spinner that never ends. Returns the (possibly refreshed) record.
async def reconcile_stalled(debate_id: str, record: dict) -> dict:
    if record.get("origin") != "user" or record.get("status") != "generating":
        return record
    if await store.job_lock_held(debate_id):
        return record
    parsed = store.parse_debate_id(debate_id)
    if not parsed:
        return record
    await _fail_unfinished(parsed[0], parsed[1], ERR_INTERRUPTED)
    return await store.get_debate(*parsed) or record

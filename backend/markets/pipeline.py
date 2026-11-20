"""Runs one market day: fetch and freeze the packet, let three agents debate it (with a validator that can send an
answer back), write the moderator's verdict, and keep the state in Redis as it goes."""
import asyncio  # runs the fetches and the two first agents at once
import json  # model replies and stored fields
import logging
from datetime import UTC, datetime

from ..config import llm, settings
from ..graph.guardrails.common import GuardUnavailable
from ..graph.guardrails.output_guard import check_output
from ..graph.prompts import article_block
from ..services import redis_service as redis_store
from ..userdebate.synthesis import extract_json  # pulls the JSON object out of a model reply
from . import store
from .build import build_packet, now_iso
from .packet import NoMarketData
from .prompts import MODERATOR_SYSTEM, RETRY_NOTE, agent_system
from .providers import collect, configured_providers
from .validator import validate_agent, validate_verdict

logger = logging.getLogger(__name__)

ERR_UNUSABLE = "The model returned an answer in an unusable format."
ERR_TIMEOUT = "The AI provider took too long to respond."
ERR_PROVIDER = "The AI provider was unavailable or rate-limited."
ERR_BLOCKED = "The answer was blocked by the content filter."
ERR_FILTER_DOWN = "The content filter is unavailable, so nothing was published."
ERR_REJECTED = "The validator rejected every attempt (see the audit trail)."
ERR_INTERRUPTED = "Generation was interrupted (the server restarted or stopped). Run it again to continue."
ERR_NO_DATA = "The NIFTY 50 data could not be fetched, so there is no market day to debate."


def _now() -> str:
    return datetime.now(UTC).isoformat()


# Sends one prompt to the model in a worker thread, giving up after the configured time.
async def _ask(system: str, user: str, max_tokens: int) -> str:
    return await asyncio.wait_for(
        asyncio.to_thread(llm.invoke, system=system, user=user, max_tokens=max_tokens, fast=False),
        timeout=settings.PERSPECTIVE_TIMEOUT_SECONDS,
    )


# The facts as the agents see them: one line per fact, fenced as data.
def facts_block(packet: dict) -> str:
    lines = [f"[{f['id']}] ({f['series']}) {f['text']}" for f in packet["facts"]]
    missing = packet.get("missing") or []
    if missing:
        lines.append("Series missing or stale: " + ", ".join(m["series"] for m in missing) + ".")
    return f"Frozen data packet for {packet['as_of']}:\n{article_block(chr(10).join(lines))}"


# Every reader-facing text of an answer, in a fixed order, for the content filter.
def _texts(answer: dict) -> list[str]:
    out: list[str] = []
    for key in ("stance", "thesis", "summary", "attribution_view", "bull_strongest", "bear_strongest", "conclusion",
                "attribution_reasoning"):
        if isinstance(answer.get(key), str):
            out.append(answer[key])
    for key in ("caveats", "what_would_change", "data_gaps"):
        out += [t for t in answer.get(key, []) if isinstance(t, str)]
    for item in answer.get("claims", []) + answer.get("key_drivers", []):
        out.append(item["text"])
    return out


# Screens the text of a validated answer. Returns an error message, or None when it may be published.
async def _screen(answer: dict) -> str | None:
    joined = "\n\n".join(_texts(answer))
    try:
        result = await asyncio.to_thread(check_output, joined)
    except GuardUnavailable:
        return ERR_FILTER_DOWN
    return None if result.passed else ERR_BLOCKED


# The heart of the project: ask, validate, and if the validator rejects the answer send it back with the reasons.
# Returns (answer or None, error or None, audit trail). The audit trail records every attempt and why it failed.
async def ask_with_validation(
    system: str, user: str, max_tokens: int, validate
) -> tuple[dict | None, str | None, list]:
    audit: list[dict] = []
    attempts = max(1, settings.MARKETS_MAX_ATTEMPTS)
    prompt = user
    error = ERR_UNUSABLE
    for attempt in range(1, attempts + 1):
        entry: dict = {"attempt": attempt, "at": _now(), "outcome": "", "rejections": []}
        audit.append(entry)
        try:
            raw = await _ask(system, prompt, max_tokens)
            data = extract_json(raw)
            if data is None:
                entry["outcome"], error = "unusable", ERR_UNUSABLE
                prompt = user + "\n\n" + RETRY_NOTE.format(reasons="- The reply was not a single JSON object.")
            else:
                answer, rejections = validate(data)
                if answer is not None:
                    blocked = await _screen(answer)
                    if blocked is None:
                        entry["outcome"] = "accepted"
                        return answer, None, audit
                    entry["outcome"], error = "blocked", blocked
                    if blocked == ERR_FILTER_DOWN:
                        return None, blocked, audit
                else:
                    entry["outcome"], entry["rejections"], error = "rejected", rejections, ERR_REJECTED
                    reasons = "\n".join(f"- {r['message']}" for r in rejections)
                    prompt = user + "\n\n" + RETRY_NOTE.format(reasons=reasons)
        except TimeoutError:
            entry["outcome"], error = "timeout", ERR_TIMEOUT
        except Exception:
            logger.exception("Market LLM call failed (attempt %d/%d)", attempt, attempts)
            entry["outcome"], error = "provider_error", ERR_PROVIDER
        if attempt < attempts:
            await asyncio.sleep(settings.PERSPECTIVE_BACKOFF_SECONDS * 2 ** (attempt - 1))
    return None, error, audit


# One analyst: validated against the packet. The skeptic also reads the bull's and bear's accepted theses.
async def run_agent(date: str, role: str, packet: dict, others: dict[str, dict]) -> dict:
    facts = {f["id"]: f for f in packet["facts"]}
    user = facts_block(packet)
    if role == "skeptic":
        lines = [f"- {r}: {a['stance']} {a['thesis']}" for r, a in others.items()]
        user += "\n\nThe other analysts' accepted positions:\n" + ("\n".join(lines) or "None were accepted.")
    await store.set_agent(date, role, {**store.pending_agent(), "status": "generating", "started_at": _now()})

    answer, error, audit = await ask_with_validation(
        agent_system(role), user, 1000, lambda data: validate_agent(data, role, facts, packet["attribution"])
    )
    state = {
        "status": "completed" if answer else "failed", "attempts": len(audit), "error": error,
        "content": answer, "audit": audit, "finished_at": _now(),
    }
    await store.set_agent(date, role, state)
    return state


# The moderator's verdict, from the accepted claims only.
async def run_verdict(date: str, packet: dict, agents: dict[str, dict]) -> bool:
    facts = {f["id"]: f for f in packet["facts"]}
    accepted = {r: s["content"] for r, s in agents.items() if s["status"] == "completed"}
    blocks = []
    for role, content in accepted.items():
        claims = "\n".join(f"  [{c['id']}] ({c['kind']}; cites {', '.join(c['fact_ids'])}) {c['text']}"
                           for c in content["claims"])
        extra = f"\n  Attribution: {content['attribution']}" if role == "skeptic" else ""
        blocks.append(f"{role}: {content['stance']}\n{claims}{extra}")
    user = f"{facts_block(packet)}\n\nValidated analyst claims ({len(accepted)} of 3 analysts):\n" + "\n\n".join(blocks)
    verdict, error, audit = await ask_with_validation(
        MODERATOR_SYSTEM, user, 1200,
        lambda data: validate_verdict(data, facts, packet.get("missing", []), packet["attribution"]),
    )
    if verdict is None:
        await store.update(date, {"verdict": "{}", "verdict_error": error or ERR_UNUSABLE,
                                  "verdict_audit": json.dumps(audit)})
        return False
    verdict["based_on"] = {"analysts": len(accepted), "of": 3, "facts": len(packet["facts"])}
    await store.update(date, {"verdict": json.dumps(verdict), "verdict_error": "", "verdict_audit": json.dumps(audit)})
    return True


# Runs the agents that have not completed (bull and bear together, then the skeptic), then the verdict if it is needed.
async def _run_day(date: str, packet: dict, record: dict, rerun_all: bool) -> None:
    agents = {r: (store.pending_agent() if rerun_all else record["agents"][r]) for r in store.ROLES}
    lock = store.lock_id(date)
    todo = [r for r in store.ROLES if agents[r]["status"] != "completed"]
    sem = asyncio.Semaphore(max(1, settings.LLM_CONCURRENCY))

    async def limited(role: str, others: dict) -> None:
        async with sem:
            agents[role] = await run_agent(date, role, packet, others)
        await redis_store.refresh_job_lock(lock)

    await store.update(date, {"status": "generating", "stage": "agents"})
    await asyncio.gather(*(limited(r, {}) for r in ("bull", "bear") if r in todo))
    if "skeptic" in todo:
        accepted = {r: a["content"] for r, a in agents.items() if r != "skeptic" and a["status"] == "completed"}
        await limited("skeptic", accepted)

    completed = [r for r in store.ROLES if agents[r]["status"] == "completed"]
    verdict_ok = bool(record["verdict"]) and not todo and not rerun_all
    if len(completed) >= 2 and (todo or rerun_all or not record["verdict"]):
        await store.update(date, {"stage": "verdict"})
        verdict_ok = await run_verdict(date, packet, agents)
    status = "done" if len(completed) == 3 and verdict_ok else ("failed" if not completed else "partial")
    await store.update(date, {"status": status, "stage": "finished"})


# Runs (or resumes) one market day and returns its date (the anchor index's last trading day), or None when there was
# no data. A finished day is left alone; an unfinished one resumes from its frozen packet; `force` starts over.
async def run_market_day(requested: str, force: bool = False) -> str | None:
    date: str | None = None
    claimed = False
    try:
        fetched = await asyncio.to_thread(collect, requested, configured_providers())
        flows = await store.get_flows()
        try:
            packet, fingerprint = build_packet(requested, fetched, flows)
        except NoMarketData:
            logger.error(ERR_NO_DATA)
            return None
        date = packet["as_of"]
        # Remember new flow points so the 5 and 20 day totals build up over time.
        if "FII_NET" in fetched:
            await store.save_flows(fetched["FII_NET"].points)

        if not await redis_store.acquire_job_lock(store.lock_id(date)):
            logger.info("Market day %s is already being generated", date)
            return date
        claimed = True
        record = await store.get(date)
        if record is not None and not force and record["status"] == "done":
            return date
        if record is None or force:
            await store.create(date, packet, fingerprint, now_iso())
            record = await store.get(date)
        else:
            packet = record["packet"]  # resume from the frozen packet, never a newer fetch
        if record is None:
            return date
        await _run_day(date, packet, record, rerun_all=force)
    except Exception:
        logger.exception("Market day %s crashed", requested)
        if date:
            await _fail_unfinished(date, ERR_INTERRUPTED)
    finally:
        if claimed and date:
            await redis_store.release_job_lock(store.lock_id(date))
    return date


# Marks every agent that never finished as failed and sets the final status. Used after a crash or a restart.
async def _fail_unfinished(date: str, message: str) -> None:
    record = await store.get(date)
    if record is None:
        return
    done = 0
    for role, state in record["agents"].items():
        if state["status"] in ("pending", "generating"):
            await store.set_agent(date, role, {**state, "status": "failed", "error": message})
        elif state["status"] == "completed":
            done += 1
    await store.update(date, {"status": "failed" if done == 0 else "partial", "stage": "finished"})


# A day that says "generating" with no live job (the server restarted) is repaired when read, so the page never
# spins forever. Returns the refreshed record.
async def reconcile_stalled(record: dict) -> dict:
    if record.get("status") != "generating" or await redis_store.job_lock_held(store.lock_id(record["date"])):
        return record
    await _fail_unfinished(record["date"], ERR_INTERRUPTED)
    return await store.get(record["date"]) or record

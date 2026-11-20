"""Redis storage for market days: one hash per day (`market:{date}`), an index of days and the FII flow history."""
import json  # fields are stored as JSON text
import time  # timestamps for the record
from typing import Any

from ..config import settings  # retention
from ..services import redis_service as redis_store  # the shared Redis client, plus the generic job lock
from .build import brief  # headline numbers for the list view

ROLES = ("bull", "bear", "skeptic")
INDEX_KEY = "market:index"
FLOWS_KEY = "market:flows"


def _key(date: str) -> str:
    return f"market:{date}"


# The lock id for a day's job (the generic job lock is keyed by any string).
def lock_id(date: str) -> str:
    return f"market:{date}"


# An integer that sorts like the date (2026-11-19 -> 20261119), used as the index score.
def _score(date: str) -> int:
    return int(date.replace("-", ""))


def _loads(text: Any, default):
    try:
        return json.loads(text) if text else default
    except (TypeError, ValueError):
        return default


# Creates a day's record from a frozen packet. The agents are pending; the day is added to the index.
async def create(date: str, packet: dict, fingerprint: str, created_at: str) -> None:
    redis = redis_store.get_redis()
    key = _key(date)
    mapping = {
        "status": "generating", "stage": "agents", "date": date, "packet": json.dumps(packet),
        "packet_sha256": fingerprint, "brief": json.dumps(brief(packet)), "verdict": "{}", "verdict_error": "",
        "created_at": created_at,
        "updated_at": str(time.time()),
    }
    for role in ROLES:
        mapping[f"a:{role}"] = json.dumps(pending_agent())
    await redis.hset(key, mapping=mapping)  # type: ignore[arg-type]
    await redis.expire(key, settings.DEBATE_TTL_SECONDS)
    await redis.zadd(INDEX_KEY, {date: _score(date)})


def pending_agent() -> dict:
    return {"status": "pending", "attempts": 0, "error": None, "content": None, "audit": []}


# Reads a day's record with its JSON fields parsed, or None.
async def get(date: str) -> dict | None:
    data = await redis_store.get_redis().hgetall(_key(date))
    if not data:
        return None
    return {
        "date": data.get("date", date), "status": data.get("status", ""), "stage": data.get("stage", ""),
        "created_at": data.get("created_at", ""), "packet": _loads(data.get("packet"), {}),
        "packet_sha256": data.get("packet_sha256", ""), "verdict": _loads(data.get("verdict"), {}),
        "verdict_error": data.get("verdict_error", ""), "verdict_audit": _loads(data.get("verdict_audit"), []),
        "agents": {r: _loads(data.get(f"a:{r}"), pending_agent()) for r in ROLES},
    }


async def update(date: str, fields: dict[str, str]) -> None:
    fields = {**fields, "updated_at": str(time.time())}
    await redis_store.get_redis().hset(_key(date), mapping=fields)  # type: ignore[arg-type]


async def set_agent(date: str, role: str, state: dict) -> None:
    await update(date, {f"a:{role}": json.dumps(state)})


# Dates newest first.
async def list_dates(limit: int, offset: int) -> list[str]:
    values = await redis_store.get_redis().zrevrange(INDEX_KEY, offset, offset + limit - 1)
    return [str(v) for v in values]


async def count() -> int:
    return int(await redis_store.get_redis().zcard(INDEX_KEY))


async def latest_date() -> str | None:
    values = await redis_store.get_redis().zrevrange(INDEX_KEY, 0, 0)
    return str(values[0]) if values else None


# FII flow history accumulated day by day (the NSE endpoint only returns the latest day).
async def get_flows() -> dict[str, float]:
    raw = await redis_store.get_redis().hgetall(FLOWS_KEY)
    return {str(d): float(v) for d, v in raw.items()}


async def save_flows(points: list[tuple[str, float]]) -> None:
    if points:
        await redis_store.get_redis().hset(FLOWS_KEY, mapping={d: str(v) for d, v in points})


# Small summaries for the list view: one pipelined read of three fields per day. Missing days are skipped.
async def summaries(dates: list[str]) -> list[dict]:
    if not dates:
        return []
    pipe = redis_store.get_redis().pipeline()
    for date in dates:
        pipe.hmget(_key(date), ["status", "brief", "a:bull", "a:bear", "a:skeptic"])
    rows = await pipe.execute()
    out = []
    for date, (status, brief_text, *agents) in zip(dates, rows, strict=True):
        if status is None:
            continue
        completed = sum(1 for a in agents if _loads(a, {}).get("status") == "completed")
        out.append({"date": date, "status": status, "completed": completed, **_loads(brief_text, {})})
    return out

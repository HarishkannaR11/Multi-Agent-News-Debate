import json
import re
import time
from datetime import UTC, datetime

import redis.asyncio as redis

from ..config import settings

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_ID_RE = re.compile(r"^(\d{4}-\d{2}-\d{2}):([a-z0-9-]{1,60})$")

INDEX_KEY = "debates:index"      # ZSET  member "date:slug", score = created-at epoch seconds
SEEN_URLS_KEY = "seen:urls"      # ZSET  member article url, score = epoch seconds
SEEN_URLS_TTL = 60 * 60 * 24 * 14

_redis: redis.Redis | None = None


def get_redis() -> redis.Redis:
    """Created on first use so importing the app needs no running Redis."""
    global _redis
    if _redis is None:
        _redis = redis.from_url(settings.REDIS_URL, decode_responses=True)
    return _redis


def _strs(values) -> list[str]:
    """redis-py is typed as returning bytes|str; we always connect with decode_responses=True."""
    return [v.decode() if isinstance(v, bytes) else str(v) for v in values]


def _debate_key(date: str, topic_slug: str) -> str:
    return f"debate:{date}:{topic_slug}"


def _opinions_key(date: str, topic_slug: str, user_id: str) -> str:
    return f"opinions:{date}:{topic_slug}:{user_id}"


def parse_debate_id(debate_id: str) -> tuple[str, str] | None:
    """Split a full '{date}:{slug}' id. Returns None if it isn't well-formed."""
    match = _ID_RE.match(debate_id)
    return (match.group(1), match.group(2)) if match else None


def _decode(data: dict) -> dict:
    return {
        "status": data.get("status", ""),
        "date": data.get("date", ""),
        "created_at": data.get("created_at", ""),
        "topic": data.get("topic", ""),
        "source_url": data.get("source_url", ""),
        "news_context": data.get("news_context", ""),
        "verdict": data.get("verdict", ""),
        "arguments": json.loads(data.get("arguments", "{}")),
        "rebuttals": json.loads(data.get("rebuttals", "{}")),
        "bias_scores": json.loads(data.get("bias_scores", "{}")),
    }


async def ping() -> bool:
    return bool(await get_redis().ping())


async def save_debate(date: str, topic_slug: str, state: dict) -> str:
    """Store a finished debate and index it. Returns its id."""
    r = get_redis()
    key = _debate_key(date, topic_slug)
    debate_id = f"{date}:{topic_slug}"
    now = time.time()
    async with r.pipeline(transaction=True) as pipe:
        pipe.hset(key, mapping={
            "status": state.get("status", ""),
            "date": date,
            "created_at": datetime.fromtimestamp(now, tz=UTC).isoformat(),
            "topic": state.get("topic", ""),
            "source_url": state.get("source_url", ""),
            "news_context": state.get("news_context", ""),
            "verdict": state.get("verdict", ""),
            "arguments": json.dumps(state.get("arguments", {})),
            "rebuttals": json.dumps(state.get("rebuttals", {})),
            "bias_scores": json.dumps(state.get("bias_scores", {})),
        })
        pipe.expire(key, settings.DEBATE_TTL_SECONDS)
        pipe.zadd(INDEX_KEY, {debate_id: now})
        pipe.zremrangebyscore(INDEX_KEY, "-inf", now - settings.DEBATE_TTL_SECONDS)
        if state.get("source_url"):
            pipe.zadd(SEEN_URLS_KEY, {state["source_url"]: now})
            pipe.zremrangebyscore(SEEN_URLS_KEY, "-inf", now - SEEN_URLS_TTL)
        await pipe.execute()
    return debate_id


async def get_debate(date: str, topic_slug: str) -> dict | None:
    data = await get_redis().hgetall(_debate_key(date, topic_slug))
    return _decode(data) if data else None


async def resolve_debate_id(raw: str) -> str | None:
    """Turn a user-supplied id into a stored debate id, or None.

    Accepts a full '{date}:{slug}', a bare 'YYYY-MM-DD' (newest debate that day),
    or 'latest'. Anything else is treated as not found.
    """
    r = get_redis()
    if raw == "latest":
        newest = _strs(await r.zrevrange(INDEX_KEY, 0, 0))
        return newest[0] if newest else None
    if _DATE_RE.match(raw):
        for member in _strs(await r.zrevrange(INDEX_KEY, 0, 99)):
            if member.startswith(f"{raw}:"):
                return member
        return None
    parsed = parse_debate_id(raw)
    if parsed and await r.exists(_debate_key(*parsed)):
        return raw
    return None


async def list_debates(offset: int = 0, limit: int = 30) -> list[dict]:
    """Newest-first debate summaries, one index read plus one pipelined fetch."""
    r = get_redis()
    ids = _strs(await r.zrevrange(INDEX_KEY, offset, offset + limit - 1))
    if not ids:
        return []
    async with r.pipeline(transaction=False) as pipe:
        for debate_id in ids:
            pipe.hgetall(_debate_key(*debate_id.split(":", 1)))
        rows = await pipe.execute()

    debates = []
    expired = []
    for debate_id, data in zip(ids, rows, strict=True):
        if not data:
            expired.append(debate_id)
            continue
        full = _decode(data)
        debates.append({
            "id": debate_id,
            "date": full["date"] or debate_id.split(":", 1)[0],
            "created_at": full["created_at"],
            "topic": full["topic"],
            "verdict": full["verdict"],
            "status": full["status"],
            "bias_scores": full["bias_scores"],
        })
    if expired:
        await r.zrem(INDEX_KEY, *expired)
    return debates


async def rebuild_index_if_empty() -> int:
    """Index debates saved before the index existed. Returns how many were added."""
    r = get_redis()
    if await r.zcard(INDEX_KEY):
        return 0
    added = 0
    async for raw_key in r.scan_iter(match="debate:*"):
        _, date, slug = str(raw_key).split(":", 2)
        if not (_DATE_RE.match(date) and slug):
            continue
        created = datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=UTC).timestamp()
        await r.zadd(INDEX_KEY, {f"{date}:{slug}": created})
        added += 1
    return added


async def recent_source_urls() -> list[str]:
    r = get_redis()
    await r.zremrangebyscore(SEEN_URLS_KEY, "-inf", time.time() - SEEN_URLS_TTL)
    return _strs(await r.zrange(SEEN_URLS_KEY, 0, -1))


async def acquire_daily_lock(date: str, ttl_seconds: int = 60 * 30) -> bool:
    """True if this caller owns today's run. A short TTL lets a crashed run be retried."""
    return bool(await get_redis().set(f"lock:daily:{date}", "1", nx=True, ex=ttl_seconds))


async def release_daily_lock(date: str) -> None:
    await get_redis().delete(f"lock:daily:{date}")


async def mark_daily_done(date: str) -> None:
    """Keep the lock for a day after success so replicas/retries don't run it twice."""
    await get_redis().set(f"lock:daily:{date}", "done", ex=60 * 60 * 36)


async def rate_limit_allow(bucket: str, limit: int, window_seconds: int) -> bool:
    """Fixed-window counter. Returns False once `limit` hits are used in the window."""
    r = get_redis()
    key = f"rate:{bucket}"
    # Create-with-TTL first so a crash between the two calls can't leave an immortal counter.
    await r.set(key, 0, ex=window_seconds, nx=True)
    return await r.incr(key) <= limit


async def append_opinion(date: str, topic_slug: str, user_id: str, entry: dict) -> None:
    key = _opinions_key(date, topic_slug, user_id)
    await get_redis().rpush(key, json.dumps(entry))
    await get_redis().expire(key, settings.OPINION_TTL_SECONDS)


async def get_opinions(date: str, topic_slug: str, user_id: str) -> list[dict]:
    raw = await get_redis().lrange(_opinions_key(date, topic_slug, user_id), 0, -1)
    return [json.loads(item) for item in raw]

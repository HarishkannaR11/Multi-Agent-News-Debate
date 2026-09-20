import json

import redis.asyncio as redis

from ..config import settings

_pool = redis.from_url(settings.REDIS_URL, decode_responses=True)


def _debate_key(date: str, topic_slug: str) -> str:
    return f"debate:{date}:{topic_slug}"


def _opinions_key(date: str, topic_slug: str, user_id: str) -> str:
    return f"opinions:{date}:{topic_slug}:{user_id}"


async def save_debate(date: str, topic_slug: str, state: dict) -> None:
    key = _debate_key(date, topic_slug)
    await _pool.hset(key, mapping={
        "status": state.get("status", ""),
        "topic": state.get("topic", ""),
        "news_context": state.get("news_context", ""),
        "verdict": state.get("verdict", ""),
        "arguments": json.dumps(state.get("arguments", {})),
        "rebuttals": json.dumps(state.get("rebuttals", {})),
        "bias_scores": json.dumps(state.get("bias_scores", {})),
    })
    await _pool.expire(key, settings.DEBATE_TTL_SECONDS)


async def get_debate(date: str, topic_slug: str) -> dict | None:
    key = _debate_key(date, topic_slug)
    data = await _pool.hgetall(key)
    if not data:
        return None
    return {
        "status": data.get("status", ""),
        "topic": data.get("topic", ""),
        "news_context": data.get("news_context", ""),
        "verdict": data.get("verdict", ""),
        "arguments": json.loads(data.get("arguments", "{}")),
        "rebuttals": json.loads(data.get("rebuttals", "{}")),
        "bias_scores": json.loads(data.get("bias_scores", "{}")),
    }


async def list_debates(pattern: str = "debate:*") -> list[dict]:
    keys = [key async for key in _pool.scan_iter(match=pattern)]
    debates = []
    for key in sorted(keys, reverse=True):
        _, date, topic_slug = key.split(":", 2)
        data = await get_debate(date, topic_slug)
        if data:
            debates.append({"id": f"{date}:{topic_slug}", "date": date, **data})
    return debates


async def append_opinion(date: str, topic_slug: str, user_id: str, entry: dict) -> None:
    key = _opinions_key(date, topic_slug, user_id)
    await _pool.rpush(key, json.dumps(entry))
    await _pool.expire(key, settings.OPINION_TTL_SECONDS)


async def get_opinions(date: str, topic_slug: str, user_id: str) -> list[dict]:
    key = _opinions_key(date, topic_slug, user_id)
    raw = await _pool.lrange(key, 0, -1)
    return [json.loads(item) for item in raw]

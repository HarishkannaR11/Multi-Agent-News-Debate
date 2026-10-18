import json  # converts Python objects to/from JSON text (Redis stores plain text)
import re  # regular expressions (pattern matching on text)
import time  # gives the current time as a number
from datetime import UTC, datetime  # date/time class and the UTC timezone
from typing import Any  # "any type" (used where redis-py's strict typing would reject a plain dict)

import redis.asyncio as redis  # the async Redis client (named "redis" in this file)

from ..config import PERSONA_KEYS, settings  # the five analyst names and the shared app settings

# Pattern for a plain date like "2026-10-01".
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
# Pattern for a full debate id like "2026-10-01:some-topic" (captures the date and the slug).
_ID_RE = re.compile(r"^(\d{4}-\d{2}-\d{2}):([a-z0-9-]{1,60})$")

INDEX_KEY = "debates:index"      # ZSET  member "date:slug", score = created-at epoch seconds
SEEN_URLS_KEY = "seen:urls"      # ZSET  member article url, score = epoch seconds
# Remember debated article URLs for 14 days (seconds).
SEEN_URLS_TTL = 60 * 60 * 24 * 14

# The shared Redis client; None until first used.
_redis: redis.Redis | None = None


# Returns the shared Redis client, creating it on first use.
def get_redis() -> redis.Redis:
    """Created on first use so importing the app needs no running Redis."""
    # We assign to the module-level variable below, so declare it as global.
    global _redis
    # Create the client only once.
    if _redis is None:
        # Connect using the configured URL; decode_responses=True returns text instead of raw bytes.
        _redis = redis.from_url(settings.REDIS_URL, decode_responses=True)
    # Return the client.
    return _redis


# Converts a list of Redis results to a list of plain strings.
def _strs(values) -> list[str]:
    """redis-py is typed as returning bytes|str; we always connect with decode_responses=True."""
    # Decode bytes to text if needed; otherwise convert whatever it is to text.
    return [v.decode() if isinstance(v, bytes) else str(v) for v in values]


# Builds the Redis key under which one debate is stored.
def _debate_key(date: str, topic_slug: str) -> str:
    # Example: "debate:2026-10-01:some-topic".
    return f"debate:{date}:{topic_slug}"


# Builds the Redis key for one user's opinions on one debate.
def _opinions_key(date: str, topic_slug: str, user_id: str) -> str:
    # Example: "opinions:2026-10-01:some-topic:user123".
    return f"opinions:{date}:{topic_slug}:{user_id}"


# Splits a full debate id into (date, slug), or returns None if it is malformed.
def parse_debate_id(debate_id: str) -> tuple[str, str] | None:
    """Split a full '{date}:{slug}' id. Returns None if it isn't well-formed."""
    # Check the id against the pattern.
    match = _ID_RE.match(debate_id)
    # If it matched, return the two captured parts; otherwise None.
    return (match.group(1), match.group(2)) if match else None


# Parses JSON text from Redis; a missing or damaged value gives the default instead of an error.
def _loads(text: str | None, default):
    try:
        return json.loads(text) if text else default
    except (TypeError, ValueError):
        return default


# Converts a debate as stored in Redis (all text) back into a normal Python dict.
def _decode(data: dict) -> dict:
    # Build the dict field by field, using "" when a field is missing.
    return {
        "status": data.get("status", ""),
        "date": data.get("date", ""),
        "created_at": data.get("created_at", ""),
        "topic": data.get("topic", ""),
        "source_url": data.get("source_url", ""),
        "news_context": data.get("news_context", ""),
        "verdict": data.get("verdict", ""),
        # These three were saved as JSON text, so parse them back into dicts.
        "arguments": json.loads(data.get("arguments", "{}")),
        "rebuttals": json.loads(data.get("rebuttals", "{}")),
        "bias_scores": json.loads(data.get("bias_scores", "{}")),
        # Fields used by debates that a visitor started from their own question (empty for daily debates).
        "origin": data.get("origin", "daily"),
        "question": data.get("question", ""),
        "category": data.get("category", ""),
        "stage": data.get("stage", ""),
        "updated_at": data.get("updated_at", ""),
        "use_sources": data.get("use_sources", "0") == "1",
        "completed": int(data.get("completed", "0") or 0),
        "sources": _loads(data.get("sources"), []),
        "disagreements": _loads(data.get("disagreements"), {}),
        "verdict_data": _loads(data.get("verdict_data"), {}),
        # One stored field per analyst ("p:left", ...), so parallel tasks never overwrite each other.
        "perspectives": {p: _loads(data.get(f"p:{p}"), None) for p in PERSONA_KEYS if f"p:{p}" in data},
        # Debates saved before the second round existed simply have no such fields.
        "focus": data.get("focus", ""),
        "crossfire": json.loads(data.get("crossfire", "{}")),
    }


# Checks that Redis is reachable.
async def ping() -> bool:
    # Send PING; Redis answers True when healthy.
    return bool(await get_redis().ping())


# Saves a finished debate and adds it to the index. Returns its id.
async def save_debate(date: str, topic_slug: str, state: dict) -> str:
    """Store a finished debate and index it. Returns its id."""
    # Get the Redis client.
    r = get_redis()
    # The key the debate hash is stored under.
    key = _debate_key(date, topic_slug)
    # The public id, e.g. "2026-10-01:some-topic".
    debate_id = f"{date}:{topic_slug}"
    # The current time as a number (used for the "created at" timestamp and index score).
    now = time.time()
    # A pipeline groups several commands; transaction=True makes them run together (all or nothing).
    async with r.pipeline(transaction=True) as pipe:
        # Store the debate as a Redis hash (a set of named fields).
        pipe.hset(key, mapping={
            "status": state.get("status", ""),
            "date": date,
            # ISO-formatted creation time in UTC.
            "created_at": datetime.fromtimestamp(now, tz=UTC).isoformat(),
            "topic": state.get("topic", ""),
            "source_url": state.get("source_url", ""),
            "news_context": state.get("news_context", ""),
            "verdict": state.get("verdict", ""),
            # Dicts are saved as JSON text.
            "arguments": json.dumps(state.get("arguments", {})),
            "rebuttals": json.dumps(state.get("rebuttals", {})),
            "bias_scores": json.dumps(state.get("bias_scores", {})),
            # The optional second round: the moderator's question and the analysts' answers.
            "focus": state.get("focus", ""),
            "crossfire": json.dumps(state.get("crossfire", {})),
        })
        # Make the debate expire automatically after the retention period.
        pipe.expire(key, settings.DEBATE_TTL_SECONDS)
        # Add the debate to the sorted-set index, scored by creation time.
        pipe.zadd(INDEX_KEY, {debate_id: now})
        # Remove index entries older than the retention period.
        pipe.zremrangebyscore(INDEX_KEY, "-inf", now - settings.DEBATE_TTL_SECONDS)
        # If we know the article URL, remember it so it is not debated again soon.
        if state.get("source_url"):
            # Add the URL to the "seen" set, scored by time.
            pipe.zadd(SEEN_URLS_KEY, {state["source_url"]: now})
            # Forget URLs older than 14 days.
            pipe.zremrangebyscore(SEEN_URLS_KEY, "-inf", now - SEEN_URLS_TTL)
        # Send all the queued commands to Redis in one go.
        await pipe.execute()
    # Return the new debate's id.
    return debate_id


# Loads one debate, or None if it does not exist.
async def get_debate(date: str, topic_slug: str) -> dict | None:
    # Read every field of the debate's hash.
    data = await get_redis().hgetall(_debate_key(date, topic_slug))
    # If it exists, convert it to a normal dict; otherwise None.
    return _decode(data) if data else None


# Turns whatever id the client sent into a real stored debate id, or None.
async def resolve_debate_id(raw: str) -> str | None:
    """Turn a user-supplied id into a stored debate id, or None.

    Accepts a full '{date}:{slug}', a bare 'YYYY-MM-DD' (newest debate that day),
    or 'latest'. Anything else is treated as not found.
    """
    # Get the Redis client.
    r = get_redis()
    # "latest" means the most recently created debate.
    if raw == "latest":
        # Read the highest-scored (newest) entry from the index.
        newest = _strs(await r.zrevrange(INDEX_KEY, 0, 0))
        # Return it, or None if there are no debates.
        return newest[0] if newest else None
    # A bare date means "the newest debate on that day".
    if _DATE_RE.match(raw):
        # Look through the 100 newest index entries.
        for member in _strs(await r.zrevrange(INDEX_KEY, 0, 99)):
            # The first one that starts with that date is the newest from that day.
            if member.startswith(f"{raw}:"):
                return member
        # Nothing found for that date.
        return None
    # Otherwise treat it as a full id and validate its format.
    parsed = parse_debate_id(raw)
    # If the format is valid AND the debate really exists in Redis, accept it.
    if parsed and await r.exists(_debate_key(*parsed)):
        return raw
    # Anything else counts as "not found".
    return None


# Returns short summaries of debates, newest first, for the archive page.
async def list_debates(offset: int = 0, limit: int = 30) -> list[dict]:
    """Newest-first debate summaries, one index read plus one pipelined fetch."""
    # Get the Redis client.
    r = get_redis()
    # Read a page of ids from the index (highest score = newest first).
    ids = _strs(await r.zrevrange(INDEX_KEY, offset, offset + limit - 1))
    # No debates: return an empty list.
    if not ids:
        return []
    # A pipeline without a transaction: just batches the reads into one round trip.
    async with r.pipeline(transaction=False) as pipe:
        # Queue one "read this debate" command per id.
        for debate_id in ids:
            # Split "date:slug" into its two parts for the key.
            pipe.hgetall(_debate_key(*debate_id.split(":", 1)))
        # Send them all and collect the results.
        rows = await pipe.execute()

    # The summaries we will return.
    debates = []
    # Ids whose data no longer exists (expired).
    expired = []
    # Pair each id with its stored data; strict=True checks both lists match in length.
    for debate_id, data in zip(ids, rows, strict=True):
        # No data: the debate expired; remember to clean up its index entry.
        if not data:
            expired.append(debate_id)
            continue
        # Convert the stored data to a normal dict.
        full = _decode(data)
        # Add a short summary (no full transcript, to keep the response small).
        debates.append({
            "id": debate_id,
            # Use the stored date, or fall back to the date inside the id.
            "date": full["date"] or debate_id.split(":", 1)[0],
            "created_at": full["created_at"],
            "topic": full["topic"],
            "verdict": full["verdict"],
            "status": full["status"],
            "bias_scores": full["bias_scores"],
        })
    # Remove expired ids from the index so they are not listed again.
    if expired:
        await r.zrem(INDEX_KEY, *expired)
    # Return the summaries.
    return debates


# After an upgrade, adds old debates (saved before the index existed) to the index.
async def rebuild_index_if_empty() -> int:
    """Index debates saved before the index existed. Returns how many were added."""
    # Get the Redis client.
    r = get_redis()
    # If the index already has entries, there is nothing to do.
    if await r.zcard(INDEX_KEY):
        return 0
    # Count of debates added.
    added = 0
    # Walk through every key that looks like "debate:*" (SCAN is safe on big databases).
    async for raw_key in r.scan_iter(match="debate:*"):
        # Split "debate:DATE:SLUG" into its three parts.
        _, date, slug = str(raw_key).split(":", 2)
        # Skip keys whose date or slug is not valid.
        if not (_DATE_RE.match(date) and slug):
            continue
        # Debates started by visitors are unlisted: they never go into the public index.
        if await r.hget(str(raw_key), "origin") == "user":
            continue
        # Use midnight UTC of the debate's date as its score.
        created = datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=UTC).timestamp()
        # Add it to the index.
        await r.zadd(INDEX_KEY, {f"{date}:{slug}": created})
        # Count it.
        added += 1
    # Report how many were indexed.
    return added


# Returns article URLs debated recently (so the fetcher can skip them).
async def recent_source_urls() -> list[str]:
    # Get the Redis client.
    r = get_redis()
    # First delete URLs older than the 14-day window.
    await r.zremrangebyscore(SEEN_URLS_KEY, "-inf", time.time() - SEEN_URLS_TTL)
    # Return everything that remains.
    return _strs(await r.zrange(SEEN_URLS_KEY, 0, -1))


# Tries to claim today's run; only one caller can succeed.
async def acquire_daily_lock(date: str, ttl_seconds: int = 60 * 30) -> bool:
    """True if this caller owns today's run. A short TTL lets a crashed run be retried."""
    # SET ... NX EX: create the key only if it does not exist (NX) and make it expire (EX). True if we created it.
    return bool(await get_redis().set(f"lock:daily:{date}", "1", nx=True, ex=ttl_seconds))


# Gives up the lock (used after a failed run so it can be retried).
async def release_daily_lock(date: str) -> None:
    # Delete the lock key.
    await get_redis().delete(f"lock:daily:{date}")


# After a successful run, keeps the lock for a day and a half so it cannot run twice.
async def mark_daily_done(date: str) -> None:
    """Keep the lock for a day after success so replicas/retries don't run it twice."""
    # Overwrite the lock with "done" and a 36-hour expiry (60 * 60 * 36 seconds).
    await get_redis().set(f"lock:daily:{date}", "done", ex=60 * 60 * 36)


# Counts a request and says whether the caller is still under the limit.
async def rate_limit_allow(bucket: str, limit: int, window_seconds: int) -> bool:
    """Fixed-window counter. Returns False once `limit` hits are used in the window."""
    # Get the Redis client.
    r = get_redis()
    # The counter's key, e.g. "rate:opinion:1.2.3.4".
    key = f"rate:{bucket}"
    # Create-with-TTL first so a crash between the two calls can't leave an immortal counter.
    # Create the counter at 0 with an expiry, but only if it does not exist yet.
    await r.set(key, 0, ex=window_seconds, nx=True)
    # Add 1 to the counter and check it is still within the limit.
    return await r.incr(key) <= limit


# Appends one opinion (and the AI's reply) to a user's list for a debate.
async def append_opinion(date: str, topic_slug: str, user_id: str, entry: dict) -> None:
    # The list's key.
    key = _opinions_key(date, topic_slug, user_id)
    # Add the entry (as JSON text) to the end of the list.
    await get_redis().rpush(key, json.dumps(entry))
    # Refresh the list's expiry so it is deleted after the retention period.
    await get_redis().expire(key, settings.OPINION_TTL_SECONDS)


# Returns all of a user's saved opinions for a debate, oldest first.
async def get_opinions(date: str, topic_slug: str, user_id: str) -> list[dict]:
    # Read the whole list (index 0 to -1 means "everything").
    raw = await get_redis().lrange(_opinions_key(date, topic_slug, user_id), 0, -1)
    # Parse each JSON text item back into a dict.
    return [json.loads(item) for item in raw]


# --- debates started by visitors from their own question ----------------------------------------------------------
# These are "unlisted": stored like other debates (same key shape, same retention) but never added to the public
# index, so they do not appear in "latest" or the public archive. Whoever has the link can open one.

JOB_LOCK_TTL = 900  # seconds a generation job may go without a heartbeat before it counts as dead


def _job_lock_key(debate_id: str) -> str:
    return f"joblock:{debate_id}"


# Creates the stored record for a new visitor debate, with every analyst "pending". Not added to the public index.
async def create_user_debate(date: str, slug: str, *, question: str, category: str, use_sources: bool) -> None:
    now = time.time()
    key = _debate_key(date, slug)
    pending = json.dumps({"status": "pending", "attempts": 0, "error": None, "content": None})
    mapping: dict[Any, Any] = {
        "origin": "user",
        "status": "generating",
        "stage": "queued",
        "date": date,
        "created_at": datetime.fromtimestamp(now, tz=UTC).isoformat(),
        "updated_at": str(now),
        # The topic IS the visitor's question, so every page that shows "topic" shows exactly what they asked.
        "topic": question,
        "question": question,
        "category": category,
        "use_sources": "1" if use_sources else "0",
        "completed": "0",
        "sources": "[]",
        "sources_done": "0",
        "disagreements": "{}",
        "verdict_data": "{}",
        "verdict": "",
        "arguments": "{}",
        "rebuttals": "{}",
        "bias_scores": "{}",
        "focus": "",
        "crossfire": "{}",
        "source_url": "",
        "news_context": "",
        **{f"p:{persona}": pending for persona in PERSONA_KEYS},
    }
    async with get_redis().pipeline(transaction=True) as pipe:
        pipe.hset(key, mapping=mapping)
        pipe.expire(key, settings.DEBATE_TTL_SECONDS)
        await pipe.execute()


# Updates some fields of a debate (text values) and stamps the time, which doubles as the job's heartbeat.
async def update_debate_fields(date: str, slug: str, fields: dict[str, str]) -> None:
    key = _debate_key(date, slug)
    # Do not resurrect a debate that has expired mid-job.
    if await get_redis().exists(key):
        payload: dict[Any, Any] = {**fields, "updated_at": str(time.time())}
        await get_redis().hset(key, mapping=payload)


# Stores one analyst's state (status, attempts, error, content) under its own field.
async def set_perspective(date: str, slug: str, persona: str, state: dict) -> None:
    await update_debate_fields(date, slug, {f"p:{persona}": json.dumps(state)})


# Reads a single field of a debate as text, or None.
async def get_debate_field(date: str, slug: str, field: str) -> str | None:
    value = await get_redis().hget(_debate_key(date, slug), field)
    return None if value is None else str(value)


# Claims the right to run the generation job for a debate. False if one is already running.
async def acquire_job_lock(debate_id: str, ttl: int = JOB_LOCK_TTL) -> bool:
    return bool(await get_redis().set(_job_lock_key(debate_id), "1", nx=True, ex=ttl))


# Extends the lock while the job is alive.
async def refresh_job_lock(debate_id: str, ttl: int = JOB_LOCK_TTL) -> None:
    await get_redis().expire(_job_lock_key(debate_id), ttl)


async def release_job_lock(debate_id: str) -> None:
    await get_redis().delete(_job_lock_key(debate_id))


# Is a job currently alive for this debate?
async def job_lock_held(debate_id: str) -> bool:
    return bool(await get_redis().exists(_job_lock_key(debate_id)))


# Stores a value only if the key is new (SET NX with an expiry). True when this call stored it.
async def claim_key(key: str, value: str, ttl: int) -> bool:
    return bool(await get_redis().set(f"claim:{key}", value, nx=True, ex=ttl))


# Reads or overwrites a claimed key (used by the duplicate-submission guard).
async def get_claim(key: str) -> str | None:
    value = await get_redis().get(f"claim:{key}")
    return None if value is None else str(value)


async def set_claim(key: str, value: str, ttl: int) -> None:
    await get_redis().set(f"claim:{key}", value, ex=ttl)


async def delete_claim(key: str) -> None:
    await get_redis().delete(f"claim:{key}")


# Stores a visitor's feedback on a debate (newest last, capped, expiring with the debate).
async def append_feedback(debate_id: str, entry: dict) -> None:
    key = f"feedback:{debate_id}"
    r = get_redis()
    await r.rpush(key, json.dumps(entry))
    await r.ltrim(key, -200, -1)
    await r.expire(key, settings.DEBATE_TTL_SECONDS)


# The ids in the PUBLIC index (the daily debates), newest first.
async def public_debate_ids() -> list[str]:
    return _strs(await get_redis().zrevrange(INDEX_KEY, 0, -1))


# Light summaries (no transcripts) for the archive: one pipelined read of a few fields per id.
async def summaries_for(ids: list[str]) -> list[dict]:
    """Missing or expired ids are skipped. Only small fields are read, never the full debate."""
    if not ids:
        return []
    fields = ["date", "created_at", "topic", "category", "status", "origin", "verdict", "completed"]
    async with get_redis().pipeline(transaction=False) as pipe:
        for debate_id in ids:
            parsed = parse_debate_id(debate_id)
            pipe.hmget(_debate_key(*parsed) if parsed else "debate:invalid", fields)
        rows = await pipe.execute()
    summaries = []
    for debate_id, row in zip(ids, rows, strict=True):
        if not row or row[2] is None:  # no topic stored: the debate does not exist (expired or invalid id)
            continue
        date, created_at, topic, category, status, origin, verdict, completed = (
            "" if value is None else str(value) for value in row
        )
        summaries.append({
            "id": debate_id,
            "date": date or debate_id.split(":", 1)[0],
            "created_at": created_at,
            "topic": topic,
            "category": category,
            "status": status,
            "origin": origin or "daily",
            "summary": verdict[:240],
            "completed": int(completed or 0),
        })
    return summaries

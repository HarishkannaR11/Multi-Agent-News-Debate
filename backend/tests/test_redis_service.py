import pytest  # the test framework

from backend.services import redis_service as rs  # the Redis storage layer under test

# Apply the fake Redis fixture to every test in this file.
pytestmark = pytest.mark.usefixtures("fake_redis")

# A sample finished debate used as test data.
STATE = {"status": "done", "topic": "T", "verdict": "V", "arguments": {"left": "a"}, "rebuttals": {},
         "bias_scores": {"left": 0.5}, "source_url": "https://x/1", "news_context": "ctx"}


# Run once per (text, expected result) pair: only "<date>:<slug>" is a valid full id; everything else gives None.
@pytest.mark.parametrize("raw,expected", [
    ("2026-09-30:some-topic", ("2026-09-30", "some-topic")),
    # A bare date, "latest", a path trick, a slug with a space/capital, and extra colons are all rejected.
    ("2026-09-30", None), ("latest", None), ("../etc", None), ("2026-09-30:Bad Slug", None), ("a:b:c", None),
])
def test_parse_debate_id(raw, expected):
    assert rs.parse_debate_id(raw) == expected


# Save two debates, then read, list, page and look them up in every supported way.
async def test_save_get_list_and_resolve():
    await rs.save_debate("2026-09-29", "older", STATE)
    await rs.save_debate("2026-09-30", "newer", {**STATE, "topic": "Newer"})

    # Reading a saved debate returns its data.
    assert (await rs.get_debate("2026-09-30", "newer"))["topic"] == "Newer"
    # The list is newest first.
    assert [d["id"] for d in await rs.list_debates()] == ["2026-09-30:newer", "2026-09-29:older"]
    # Paging: skip one, take one.
    assert [d["id"] for d in await rs.list_debates(offset=1, limit=1)] == ["2026-09-29:older"]
    assert "news_context" not in (await rs.list_debates())[0]     # summaries only

    # "latest", a bare date and a full id all resolve to a real stored id.
    assert await rs.resolve_debate_id("latest") == "2026-09-30:newer"
    assert await rs.resolve_debate_id("2026-09-29") == "2026-09-29:older"
    assert await rs.resolve_debate_id("2026-09-30:newer") == "2026-09-30:newer"
    # A date with no debate, a missing slug and garbage all resolve to None.
    assert await rs.resolve_debate_id("2026-01-01") is None
    assert await rs.resolve_debate_id("2026-09-30:missing") is None
    assert await rs.resolve_debate_id("garbage") is None


# When a debate's data has expired, its leftover entry is removed from the index when listing.
async def test_expired_debates_are_pruned_from_the_index(fake_redis):
    await rs.save_debate("2026-09-30", "gone", STATE)
    # Simulate expiry by deleting the data but leaving the index entry.
    await fake_redis.delete("debate:2026-09-30:gone")
    assert await rs.list_debates() == []
    # The stale index entry was cleaned up (zcard = number of items in the sorted set).
    assert await fake_redis.zcard(rs.INDEX_KEY) == 0


# Debates saved before the index existed can be added to it, and doing it twice adds nothing more.
async def test_rebuild_index_for_debates_saved_before_the_index_existed(fake_redis):
    # Write a debate directly, bypassing save_debate so it is not indexed.
    await fake_redis.hset("debate:2026-09-01:old", mapping={"topic": "Old", "status": "done"})
    # The first rebuild finds 1 debate; the second finds nothing to do.
    assert await rs.rebuild_index_if_empty() == 1
    assert await rs.rebuild_index_if_empty() == 0
    assert (await rs.list_debates())[0]["topic"] == "Old"


# Recently debated source URLs are tracked, and the once-per-day lock works.
async def test_recent_source_urls_and_daily_lock():
    await rs.save_debate("2026-09-30", "t", STATE)
    assert await rs.recent_source_urls() == ["https://x/1"]

    # The first claim on the day's lock succeeds; the second fails because it is already held.
    assert await rs.acquire_daily_lock("2026-09-30") is True
    assert await rs.acquire_daily_lock("2026-09-30") is False
    # After releasing it, it can be taken again.
    await rs.release_daily_lock("2026-09-30")
    assert await rs.acquire_daily_lock("2026-09-30") is True


# The limiter allows 2 requests per 60 seconds per key; keys are independent.
async def test_rate_limit_window(fake_redis):
    results = [await rs.rate_limit_allow("ip:1", 2, 60) for _ in range(4)]
    assert results == [True, True, False, False]
    # A different key has its own allowance.
    assert await rs.rate_limit_allow("ip:2", 2, 60) is True
    # The counter has an expiry, so it resets by itself (ttl = seconds left).
    assert await fake_redis.ttl("rate:ip:1") > 0

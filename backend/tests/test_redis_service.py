import pytest

from backend.services import redis_service as rs

pytestmark = pytest.mark.usefixtures("fake_redis")

STATE = {"status": "done", "topic": "T", "verdict": "V", "arguments": {"left": "a"}, "rebuttals": {},
         "bias_scores": {"left": 0.5}, "source_url": "https://x/1", "news_context": "ctx"}


@pytest.mark.parametrize("raw,expected", [
    ("2026-09-30:some-topic", ("2026-09-30", "some-topic")),
    ("2026-09-30", None), ("latest", None), ("../etc", None), ("2026-09-30:Bad Slug", None), ("a:b:c", None),
])
def test_parse_debate_id(raw, expected):
    assert rs.parse_debate_id(raw) == expected


async def test_save_get_list_and_resolve():
    await rs.save_debate("2026-09-29", "older", STATE)
    await rs.save_debate("2026-09-30", "newer", {**STATE, "topic": "Newer"})

    assert (await rs.get_debate("2026-09-30", "newer"))["topic"] == "Newer"
    assert [d["id"] for d in await rs.list_debates()] == ["2026-09-30:newer", "2026-09-29:older"]
    assert [d["id"] for d in await rs.list_debates(offset=1, limit=1)] == ["2026-09-29:older"]
    assert "news_context" not in (await rs.list_debates())[0]     # summaries only

    assert await rs.resolve_debate_id("latest") == "2026-09-30:newer"
    assert await rs.resolve_debate_id("2026-09-29") == "2026-09-29:older"
    assert await rs.resolve_debate_id("2026-09-30:newer") == "2026-09-30:newer"
    assert await rs.resolve_debate_id("2026-01-01") is None
    assert await rs.resolve_debate_id("2026-09-30:missing") is None
    assert await rs.resolve_debate_id("garbage") is None


async def test_expired_debates_are_pruned_from_the_index(fake_redis):
    await rs.save_debate("2026-09-30", "gone", STATE)
    await fake_redis.delete("debate:2026-09-30:gone")
    assert await rs.list_debates() == []
    assert await fake_redis.zcard(rs.INDEX_KEY) == 0


async def test_rebuild_index_for_debates_saved_before_the_index_existed(fake_redis):
    await fake_redis.hset("debate:2026-09-01:old", mapping={"topic": "Old", "status": "done"})
    assert await rs.rebuild_index_if_empty() == 1
    assert await rs.rebuild_index_if_empty() == 0
    assert (await rs.list_debates())[0]["topic"] == "Old"


async def test_recent_source_urls_and_daily_lock():
    await rs.save_debate("2026-09-30", "t", STATE)
    assert await rs.recent_source_urls() == ["https://x/1"]

    assert await rs.acquire_daily_lock("2026-09-30") is True
    assert await rs.acquire_daily_lock("2026-09-30") is False
    await rs.release_daily_lock("2026-09-30")
    assert await rs.acquire_daily_lock("2026-09-30") is True


async def test_rate_limit_window(fake_redis):
    results = [await rs.rate_limit_allow("ip:1", 2, 60) for _ in range(4)]
    assert results == [True, True, False, False]
    assert await rs.rate_limit_allow("ip:2", 2, 60) is True
    assert await fake_redis.ttl("rate:ip:1") > 0

import pytest

from backend import scheduler
from backend.config import settings
from backend.services import redis_service as rs

pytestmark = pytest.mark.usefixtures("fake_redis")

FINAL = {"status": "done", "date": "2026-09-30", "topic": "Should We? Yes!", "verdict": "v",
         "arguments": {}, "rebuttals": {}, "bias_scores": {}, "source_url": "https://x/1"}


class FlakyGraph:
    def __init__(self, failures):
        self.failures, self.calls = failures, 0

    async def ainvoke(self, state, config=None):
        self.calls += 1
        if self.calls <= self.failures:
            raise RuntimeError("groq down")
        return FINAL


@pytest.fixture(autouse=True)
def fixed_date(monkeypatch):
    monkeypatch.setattr(scheduler, "today_iso", lambda: "2026-09-30")


def use_graph(monkeypatch, graph):
    monkeypatch.setattr(scheduler, "build_graph", lambda: graph)


def test_slugify():
    assert scheduler._slugify("Should We? Yes!") == "should-we-yes"
    assert scheduler._slugify("???") == "topic"
    assert not scheduler._slugify("a" * 59 + " b c").endswith("-")


async def test_retries_then_saves(monkeypatch):
    graph = FlakyGraph(failures=2)
    use_graph(monkeypatch, graph)

    assert await scheduler.run_daily_debate() == "2026-09-30:should-we-yes"
    assert graph.calls == 3
    assert await rs.resolve_debate_id("latest") == "2026-09-30:should-we-yes"


async def test_second_run_the_same_day_is_a_noop(monkeypatch):
    graph = FlakyGraph(failures=0)
    use_graph(monkeypatch, graph)

    await scheduler.run_daily_debate()
    assert await scheduler.run_daily_debate() is None
    assert graph.calls == 1


async def test_lock_is_released_after_final_failure_so_it_can_be_retried(monkeypatch):
    graph = FlakyGraph(failures=99)
    use_graph(monkeypatch, graph)

    assert await scheduler.run_daily_debate() is None
    assert graph.calls == settings.DAILY_RUN_ATTEMPTS

    use_graph(monkeypatch, FlakyGraph(failures=0))
    assert await scheduler.run_daily_debate() is not None

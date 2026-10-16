import pytest  # the test framework

from backend import scheduler  # the daily-job module under test
from backend.config import settings  # the settings object (the retry count lives here)
from backend.services import redis_service as rs  # Redis helpers, shortened to "rs"

# Apply the fake Redis fixture to every test in this file.
pytestmark = pytest.mark.usefixtures("fake_redis")

# The final state a (fake) finished graph run returns.
FINAL = {"status": "done", "date": "2026-09-30", "topic": "Should We? Yes!", "verdict": "v",
         "arguments": {}, "rebuttals": {}, "bias_scores": {}, "source_url": "https://x/1"}


# A fake graph that fails a set number of times before succeeding.
class FlakyGraph:
    def __init__(self, failures):
        # How many calls should fail, and how many have happened so far.
        self.failures, self.calls = failures, 0

    # Same method name and parameters as the real graph's ainvoke.
    async def ainvoke(self, state, config=None):
        self.calls += 1
        # Fail while we are still within the allowed number of failures.
        if self.calls <= self.failures:
            raise RuntimeError("groq down")
        # Afterwards succeed with the fixed final state.
        return FINAL


# autouse=True: every test pretends today is 2026-09-30.
@pytest.fixture(autouse=True)
def fixed_date(monkeypatch):
    monkeypatch.setattr(scheduler, "today_iso", lambda: "2026-09-30")


# Helper: make the scheduler use the given fake graph instead of building the real one.
def use_graph(monkeypatch, graph):
    monkeypatch.setattr(scheduler, "build_graph", lambda: graph)


# Turning a topic into a URL-safe slug.
def test_slugify():
    # Punctuation is dropped and words are joined with hyphens, in lower case.
    assert scheduler._slugify("Should We? Yes!") == "should-we-yes"
    # With nothing usable left, a default is used.
    assert scheduler._slugify("???") == "topic"
    # When a long title is cut to the length limit, it must not end with a dangling hyphen.
    assert not scheduler._slugify("a" * 59 + " b c").endswith("-")


# Two failures followed by a success: the job retries and then saves the debate.
async def test_retries_then_saves(monkeypatch):
    graph = FlakyGraph(failures=2)
    use_graph(monkeypatch, graph)

    # It returns the saved debate's id, after 3 attempts in total.
    assert await scheduler.run_daily_debate() == "2026-09-30:should-we-yes"
    assert graph.calls == 3
    # And the debate is really in Redis.
    assert await rs.resolve_debate_id("latest") == "2026-09-30:should-we-yes"


# Running the job twice in one day generates only once.
async def test_second_run_the_same_day_is_a_noop(monkeypatch):
    graph = FlakyGraph(failures=0)
    use_graph(monkeypatch, graph)

    await scheduler.run_daily_debate()
    # The second call returns None (nothing to do) because the day's lock is held.
    assert await scheduler.run_daily_debate() is None
    # The graph ran only once.
    assert graph.calls == 1


# If every attempt fails, the lock is released so that a later run can try again.
async def test_lock_is_released_after_final_failure_so_it_can_be_retried(monkeypatch):
    # Fails far more often than the allowed number of attempts.
    graph = FlakyGraph(failures=99)
    use_graph(monkeypatch, graph)

    # The job gives up after the configured number of attempts and returns None.
    assert await scheduler.run_daily_debate() is None
    assert graph.calls == settings.DAILY_RUN_ATTEMPTS

    # Now a healthy graph: the job can run again (the lock was not left stuck).
    use_graph(monkeypatch, FlakyGraph(failures=0))
    assert await scheduler.run_daily_debate() is not None

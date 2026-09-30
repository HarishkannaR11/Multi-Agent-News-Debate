import pytest

from backend.graph.graph import build_graph, new_debate_state, run_config
from backend.graph.guardrails.common import GuardResult
from backend.graph.nodes import rebuttal
from backend.graph.nodes.agents import PERSONAS

pytestmark = pytest.mark.usefixtures("fake_news")


async def run(seen=None):
    return await build_graph().ainvoke(new_debate_state(seen), config=run_config())


async def test_happy_path_completes(fake_llm):
    state = await run()

    assert state["status"] == "done"
    assert state["topic"] == "Should X happen?"
    assert set(state["arguments"]) == set(PERSONAS)
    assert set(state["rebuttals"]) == set(PERSONAS)
    assert state["verdict"] == "A balanced verdict."
    assert state["bias_scores"]["left"] == 0.7
    assert state["source_url"] == "https://n.example/a"
    assert "[+1200 chars]" not in state["news_context"]


async def test_devil_sees_the_other_four_openings(fake_llm):
    await run()
    devil_system = PERSONAS["devil"]
    (call,) = [c for c in fake_llm.calls if c["system"].startswith(devil_system) and "round 1" not in c["user"]
               and "rebuttal" not in c["user"].lower()]
    for key in ("left", "right", "economist", "geopolitical"):
        assert f"[{key}] {key} says something" in call["user"]


async def test_fetcher_skips_recently_debated_urls(fake_llm):
    state = await run(seen=["https://n.example/a"])
    assert state["source_url"] == "https://n.example/b"


async def test_guardrail_that_always_fails_terminates_and_drops_rebuttals(fake_llm, monkeypatch):
    monkeypatch.setattr(rebuttal, "check_output", lambda text: GuardResult(False, text, "toxic"))

    state = await run()

    assert state["status"] == "done"
    assert state["rebuttals"] == {}
    # 1 initial attempt + MAX_REBUTTAL_RETRIES retries, per persona, and no more.
    assert len(fake_llm.rebuttal_calls("left")) == 3


async def test_only_failing_rebuttals_are_regenerated(fake_llm, monkeypatch):
    failed_once = set()

    def check(text):
        if text.startswith("right") and "right" not in failed_once:
            failed_once.add("right")
            return GuardResult(False, text, "toxic")
        return GuardResult(True, text.upper())

    monkeypatch.setattr(rebuttal, "check_output", check)

    state = await run()

    assert len(fake_llm.rebuttal_calls("right")) == 2
    assert len(fake_llm.rebuttal_calls("left")) == 1
    assert set(state["rebuttals"]) == set(PERSONAS)
    assert state["rebuttals"]["left"] == "LEFT SAYS SOMETHING"   # guard-fixed text is what's stored

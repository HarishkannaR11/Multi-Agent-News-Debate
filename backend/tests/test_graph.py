import pytest  # the test framework

from backend.graph.graph import build_graph, new_debate_state, run_config  # build, seed and configure the pipeline
from backend.graph.guardrails.common import GuardResult  # the result type a safety check returns
from backend.graph.nodes import rebuttal  # the rebuttal node module (its safety check gets patched)
from backend.graph.nodes.agents import PERSONAS  # the analyst prompts, keyed by analyst name

# Apply the fake_news fixture to every test in this file (so no real news API is called).
pytestmark = pytest.mark.usefixtures("fake_news")


# Helper: runs the whole pipeline once and returns the final state. "seen" = URLs to skip as already debated.
async def run(seen=None):
    return await build_graph().ainvoke(new_debate_state(seen), config=run_config())


# With everything working, the pipeline should finish with a full debate.
async def test_happy_path_completes(fake_llm):
    state = await run()

    # The final stage was reached.
    assert state["status"] == "done"
    # The topic came from the fake extractor.
    assert state["topic"] == "Should X happen?"
    # All five analysts produced an opening and a rebuttal.
    assert set(state["arguments"]) == set(PERSONAS)
    assert set(state["rebuttals"]) == set(PERSONAS)
    # The moderator's verdict and the parsed bias scores are present.
    assert state["verdict"] == "A balanced verdict."
    assert state["bias_scores"]["left"] == 0.7
    # The first article was used, and the "[+1200 chars]" truncation marker was cleaned out of the text.
    assert state["source_url"] == "https://n.example/a"
    assert "[+1200 chars]" not in state["news_context"]


# The devil's advocate must be shown the other four analysts' openings.
async def test_devil_sees_the_other_four_openings(fake_llm):
    await run()
    devil_system = PERSONAS["devil"]
    # Find the single opening-argument call made with the devil's prompt (excluding round-1 and rebuttal calls).
    (call,) = [c for c in fake_llm.calls if c["system"].startswith(devil_system) and "round 1" not in c["user"]
               and "rebuttal" not in c["user"].lower()]
    # Each of the other four analysts' text must appear in the devil's prompt, tagged with the analyst's name.
    for key in ("left", "right", "economist", "geopolitical"):
        assert f"[{key}] {key} says something" in call["user"]


# Articles that were debated recently are skipped.
async def test_fetcher_skips_recently_debated_urls(fake_llm):
    # Mark article A as already seen, so the pipeline should pick article B.
    state = await run(seen=["https://n.example/a"])
    assert state["source_url"] == "https://n.example/b"


# If the safety check rejects every rebuttal, the retries must stop (no endless loop) and the rebuttals be dropped.
async def test_guardrail_that_always_fails_terminates_and_drops_rebuttals(fake_llm, monkeypatch):
    # Make the rebuttal safety check always fail.
    monkeypatch.setattr(rebuttal, "check_output", lambda text: GuardResult(False, text, "toxic"))

    state = await run()

    # The debate still finishes...
    assert state["status"] == "done"
    # ...but with no rebuttals.
    assert state["rebuttals"] == {}
    # 1 initial attempt + MAX_REBUTTAL_RETRIES retries, per persona, and no more.
    assert len(fake_llm.rebuttal_calls("left")) == 3


# When only one analyst's rebuttal fails, only that one is regenerated.
async def test_only_failing_rebuttals_are_regenerated(fake_llm, monkeypatch):
    # Remembers which analysts have already failed once.
    failed_once = set()

    # A fake safety check: fail the "right" analyst's first rebuttal and pass everything else.
    # Passed text is upper-cased to prove the guard-fixed text is the one that gets stored.
    def check(text):
        if text.startswith("right") and "right" not in failed_once:
            failed_once.add("right")
            return GuardResult(False, text, "toxic")
        return GuardResult(True, text.upper())

    monkeypatch.setattr(rebuttal, "check_output", check)

    state = await run()

    # "right" needed two attempts; "left" needed just one.
    assert len(fake_llm.rebuttal_calls("right")) == 2
    assert len(fake_llm.rebuttal_calls("left")) == 1
    # In the end all five rebuttals exist.
    assert set(state["rebuttals"]) == set(PERSONAS)
    assert state["rebuttals"]["left"] == "LEFT SAYS SOMETHING"   # guard-fixed text is what's stored

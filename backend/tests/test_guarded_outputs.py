import pytest  # the test framework

from backend.graph import guarded  # the retry-until-safe helper under test
from backend.graph.guardrails.common import GuardResult  # the result type a safety check returns
from backend.graph.nodes import agents, moderator  # the analyst and moderator node modules
from backend.graph.nodes.moderator import VERDICT_FALLBACK  # the text used when the verdict is blocked


# Builds a fake safety check that blocks any text containing one of the given words.
def blocking(*blocked_markers):
    """A check_output stub that blocks text containing any marker."""
    def check(text):
        # True if any marker appears in the text.
        blocked = any(m in text for m in blocked_markers)
        # passed = not blocked; the reason is "toxic" only when blocked.
        return GuardResult(not blocked, text, "toxic" if blocked else "")

    return check


# Two bad replies are retried, and the third (good) one is returned after the safety check fixed it.
def test_generate_guarded_retries_then_returns_validated_text(fake_llm, monkeypatch):
    # An iterator that gives out one reply per call: two bad, then a good one.
    replies = iter(["bad one", "bad two", "fine now"])
    monkeypatch.setattr("backend.config.llm.invoke", lambda **kw: next(replies))
    # The fake check passes only "fine now", and returns it upper-cased to prove the fixed text is the one returned.
    monkeypatch.setattr(guarded, "check_output", lambda t: GuardResult(t == "fine now", t.upper(), "toxic"))

    assert guarded.generate_guarded("s", "u", max_tokens=10, retries=2, label="x") == "FINE NOW"


# If every reply is blocked, the helper gives up and returns None after exactly 1 try + 2 retries.
def test_generate_guarded_gives_up_after_retries(fake_llm, monkeypatch):
    monkeypatch.setattr(guarded, "check_output", blocking("generic reply"))  # what the fake LLM says here
    assert guarded.generate_guarded("s", "u", max_tokens=10, retries=2, label="x") is None
    # 3 LLM calls in total.
    assert len(fake_llm.calls) == 3


# If an analyst's opening is blocked, that analyst is simply left out (the node returns no update).
def test_blocked_opening_leaves_the_persona_out(fake_llm, monkeypatch):
    # Block anything containing "says", which is in every fake analyst reply.
    monkeypatch.setattr(guarded, "check_output", blocking("says"))
    node = agents.make_debate_node("left")
    assert node({"topic": "T", "news_context": "c", "arguments": {}}) == {}


# When the reply is fine, it is returned under that analyst's name.
def test_passing_opening_is_returned(fake_llm):
    out = agents.make_debate_node("left")({"topic": "T", "news_context": "c", "arguments": {}})
    assert out == {"arguments": {"left": "left says something"}}


# If the moderator's verdict is blocked, the fixed fallback sentence is used and the debate still completes.
def test_verdict_falls_back_when_blocked(fake_llm, monkeypatch):
    monkeypatch.setattr(guarded, "check_output", blocking("balanced verdict"))
    out = moderator.moderator_node({"topic": "T", "arguments": {"left": "a"}, "rebuttals": {}})
    assert out["verdict"] == VERDICT_FALLBACK
    assert out["status"] == "done"


# With no arguments at all there is nothing to moderate, so the node must fail loudly, not invent a verdict.
def test_moderator_refuses_to_run_with_no_arguments(fake_llm):
    with pytest.raises(RuntimeError, match="nothing to moderate"):
        moderator.moderator_node({"topic": "T", "arguments": {}, "rebuttals": {}})

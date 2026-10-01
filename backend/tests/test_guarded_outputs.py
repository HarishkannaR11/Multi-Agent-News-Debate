import pytest

from backend.graph import guarded
from backend.graph.guardrails.common import GuardResult
from backend.graph.nodes import agents, moderator
from backend.graph.nodes.moderator import VERDICT_FALLBACK


def blocking(*blocked_markers):
    """A check_output stub that blocks text containing any marker."""
    def check(text):
        blocked = any(m in text for m in blocked_markers)
        return GuardResult(not blocked, text, "toxic" if blocked else "")

    return check


def test_generate_guarded_retries_then_returns_validated_text(fake_llm, monkeypatch):
    replies = iter(["bad one", "bad two", "fine now"])
    monkeypatch.setattr("backend.config.llm.invoke", lambda **kw: next(replies))
    monkeypatch.setattr(guarded, "check_output", lambda t: GuardResult(t == "fine now", t.upper(), "toxic"))

    assert guarded.generate_guarded("s", "u", max_tokens=10, retries=2, label="x") == "FINE NOW"


def test_generate_guarded_gives_up_after_retries(fake_llm, monkeypatch):
    monkeypatch.setattr(guarded, "check_output", blocking("generic reply"))  # what the fake LLM says here
    assert guarded.generate_guarded("s", "u", max_tokens=10, retries=2, label="x") is None
    assert len(fake_llm.calls) == 3


def test_blocked_opening_leaves_the_persona_out(fake_llm, monkeypatch):
    monkeypatch.setattr(guarded, "check_output", blocking("says"))
    node = agents.make_debate_node("left")
    assert node({"topic": "T", "news_context": "c", "arguments": {}}) == {}


def test_passing_opening_is_returned(fake_llm):
    out = agents.make_debate_node("left")({"topic": "T", "news_context": "c", "arguments": {}})
    assert out == {"arguments": {"left": "left says something"}}


def test_verdict_falls_back_when_blocked(fake_llm, monkeypatch):
    monkeypatch.setattr(guarded, "check_output", blocking("balanced verdict"))
    out = moderator.moderator_node({"topic": "T", "arguments": {"left": "a"}, "rebuttals": {}})
    assert out["verdict"] == VERDICT_FALLBACK
    assert out["status"] == "done"


def test_moderator_refuses_to_run_with_no_arguments(fake_llm):
    with pytest.raises(RuntimeError, match="nothing to moderate"):
        moderator.moderator_node({"topic": "T", "arguments": {}, "rebuttals": {}})

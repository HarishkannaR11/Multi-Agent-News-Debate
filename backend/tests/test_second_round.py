import pytest  # the test framework

from backend.config import settings  # the settings object (the second-round switch lives here)
from backend.graph.graph import build_graph, new_debate_state, route_after_review, run_config  # the pipeline helpers
from backend.graph.guardrails.common import GuardResult  # the result type a safety check returns
from backend.graph.nodes import second_round  # the module under test
from backend.graph.nodes.agents import PERSONAS  # the analyst prompts, keyed by analyst name
from backend.services import redis_service as rs  # Redis helpers, shortened to "rs"

# Apply the fake news fixture to every test in this file (so no real news API is called).
pytestmark = pytest.mark.usefixtures("fake_news")

# What the fake moderator answers when it wants one more round.
YES = '{"needs_second_round": true, "focus": "Who pays for the policy?"}'


# Helper: runs the whole pipeline once and returns the final state.
async def run():
    return await build_graph().ainvoke(new_debate_state(), config=run_config())


# Run once per (model reply, expected decision) pair: only a clean JSON true with a question counts.
@pytest.mark.parametrize("raw,expected", [
    (YES, (True, "Who pays for the policy?")),
    # Extra words and a code fence around the JSON are tolerated.
    ('Sure!\n```json\n' + YES + '\n```', (True, "Who pays for the policy?")),
    # Whitespace and newlines inside the question are collapsed.
    ('{"needs_second_round": true, "focus": "  Who\\n pays? "}', (True, "Who pays?")),
    # A clear "no".
    ('{"needs_second_round": false, "focus": ""}', (False, "")),
    # "true" as text or the number 1 do not count as a real true.
    ('{"needs_second_round": "true", "focus": "Q?"}', (False, "")),
    ('{"needs_second_round": 1, "focus": "Q?"}', (False, "")),
    # A "yes" with no question (or a non-text question) is useless, so it means no.
    ('{"needs_second_round": true, "focus": ""}', (False, "")),
    ('{"needs_second_round": true, "focus": 5}', (False, "")),
    # Broken or missing JSON means no.
    ("no json here", (False, "")),
    ('{"needs_second_round": true', (False, "")),
    ("[true]", (False, "")),
])
def test_parse_review(raw, expected):
    assert second_round.parse_review(raw) == expected


# An over-long question is cut to the limit.
def test_parse_review_caps_the_focus_length():
    needs, focus = second_round.parse_review('{"needs_second_round": true, "focus": "' + "a" * 1000 + '"}')
    assert needs and len(focus) == second_round.MAX_FOCUS_CHARS


# The router only sends the graph to the extra round when the review asked for it.
def test_route_after_review():
    assert route_after_review({"second_round": True}) == "crossfire"
    assert route_after_review({"second_round": False}) == "moderator"
    assert route_after_review({}) == "moderator"


# When the moderator asks for it, every analyst answers once and the verdict sees those answers.
async def test_second_round_runs_when_the_moderator_asks(fake_llm):
    fake_llm.review_reply = YES

    state = await run()

    assert state["status"] == "done"
    assert state["focus"] == "Who pays for the policy?"
    # All five analysts gave a closing statement.
    assert set(state["crossfire"]) == set(PERSONAS)
    # The moderator's verdict prompt contained the closing statements.
    verdict_call = [c for c in fake_llm.calls if "Write the verdict now." in c["user"]][-1]
    assert "Closing statement" in verdict_call["user"] and "Who pays for the policy?" in verdict_call["user"]
    # Exactly one extra call per analyst, and the round ran only once.
    closings = [c for c in fake_llm.calls if "closing statement" in c["user"]]
    assert len(closings) == len(PERSONAS)


# When the moderator says no, there is no extra round and nothing extra is stored.
async def test_no_second_round_when_the_moderator_declines(fake_llm):
    state = await run()

    assert state["status"] == "done"
    assert state["crossfire"] == {} and state["focus"] == ""
    assert not [c for c in fake_llm.calls if "closing statement" in c["user"]]


# The feature can be switched off: the moderator is not even asked.
async def test_switch_off_skips_the_review(fake_llm, monkeypatch):
    fake_llm.review_reply = YES
    monkeypatch.setattr(settings, "SECOND_ROUND_ENABLED", False)

    state = await run()

    assert state["crossfire"] == {}
    assert not [c for c in fake_llm.calls if "needs_second_round" in c["system"]]


# If the review call fails, the debate still completes normally.
async def test_review_failure_does_not_fail_the_debate(fake_llm, monkeypatch):
    original = fake_llm.__call__

    def flaky(system, user, max_tokens=1024, fast=False):
        if "needs_second_round" in system:
            raise RuntimeError("groq hiccup")
        return original(system, user, max_tokens, fast)

    monkeypatch.setattr("backend.config.llm.invoke", flaky)

    state = await run()

    assert state["status"] == "done" and state["crossfire"] == {}


# A focus question that the content filter blocks is never published, and no extra round runs.
async def test_blocked_focus_question_skips_the_round(fake_llm, monkeypatch):
    fake_llm.review_reply = YES
    monkeypatch.setattr(second_round, "check_output", lambda text: GuardResult(False, text, "toxic"))

    state = await run()

    assert state["status"] == "done"
    assert state["focus"] == "" and state["crossfire"] == {}


# Closing statements that fail the content filter are dropped (and not retried).
async def test_blocked_closing_statements_are_dropped(fake_llm, monkeypatch):
    fake_llm.review_reply = YES
    # Block the "left" analyst's closing statement (its text starts with "left"), pass everything else.
    monkeypatch.setattr(
        second_round, "check_output",
        lambda text: GuardResult(not text.startswith("left"), text, "toxic"),
    )

    state = await run()

    assert set(state["crossfire"]) == set(PERSONAS) - {"left"}


# The second round survives saving to Redis and loading back.
async def test_second_round_is_stored(fake_redis):
    final = {"status": "done", "topic": "T", "verdict": "V", "arguments": {"left": "a"}, "rebuttals": {},
             "bias_scores": {}, "focus": "Q?", "crossfire": {"left": "closing"}}
    await rs.save_debate("2026-09-30", "t", final)

    stored = await rs.get_debate("2026-09-30", "t")

    assert stored["focus"] == "Q?" and stored["crossfire"] == {"left": "closing"}


# Debates saved before this feature existed still load, with empty second-round fields.
async def test_old_debates_have_an_empty_second_round(fake_redis):
    await fake_redis.hset("debate:2026-09-01:old", mapping={"topic": "Old", "status": "done"})

    stored = await rs.get_debate("2026-09-01", "old")

    assert stored["focus"] == "" and stored["crossfire"] == {}

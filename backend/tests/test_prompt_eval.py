import pytest  # the test framework

from backend.evals import prompt_eval  # the evaluation helpers under test
from backend.graph.graph import build_graph, new_debate_state, run_config  # the real pipeline (with a fake LLM)

# Apply the fake news fixture to every test in this file.
pytestmark = pytest.mark.usefixtures("fake_news")


# A well-formed debate result that passes every check.
def good_state(**overrides):
    state = {
        "status": "done", "topic": "Should X happen?",
        "arguments": {key: "A reasoned opening." for key in prompt_eval.PERSONA_KEYS},
        "rebuttals": {key: "A reasoned rebuttal." for key in prompt_eval.PERSONA_KEYS},
        "verdict": "A balanced verdict.",
        "bias_scores": {"left": 0.7, "right": 0.6, "economist": 0.2, "geopolitical": 0.3, "devil": 0.4},
        "focus": "", "crossfire": {},
    }
    return state | overrides


def test_a_good_debate_has_no_problems():
    assert prompt_eval.check_debate(good_state()) == []


# Run once per (what is wrong, text that must appear in the problem list).
@pytest.mark.parametrize("overrides,expected", [
    ({"status": "debating"}, "status"),
    ({"topic": ""}, "topic is empty"),
    ({"topic": "x" * 300}, "topic is 300"),
    ({"arguments": {"left": "ok"}}, "right: no opening"),
    ({"arguments": {k: "As an AI, I cannot do that." for k in prompt_eval.PERSONA_KEYS}}, "refusal"),
    ({"rebuttals": {"left": "only one"}}, "rebuttals present"),
    ({"verdict": ""}, "verdict is empty"),
    ({"verdict": prompt_eval.VERDICT_FALLBACK}, "fallback"),
    ({"bias_scores": {"left": 0.5}}, "missing"),
    ({"bias_scores": {k: 0.5 for k in prompt_eval.PERSONA_KEYS}}, "about the same"),
    ({"bias_scores": {"left": 1.5, "right": 0.1, "economist": 0.2, "geopolitical": 0.3, "devil": 0.4}}, "outside 0..1"),
    ({"focus": "A question?"}, "half there"),
    ({"crossfire": {"left": "answer"}}, "half there"),
])
def test_problems_are_reported(overrides, expected):
    problems = prompt_eval.check_debate(good_state(**overrides))
    assert any(expected in problem for problem in problems), problems


# The checks also accept a complete second round.
def test_a_complete_second_round_is_fine():
    state = good_state(focus="Who pays?", crossfire={"left": "I say the city."})
    assert prompt_eval.check_debate(state) == []


# The output of the fake-LLM pipeline passes the checks, so the checker and the pipeline agree on the shape.
async def test_pipeline_output_passes_the_checks(fake_llm):
    state = await build_graph().ainvoke(new_debate_state(), config=run_config())
    assert prompt_eval.check_debate(state) == []


# Without an API key the tool explains itself and exits with code 2 instead of failing mid-run.
def test_main_requires_an_api_key(monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["prompt_eval"])
    assert prompt_eval.main() == 2
    assert "GROQ_API_KEY" in capsys.readouterr().err

"""Quality check for the prompts, run by hand against the real LLM (it is NOT part of CI).

    GROQ_API_KEY=... python -m backend.evals.prompt_eval            # all sample articles
    GROQ_API_KEY=... python -m backend.evals.prompt_eval --keep-guardrails

For each fixed sample article it runs the real debate graph and checks the shape and sanity of the
output: lengths, every analyst present, valid bias scores that are not all identical, a real verdict,
and a consistent second round. News APIs are replaced by the samples and nothing is saved to Redis, so
the only cost is the LLM calls (about 14 per article). Exit code 1 when any check fails.
"""
import argparse  # reads command-line options
import asyncio  # runs the async graph
import sys  # exit codes and output

from ..config import PERSONA_KEYS, settings  # analyst names and the settings object
from ..graph.graph import build_graph, new_debate_state, run_config  # build and start the pipeline
from ..graph.nodes import fetcher  # the news step (its network calls are replaced by the samples)
from ..graph.nodes.moderator import VERDICT_FALLBACK  # the text used when the verdict was blocked

# Invented sample articles, so the evaluation is repeatable and needs no news API key.
SAMPLES = [
    {
        "title": "City council approves congestion charge for downtown drivers",
        "description": "Drivers entering the downtown core will pay 12 dollars a day from next year.",
        "content": "The council voted 7-4 to introduce the charge, saying revenue will fund bus lanes. "
                   "Business groups warn of lost foot traffic; environmental groups call it overdue.",
        "url": "https://example.test/congestion-charge",
    },
    {
        "title": "Central bank holds interest rates as inflation cools",
        "description": "Policymakers kept the benchmark rate unchanged and signalled possible cuts later this year.",
        "content": "Inflation fell to 2.8 percent, the lowest in two years, while unemployment edged up to 4.4 percent."
                   " "
                   "Economists are split on whether cuts will come before the summer.",
        "url": "https://example.test/rates-hold",
    },
    {
        "title": "Two countries agree to joint patrols along disputed shipping lane",
        "description": "The neighbours announced a six-month trial after a series of near collisions.",
        "content": "Officials said the patrols aim to reduce incidents, but analysts note the agreement leaves the "
                   "underlying territorial claims untouched.",
        "url": "https://example.test/joint-patrols",
    },
]

# Phrases that show the model refused or broke character instead of writing an argument.
REFUSAL_MARKERS = ("as an ai", "i cannot", "i can't help", "i'm sorry, but")
# Upper limits (in characters) that catch runaway or cut-off output.
MAX_TOPIC_CHARS = 250
MAX_ARGUMENT_CHARS = 2500
MAX_VERDICT_CHARS = 2500
# The bias scores must differ at least this much between the most and least slanted analyst.
MIN_BIAS_SPREAD = 0.05


# Checks one finished debate state and returns a list of problems (an empty list = all good).
def check_debate(state: dict) -> list[str]:
    problems: list[str] = []

    # The run must finish.
    if state.get("status") != "done":
        problems.append(f"status is {state.get('status')!r}, expected 'done'")

    # The topic: present and short.
    topic = (state.get("topic") or "").strip()
    if not topic:
        problems.append("topic is empty")
    elif len(topic) > MAX_TOPIC_CHARS:
        problems.append(f"topic is {len(topic)} characters long")

    # Every analyst wrote a sensible opening argument.
    arguments = state.get("arguments") or {}
    for key in PERSONA_KEYS:
        text = (arguments.get(key) or "").strip()
        if not text:
            problems.append(f"{key}: no opening argument")
        elif len(text) > MAX_ARGUMENT_CHARS:
            problems.append(f"{key}: opening is {len(text)} characters long")
        elif any(marker in text.lower() for marker in REFUSAL_MARKERS):
            problems.append(f"{key}: opening looks like a refusal")

    # Rebuttals: dropping one is allowed (guardrails), dropping most is not.
    if len(state.get("rebuttals") or {}) < len(PERSONA_KEYS) - 1:
        problems.append(f"only {len(state.get('rebuttals') or {})} of {len(PERSONA_KEYS)} rebuttals present")

    # The verdict: a real one, not the fallback text.
    verdict = (state.get("verdict") or "").strip()
    if not verdict:
        problems.append("verdict is empty")
    elif verdict == VERDICT_FALLBACK:
        problems.append("verdict was blocked and replaced by the fallback text")
    elif len(verdict) > MAX_VERDICT_CHARS:
        problems.append(f"verdict is {len(verdict)} characters long")

    # Bias scores: all five analysts, numbers in 0..1, and not all identical.
    scores = state.get("bias_scores") or {}
    missing = [key for key in PERSONA_KEYS if key not in scores]
    if missing:
        problems.append(f"bias scores missing for {', '.join(missing)}")
    elif max(scores.values()) - min(scores.values()) < MIN_BIAS_SPREAD:
        problems.append(f"bias scores are all about the same: {scores}")
    if any(not 0.0 <= value <= 1.0 for value in scores.values()):
        problems.append(f"bias score outside 0..1: {scores}")

    # The optional second round must be consistent: a question iff there are answers.
    focus, crossfire = state.get("focus") or "", state.get("crossfire") or {}
    if bool(focus) != bool(crossfire):
        problems.append("second round is half there (question without answers, or the reverse)")

    return problems


# Runs the real graph on one sample article and returns the final state.
async def run_sample(article: dict) -> dict:
    # Replace the news APIs with this one article.
    fetcher._fetch_newsapi = lambda: [article]
    fetcher._fetch_gnews = lambda: []
    return await build_graph().ainvoke(new_debate_state(), config=run_config())


# Entry point: evaluates every sample and prints a report.
def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--keep-guardrails", action="store_true",
                        help="leave the content filters on (slower; needs the guardrail models)")
    args = parser.parse_args()

    # Without a key every call would fail; say so clearly instead.
    if not settings.GROQ_API_KEY:
        print("GROQ_API_KEY is not set; this evaluation calls the real LLM.", file=sys.stderr)
        return 2
    # The content filters are tested elsewhere and need heavy models, so they are off unless asked for.
    settings.GUARDRAILS_ENABLED = args.keep_guardrails

    failures = 0
    for article in SAMPLES:
        print(f"\n=== {article['title']}")
        state = asyncio.run(run_sample(article))
        problems = check_debate(state)
        print(f"topic:   {state.get('topic')}")
        print(f"verdict: {(state.get('verdict') or '')[:160]}")
        print(f"second round: {'yes - ' + state['focus'] if state.get('focus') else 'no'}")
        print(f"bias:    {state.get('bias_scores')}")
        if problems:
            failures += 1
            print("PROBLEMS:")
            for problem in problems:
                print(f"  - {problem}")
        else:
            print("OK")

    print(f"\n{len(SAMPLES) - failures}/{len(SAMPLES)} samples passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

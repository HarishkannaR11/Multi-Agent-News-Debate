from functools import lru_cache  # decorator that remembers a function's result so it runs only once

from langgraph.graph import StateGraph  # the LangGraph class used to describe the workflow as a graph

from ..config import settings  # the shared app settings
from .nodes.agents import PARALLEL_PERSONAS, make_debate_node  # analyst names + the function that builds analyst nodes
from .nodes.extractor import topic_extractor_node  # the step that turns the article into a topic
from .nodes.fetcher import fetch_news_node  # the step that downloads and filters the news
from .nodes.moderator import moderator_node  # the step that writes the verdict and bias scores
from .nodes.rebuttal import rebuttal_node  # the step where analysts rebut each other
from .state import DebateState  # the shared state shape


# Builds the starting state that a debate run begins with.
def new_debate_state(seen_urls: list[str] | None = None) -> DebateState:
    # Return a dict with every field set to an empty/initial value.
    return {
        # No topic yet.
        "topic": "",
        # Date is filled in by the fetch step.
        "date": "",
        # No article link yet.
        "source_url": "",
        # Copy the list of recently used article URLs (or an empty list if none were given).
        "seen_urls": list(seen_urls or []),
        # No article text yet.
        "news_context": "",
        # Round 1 = opening arguments.
        "round": 1,
        # No arguments written yet.
        "arguments": {},
        # No rebuttals written yet.
        "rebuttals": {},
        # No rebuttal retries used yet.
        "rebuttal_retries": 0,
        # Article has not been checked yet.
        "guardrail_input_pass": False,
        # Rebuttal step has not finished yet.
        "guardrail_output_pass": False,
        # No verdict yet.
        "verdict": "",
        # No bias scores yet.
        "bias_scores": {},
        # The first stage is fetching the news.
        "status": "fetching",
    }


# Settings passed to LangGraph each time the graph runs.
def run_config(date: str = "") -> dict:
    # Always cap supersteps: a stuck retry loop must fail fast, not burn LLM calls.
    # run_name/tags label the trace in LangSmith (no-op when tracing is off).
    return {
        # Stop with an error if the graph takes more than this many steps.
        "recursion_limit": settings.GRAPH_RECURSION_LIMIT,
        # Name shown for this run in tracing tools.
        "run_name": "daily_debate",
        # Labels for filtering runs: always "daily_debate", plus the date when we have one.
        "tags": ["daily_debate", date] if date else ["daily_debate"],
    }


# Decides which step comes after the rebuttal step.
def route_after_rebuttal(state: DebateState) -> str:
    # If the rebuttal step says it is finished, go on to the moderator; otherwise loop back to rebuttal.
    return "moderator" if state["guardrail_output_pass"] else "rebuttal"


# Builds and compiles the whole debate workflow.
def _build():
    # Start a new graph whose shared state has the DebateState shape.
    g = StateGraph(DebateState)

    # Register each step ("node") under a name, linked to the function that runs it.
    g.add_node("fetch",     fetch_news_node)
    g.add_node("extract",   topic_extractor_node)
    # Create one analyst node per persona (the four parallel ones plus the devil's advocate).
    for persona in (*PARALLEL_PERSONAS, "devil"):
        g.add_node(persona, make_debate_node(persona))
    g.add_node("rebuttal",  rebuttal_node)
    g.add_node("moderator", moderator_node)

    # The graph starts at the fetch step.
    g.set_entry_point("fetch")
    # After fetching, extract the topic.
    g.add_edge("fetch", "extract")

    # Parallel fan-out; the devil's advocate waits for all four so it can attack their arguments.
    # After the topic is ready, all four analysts start at the same time.
    for persona in PARALLEL_PERSONAS:
        g.add_edge("extract", persona)
    # The devil's advocate starts only after ALL four analysts have finished (fan-in).
    g.add_edge(list(PARALLEL_PERSONAS), "devil")
    # After the devil's advocate, move on to the rebuttals.
    g.add_edge("devil", "rebuttal")

    # Guardrail failures retry only the failing rebuttals; the node itself caps the retries.
    # After rebuttals, a function decides: go to the moderator, or run the rebuttal step again.
    g.add_conditional_edges("rebuttal", route_after_rebuttal,
                            {"moderator": "moderator", "rebuttal": "rebuttal"})
    # The moderator is the last step; the run ends there.
    g.set_finish_point("moderator")

    # Turn the description into a runnable graph.
    return g.compile()


# Build the graph only once and reuse it for every later call.
@lru_cache(maxsize=1)
def build_graph():
    # Delegate to the real builder (cached by the decorator above).
    return _build()

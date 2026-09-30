from functools import lru_cache

from langgraph.graph import StateGraph

from .state import DebateState
from .nodes.fetcher import fetch_news_node
from .nodes.extractor import topic_extractor_node
from .nodes.agents import PARALLEL_PERSONAS, make_debate_node
from .nodes.rebuttal import rebuttal_node
from .nodes.moderator import moderator_node
from ..config import settings


def new_debate_state(seen_urls: list[str] | None = None) -> DebateState:
    return {
        "topic": "",
        "date": "",
        "source_url": "",
        "seen_urls": list(seen_urls or []),
        "news_context": "",
        "round": 1,
        "arguments": {},
        "rebuttals": {},
        "rebuttal_retries": 0,
        "guardrail_input_pass": False,
        "guardrail_output_pass": False,
        "verdict": "",
        "bias_scores": {},
        "status": "fetching",
    }


def run_config() -> dict:
    # Always cap supersteps: a stuck retry loop must fail fast, not burn LLM calls.
    return {"recursion_limit": settings.GRAPH_RECURSION_LIMIT}


def route_after_rebuttal(state: DebateState) -> str:
    return "moderator" if state["guardrail_output_pass"] else "rebuttal"


def _build():
    g = StateGraph(DebateState)

    g.add_node("fetch",     fetch_news_node)
    g.add_node("extract",   topic_extractor_node)
    for persona in (*PARALLEL_PERSONAS, "devil"):
        g.add_node(persona, make_debate_node(persona))
    g.add_node("rebuttal",  rebuttal_node)
    g.add_node("moderator", moderator_node)

    g.set_entry_point("fetch")
    g.add_edge("fetch", "extract")

    # Parallel fan-out; the devil's advocate waits for all four so it can attack their arguments.
    for persona in PARALLEL_PERSONAS:
        g.add_edge("extract", persona)
    g.add_edge(list(PARALLEL_PERSONAS), "devil")
    g.add_edge("devil", "rebuttal")

    # Guardrail failures retry only the failing rebuttals; the node itself caps the retries.
    g.add_conditional_edges("rebuttal", route_after_rebuttal,
                            {"moderator": "moderator", "rebuttal": "rebuttal"})
    g.set_finish_point("moderator")

    return g.compile()


@lru_cache(maxsize=1)
def build_graph():
    return _build()

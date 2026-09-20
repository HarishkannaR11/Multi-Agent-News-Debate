from langgraph.graph import StateGraph

from .state import DebateState
from .nodes.fetcher import fetch_news_node
from .nodes.extractor import topic_extractor_node
from .nodes.agents import make_debate_node
from .nodes.rebuttal import rebuttal_node
from .nodes.moderator import moderator_node


def build_graph():
    g = StateGraph(DebateState)

    g.add_node("fetch",     fetch_news_node)
    g.add_node("extract",   topic_extractor_node)
    g.add_node("left",      make_debate_node("left"))
    g.add_node("right",     make_debate_node("right"))
    g.add_node("economist", make_debate_node("economist"))
    g.add_node("geo",       make_debate_node("geopolitical"))
    g.add_node("devil",     make_debate_node("devil"))
    g.add_node("rebuttal",  rebuttal_node)
    g.add_node("moderator", moderator_node)

    g.set_entry_point("fetch")
    g.add_edge("fetch",   "extract")

    # Parallel fan-out
    for agent in ["left", "right", "economist", "geo", "devil"]:
        g.add_edge("extract", agent)
        g.add_edge(agent, "rebuttal")

    # Conditional: output guardrail pass (or retries exhausted) → moderator, else retry
    g.add_conditional_edges("rebuttal",
        lambda s: "moderator" if s["guardrail_output_pass"] else "rebuttal",
        {"moderator": "moderator", "rebuttal": "rebuttal"}
    )
    g.set_finish_point("moderator")

    return g.compile()

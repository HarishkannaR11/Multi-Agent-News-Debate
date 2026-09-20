from ..state import DebateState
from ...config import llm

EXTRACTOR_SYSTEM = """You distill a news article into a single, debatable
one-sentence topic statement. Be neutral and specific. Respond with only the
topic sentence, no preamble."""


def topic_extractor_node(state: DebateState) -> DebateState:
    prompt = f"Article:\n{state['news_context']}\n\nExtract the debate topic."
    state["topic"] = llm.invoke(system=EXTRACTOR_SYSTEM, user=prompt, max_tokens=100).strip()
    state["status"] = "debating"
    return state

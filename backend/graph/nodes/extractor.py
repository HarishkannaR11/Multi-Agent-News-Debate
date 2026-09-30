from ..prompts import UNTRUSTED_NOTE, article_block
from ..state import DebateState
from ...config import llm

EXTRACTOR_SYSTEM = """You distill a news article into a single, debatable
one-sentence topic statement. Be neutral and specific. Respond with only the
topic sentence, no preamble.""" + UNTRUSTED_NOTE


def topic_extractor_node(state: DebateState) -> dict:
    prompt = f"{article_block(state['news_context'])}\n\nExtract the debate topic."
    topic = llm.invoke(system=EXTRACTOR_SYSTEM, user=prompt, max_tokens=100, fast=True)
    return {"topic": topic, "status": "debating"}

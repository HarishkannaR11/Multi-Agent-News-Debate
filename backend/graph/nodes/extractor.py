from ...config import llm  # the shared wrapper used for every LLM call
from ..prompts import UNTRUSTED_NOTE, article_block  # prompt-safety helpers
from ..state import DebateState  # the shared state shape

# Instructions for the model: turn the article into one neutral, debatable sentence, plus the security note.
EXTRACTOR_SYSTEM = """You distill a news article into a single, debatable
one-sentence topic statement. Be neutral and specific. Respond with only the
topic sentence, no preamble.""" + UNTRUSTED_NOTE


# Graph step: reads the article and writes the debate topic into the state.
def topic_extractor_node(state: DebateState) -> dict:
    # The message sent to the model: the fenced article text and the request.
    prompt = f"{article_block(state['news_context'])}\n\nExtract the debate topic."
    # Ask the small, fast model (this is a cheap step) for at most 100 tokens.
    topic = llm.invoke(system=EXTRACTOR_SYSTEM, user=prompt, max_tokens=100, fast=True)
    # Save the topic and mark the next stage as "debating".
    return {"topic": topic, "status": "debating"}

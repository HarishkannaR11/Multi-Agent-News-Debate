from typing import Annotated, TypedDict  # Annotated attaches extra info to a type; TypedDict describes a dict's keys


# A "reducer": tells LangGraph how to combine two values written to the same key at the same time.
def merge_dicts(left: dict, right: dict) -> dict:
    """Reducer so parallel nodes can each contribute keys to the same dict."""
    # Merge both dicts into a new one (right wins on clashes); "or {}" guards against None.
    return {**(left or {}), **(right or {})}


# The shared "notebook" every node in the graph reads from and writes to.
# total=False means every key is optional (nodes fill them in over time).
class DebateState(TypedDict, total=False):
    # The one-sentence debate topic.
    topic: str
    # The day this debate belongs to, e.g. "2026-10-01".
    date: str
    # Link to the news article that was used.
    source_url: str
    seen_urls: list             # article URLs already debated recently; the fetcher skips them
    news_context: str           # Raw article text, capped at MAX_NEWS_CONTEXT_CHARS
    round: int                  # 1 = opening, 2 = rebuttal
    # Each analyst's opening argument. The reducer merges what parallel nodes write.
    arguments: Annotated[dict, merge_dicts]   # { "left": "...", "right": "...", ... }
    rebuttals: dict             # { "left": "...", "right": "...", ... }
    # The moderator's question for the optional second round, and whether that round should run.
    focus: str
    second_round: bool
    crossfire: dict             # { "left": "closing statement", ... } from the optional second round
    # How many times blocked rebuttals have been regenerated (must be declared here or LangGraph drops it).
    rebuttal_retries: int
    # Did the news article pass the input content filter?
    guardrail_input_pass: bool
    # True when the rebuttal step is finished and the graph may move on to the moderator.
    guardrail_output_pass: bool
    # The moderator's final summary.
    verdict: str
    bias_scores: dict           # { "left": 0.72, "right": 0.68, ... }
    status: str                 # fetching | debating | rebuttal | verdict | done

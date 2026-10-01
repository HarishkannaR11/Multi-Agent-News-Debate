from typing import Annotated, TypedDict


def merge_dicts(left: dict, right: dict) -> dict:
    """Reducer so parallel nodes can each contribute keys to the same dict."""
    return {**(left or {}), **(right or {})}


class DebateState(TypedDict, total=False):
    topic: str
    date: str
    source_url: str
    seen_urls: list             # article URLs already debated recently; the fetcher skips them
    news_context: str           # Raw article text, capped at MAX_NEWS_CONTEXT_CHARS
    round: int                  # 1 = opening, 2 = rebuttal
    arguments: Annotated[dict, merge_dicts]   # { "left": "...", "right": "...", ... }
    rebuttals: dict             # { "left": "...", "right": "...", ... }
    rebuttal_retries: int
    guardrail_input_pass: bool
    guardrail_output_pass: bool
    verdict: str
    bias_scores: dict           # { "left": 0.72, "right": 0.68, ... }
    status: str                 # fetching | debating | rebuttal | verdict | done

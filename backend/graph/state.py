from typing import TypedDict, Optional


class DebateState(TypedDict):
    topic: str
    date: str
    news_context: str           # Raw article text, max 2000 tokens
    round: int                  # 1 = opening, 2 = rebuttal
    arguments: dict             # { "left": "...", "right": "...", ... }
    rebuttals: dict             # { "left": "...", "right": "...", ... }
    guardrail_input_pass: bool
    guardrail_output_pass: bool
    verdict: str
    bias_scores: dict           # { "left": 0.72, "right": 0.68, ... }
    status: str                 # fetching | debating | rebuttal | verdict | done

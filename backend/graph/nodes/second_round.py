import json  # parses JSON text into Python objects
import logging  # Python's built-in logging system
import re  # regular expressions (pattern matching on text)
from concurrent.futures import ThreadPoolExecutor  # runs several tasks at the same time in threads

from ...config import llm, settings  # the shared LLM wrapper and app settings
from ..guardrails.output_guard import check_output  # content filter for text the AI wrote
from ..prompts import UNTRUSTED_NOTE  # prompt-safety note appended to system prompts
from ..state import DebateState  # the shared state shape
from .agents import PERSONAS  # the five analyst system prompts
from .moderator import debate_transcript  # turns the debate so far into one text transcript

# A logger named after this module.
logger = logging.getLogger(__name__)

# Longest "focus question" we accept from the model (it is shown to readers, so keep it short).
MAX_FOCUS_CHARS = 300

# Instructions for the moderator's decision step. It must answer with JSON only so the code can parse it.
REVIEW_SYSTEM = """You are the debate moderator. Read the transcript and decide whether the debate
needs ONE more round before you write your verdict.
Answer needs_second_round = true ONLY if the analysts disagree about a specific point that none of
them has actually resolved, or an important claim went unchallenged. Otherwise answer false.
Respond with ONLY a JSON object like
{"needs_second_round": true, "focus": "One sentence question the analysts must answer."}
Use an empty string for focus when needs_second_round is false."""

# Instructions added to each analyst's own persona prompt for the extra round.
CLOSING_TASK = """The moderator wants one more round. Write a closing statement of at most 80 words that
directly answers the moderator's focus question from your own perspective. Concede a point if the
other analysts made a good one."""


# Safely reads the moderator's decision from its reply (never trust model output as clean data).
def parse_review(raw: str) -> tuple[bool, str]:
    """Return (needs_second_round, focus). Anything malformed means 'no second round'."""
    # Find the first "{ ... }" block in the reply (the model may add extra words around it).
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    # No JSON-looking block: no second round.
    if not match:
        return False, ""
    try:
        # Parse that block as JSON.
        data = json.loads(match.group(0))
    # Invalid JSON: no second round.
    except json.JSONDecodeError:
        return False, ""
    # It must be a JSON object (a dict), not a list or number.
    if not isinstance(data, dict):
        return False, ""
    # Only a real JSON true counts; the text "true" or the number 1 do not.
    if data.get("needs_second_round") is not True:
        return False, ""
    # The focus question must be text.
    focus = data.get("focus")
    if not isinstance(focus, str):
        return False, ""
    # Collapse whitespace/newlines and cut to the length limit.
    focus = " ".join(focus.split())[:MAX_FOCUS_CHARS].strip()
    # A second round without a question to answer makes no sense.
    return (True, focus) if focus else (False, "")


# Graph step: the moderator decides whether the analysts need one more round.
def review_node(state: DebateState) -> dict:
    """Ask the moderator model whether a second round is needed. This optional step never fails the debate."""
    # The feature can be switched off, and one analyst alone cannot have a debate.
    if not settings.SECOND_ROUND_ENABLED or len(state.get("arguments") or {}) < 2:
        return {"second_round": False, "focus": ""}
    try:
        # Ask the small, fast model to read the transcript and answer with JSON.
        raw = llm.invoke(
            system=REVIEW_SYSTEM,
            user=f"Topic: {state['topic']}\n\nTranscript:\n{debate_transcript(state)}",
            max_tokens=200,
            fast=True,
        )
    # This step is an optional extra: if the model call fails, carry on with the normal debate.
    except Exception:
        logger.exception("Second-round review failed; continuing without a second round")
        return {"second_round": False, "focus": ""}
    # Read the decision.
    needs, focus = parse_review(raw)
    # The focus question is shown to readers, so it must pass the same content filter as everything else.
    if needs and not check_output(focus).passed:
        logger.warning("Second-round focus question blocked by output guardrail; skipping the round")
        return {"second_round": False, "focus": ""}
    # Record the decision (and the filtered question).
    return {"second_round": needs, "focus": focus}


# Writes ONE analyst's closing statement (one LLM call).
def _closing(persona_key: str, state: DebateState) -> str:
    # The message: topic, the moderator's question, and the whole debate so far.
    prompt = f"""News topic: {state['topic']}

Moderator's focus question: {state['focus']}

Debate so far:
{debate_transcript(state)}

{CLOSING_TASK}"""
    # Call the main model with this analyst's instructions (plus the security note) and return the text.
    return llm.invoke(system=PERSONAS[persona_key] + UNTRUSTED_NOTE, user=prompt, max_tokens=250)


# Graph step: every analyst answers the moderator's focus question once. This runs at most once per debate.
def crossfire_node(state: DebateState) -> dict:
    """Closing statements for the moderator's focus question; blocked ones are dropped, never retried."""
    # Analysts that have an opening argument.
    todo = [key for key in PERSONAS if key in state["arguments"]]
    # Run the LLM calls in parallel threads (they mostly wait on the network).
    with ThreadPoolExecutor(max_workers=max(1, len(todo))) as pool:
        # Pair each analyst name with its closing text; strict=True checks both lists are the same length.
        drafts = dict(zip(todo, pool.map(lambda key: _closing(key, state), todo), strict=True))
    # Statements that pass the content filter are collected here.
    kept: dict[str, str] = {}
    # Check each draft one at a time (the content-filter model is not meant for concurrent use).
    for key, draft in drafts.items():
        result = check_output(draft)
        # Approved: keep the cleaned text.
        if result.passed:
            kept[key] = result.text
        # Blocked: log and drop it (it is an optional extra, so no retry loop).
        else:
            logger.warning("Closing statement %r failed output guardrail: %s", key, result.reason)
    # Save the statements.
    return {"crossfire": kept}

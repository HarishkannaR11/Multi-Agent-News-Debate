import re  # regular expressions (pattern matching on text)

from ...config import llm  # the shared wrapper used for every LLM call
from ..prompts import UNTRUSTED_NOTE, opinion_block  # prompt-safety helpers

# Short instructions for the model, plus the security note about untrusted text.
OPINION_SYSTEM = (
    "You are a balanced opinion analyst who deepens the user's thinking about a news debate."
    + UNTRUSTED_NOTE
)

# The prompt template. Words in {curly braces} are filled in with the real debate and opinion below.
OPINION_PROMPT = """
You are a balanced opinion analyst.

Debate context:
- Topic: {topic}
- Left analyst: {left}
- Right analyst: {right}
- Economist: {economist}
- Geopolitical: {geo}
- Devil's advocate: {devil}
- Moderator verdict: {verdict}

User's opinion:
{user_opinion}

Step 1: Detect mode.
  - AGREE      → user's view aligns with one or more agents
  - CHALLENGE  → user contradicts agent arguments
  - EXPAND     → user raises an angle the agents missed

Step 2: Respond in that mode.
  - AGREE      → validate + strengthen with debate evidence
  - CHALLENGE  → respectfully counter using agent arguments
  - EXPAND     → acknowledge their angle + add what agents missed

Rules:
- Never say the user is wrong
- Cite which agent you are referencing
- Max 3 paragraphs
- End with one follow-up question to deepen their thinking
- State detected mode in first line: [Mode: AGREE / CHALLENGE / EXPAND]
"""


# Takes a stored debate and a user's opinion, and returns the AI's reply split into parts.
def handle_opinion(debate: dict, user_opinion: str) -> dict:
    # The analysts' arguments from the stored debate (empty dict if missing).
    args = debate.get("arguments", {})
    # Fill the template with the debate details and the (fenced) opinion.
    prompt = OPINION_PROMPT.format(
        # The debate topic.
        topic=debate.get("topic", ""),
        # Each analyst's argument (empty text if missing).
        left=args.get("left", ""),
        right=args.get("right", ""),
        economist=args.get("economist", ""),
        geo=args.get("geopolitical", ""),
        devil=args.get("devil", ""),
        # The moderator's verdict.
        verdict=debate.get("verdict", ""),
        # The user's opinion wrapped in <user_opinion> tags.
        user_opinion=opinion_block(user_opinion),
    )
    # Ask the main model for the reply (up to 500 tokens).
    response = llm.invoke(system=OPINION_SYSTEM, user=prompt, max_tokens=500)
    # Look for the "[Mode: ...]" tag the model was told to write on its first line.
    match = re.search(r"\[Mode:\s*(AGREE|CHALLENGE|EXPAND)\]", response, re.IGNORECASE)
    # Use the detected mode in upper case, or "EXPAND" if the tag is missing.
    mode = match.group(1).upper() if match else "EXPAND"
    # Remove the mode tag from the start so only the real reply remains.
    body = re.sub(r"^\[Mode:.*?\]\s*", "", response, flags=re.IGNORECASE).strip()

    # The follow-up question starts empty.
    followup = ""
    # Split the reply into sentences (after ".", "?" or "!" followed by whitespace).
    sentences = re.split(r"(?<=[.?!])\s+", body)
    # If the last sentence is a question...
    if sentences and sentences[-1].strip().endswith("?"):
        # ...take it as the follow-up question...
        followup = sentences[-1].strip()
        # ...and cut it off the end of the main reply.
        body = body[: -len(followup)].strip()

    # Return the mode, the reply text and the follow-up question.
    return {"mode": mode, "response": body, "followup": followup}

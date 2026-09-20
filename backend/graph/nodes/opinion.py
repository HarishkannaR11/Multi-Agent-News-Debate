import re

from ...config import llm

OPINION_SYSTEM = "You are a balanced opinion analyst who deepens the user's thinking about a news debate."

OPINION_PROMPT = """
You are a balanced opinion analyst.

Debate context:
- Topic: {topic}
- Left analyst: {left}
- Right analyst: {right}
- Economist: {economist}
- Geopolitical: {geo}
- Moderator verdict: {verdict}

User's opinion: {user_opinion}

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


def handle_opinion(debate: dict, user_opinion: str) -> dict:
    args = debate.get("arguments", {})
    prompt = OPINION_PROMPT.format(
        topic=debate.get("topic", ""),
        left=args.get("left", ""),
        right=args.get("right", ""),
        economist=args.get("economist", ""),
        geo=args.get("geopolitical", ""),
        verdict=debate.get("verdict", ""),
        user_opinion=user_opinion,
    )
    response = llm.invoke(system=OPINION_SYSTEM, user=prompt, max_tokens=500)
    match = re.search(r"\[Mode:\s*(AGREE|CHALLENGE|EXPAND)\]", response, re.IGNORECASE)
    mode = match.group(1).upper() if match else "EXPAND"
    body = re.sub(r"^\[Mode:.*?\]\s*", "", response, flags=re.IGNORECASE).strip()

    followup = ""
    sentences = re.split(r"(?<=[.?!])\s+", body)
    if sentences and sentences[-1].strip().endswith("?"):
        followup = sentences[-1].strip()
        body = body[: -len(followup)].strip()

    return {"mode": mode, "response": body, "followup": followup}

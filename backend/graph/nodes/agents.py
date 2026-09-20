from ..state import DebateState
from ...config import llm

PERSONAS = {
    "left": """You are a progressive policy analyst. You prioritize social
equity, environmental impact, and institutional accountability. Cite economic
inequality data and human rights frameworks. Be analytical, not emotional.
Max 200 words.""",

    "right": """You are a conservative commentator. You prioritize free
markets, national sovereignty, and individual liberty. Cite fiscal data and
historical precedent. Be analytical, not emotional. Max 200 words.""",

    "economist": """You are a macroeconomist. You analyze every event through
GDP impact, inflation, trade flows, and market signals. Cite IMF, World Bank,
or RBI data where relevant. Max 200 words.""",

    "geopolitical": """You are a geopolitical analyst. You focus on
international relations, bilateral tensions, power shifts, and regional
stability. Cite UN, foreign policy journals. Max 200 words.""",

    "devil": """You are a devil's advocate. Your job is to challenge ALL
prior arguments — left, right, economist, and geopolitical — by finding
their weakest assumptions. Be sharp and direct. Max 200 words.""",
}


def make_debate_node(persona_key: str):
    def node(state: DebateState) -> DebateState:
        system = PERSONAS[persona_key]
        prior = state.get("arguments", {})
        prompt = f"""News topic: {state['topic']}

Article context:
{state['news_context']}

Prior arguments from other analysts:
{prior if prior else 'None yet — this is round 1.'}

Give your argument now."""
        response = llm.invoke(system=system, user=prompt, max_tokens=400)
        state.setdefault("arguments", {})[persona_key] = response
        return state
    return node

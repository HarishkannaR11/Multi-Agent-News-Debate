from ...config import settings  # the shared app settings (we need the retry limit)
from ..guarded import generate_guarded  # "ask the LLM, then content-check the answer, retry if blocked"
from ..prompts import UNTRUSTED_NOTE, article_block, format_arguments  # prompt-safety and formatting helpers
from ..state import DebateState  # the shared state shape

# The system prompt for each analyst: it defines who the analyst is and how they should argue.
PERSONAS = {
    # Progressive analyst.
    "left": """You are a progressive policy analyst. You prioritize social
equity, environmental impact, and institutional accountability. Cite economic
inequality data and human rights frameworks. Be analytical, not emotional.
Max 200 words.""",

    # Conservative commentator.
    "right": """You are a conservative commentator. You prioritize free
markets, national sovereignty, and individual liberty. Cite fiscal data and
historical precedent. Be analytical, not emotional. Max 200 words.""",

    # Macroeconomist.
    "economist": """You are a macroeconomist. You analyze every event through
GDP impact, inflation, trade flows, and market signals. Cite IMF, World Bank,
or RBI data where relevant. Max 200 words.""",

    # Geopolitical analyst.
    "geopolitical": """You are a geopolitical analyst. You focus on
international relations, bilateral tensions, power shifts, and regional
stability. Cite UN, foreign policy journals. Max 200 words.""",

    # Devil's advocate: attacks the weak points of everyone else's argument.
    "devil": """You are a devil's advocate. Your job is to challenge ALL
prior arguments — left, right, economist, and geopolitical — by finding
their weakest assumptions. Be sharp and direct. Max 200 words.""",
}

# The devil's advocate reads the other four, so it runs after them (see graph.py).
# The four analysts that run at the same time (the devil's advocate runs afterwards).
PARALLEL_PERSONAS = ("left", "right", "economist", "geopolitical")


# Factory: builds the graph step for ONE analyst (called once per analyst).
def make_debate_node(persona_key: str):
    # This analyst's instructions plus the security note about untrusted text.
    system = PERSONAS[persona_key] + UNTRUSTED_NOTE

    # The actual step function LangGraph will run for this analyst.
    def node(state: DebateState) -> dict:
        # The other analysts' arguments so far (this analyst's own is excluded).
        prior = format_arguments(state.get("arguments", {}), exclude=persona_key)
        # The message sent to the LLM: topic, fenced article text, others' arguments, and the request.
        prompt = f"""News topic: {state['topic']}

Article context:
{article_block(state['news_context'])}

Prior arguments from other analysts:
{prior or 'None yet — this is round 1.'}

Give your argument now."""
        # Ask the LLM and content-check the answer, retrying if it is blocked.
        response = generate_guarded(
            system, prompt, max_tokens=400, retries=settings.MAX_REBUTTAL_RETRIES, label=f"opening[{persona_key}]"
        )
        # A persona whose opening never passes the guardrail sits the debate out: it is absent from
        # `arguments`, so it also gets no rebuttal and no bias score.
        # Return this analyst's argument as a state update; if none passed the filter, return nothing.
        return {"arguments": {persona_key: response}} if response else {}

    # Hand the step function back so the graph can register it.
    return node

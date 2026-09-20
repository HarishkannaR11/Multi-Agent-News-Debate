import re

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from .config import settings
from .graph.graph import build_graph
from .graph.state import DebateState
from .services.redis_service import save_debate

_scheduler = AsyncIOScheduler()


def _slugify(topic: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", topic.lower()).strip("-")[:60] or "topic"


async def run_daily_debate() -> None:
    graph = build_graph()
    initial_state: DebateState = {
        "topic": "",
        "date": "",
        "news_context": "",
        "round": 1,
        "arguments": {},
        "rebuttals": {},
        "guardrail_input_pass": False,
        "guardrail_output_pass": False,
        "verdict": "",
        "bias_scores": {},
        "status": "fetching",
    }
    final_state = await graph.ainvoke(initial_state)
    await save_debate(final_state["date"], _slugify(final_state["topic"]), final_state)


def start_scheduler() -> None:
    _scheduler.add_job(
        run_daily_debate,
        "cron",
        hour=settings.SCHEDULER_HOUR,
        minute=settings.SCHEDULER_MINUTE,
        id="daily_news_debate",
        replace_existing=True,
    )
    _scheduler.start()

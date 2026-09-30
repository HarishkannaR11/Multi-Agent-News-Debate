import asyncio
import logging
import re

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from .config import settings
from .graph.graph import build_graph, new_debate_state, run_config
from .services.redis_service import (
    acquire_daily_lock,
    mark_daily_done,
    recent_source_urls,
    release_daily_lock,
    save_debate,
)
from .timeutil import today_iso

logger = logging.getLogger(__name__)

_scheduler = AsyncIOScheduler(timezone=settings.SCHEDULER_TIMEZONE)


def _slugify(topic: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", topic.lower()).strip("-")[:60].strip("-") or "topic"


async def generate_debate(date: str) -> str | None:
    """Run the graph and save the result, retrying transient failures.

    The caller must already hold the daily lock. On success the lock is kept
    (marked done) so a second replica or a repeated trigger is a no-op; after the
    final failure it is released so a later trigger can try again.
    """
    attempts = max(1, settings.DAILY_RUN_ATTEMPTS)
    for attempt in range(1, attempts + 1):
        try:
            seen_urls = await recent_source_urls()
            final_state = await build_graph().ainvoke(new_debate_state(seen_urls), config=run_config())
            debate_id = await save_debate(final_state["date"], _slugify(final_state["topic"]), final_state)
            await mark_daily_done(date)
            logger.info("Saved debate %s", debate_id)
            return debate_id
        except Exception:
            logger.exception("Daily debate attempt %d/%d failed", attempt, attempts)
            if attempt < attempts:
                await asyncio.sleep(settings.DAILY_RUN_RETRY_SECONDS)

    await release_daily_lock(date)
    logger.error("Daily debate for %s failed after %d attempts", date, attempts)
    return None


async def run_daily_debate() -> str | None:
    date = today_iso()
    if not await acquire_daily_lock(date):
        logger.info("Debate for %s already generated or running; skipping", date)
        return None
    return await generate_debate(date)


def start_scheduler() -> None:
    if not settings.SCHEDULER_ENABLED:
        logger.info("In-process scheduler disabled (SCHEDULER_ENABLED=false)")
        return
    _scheduler.add_job(
        run_daily_debate,
        "cron",
        hour=settings.SCHEDULER_HOUR,
        minute=settings.SCHEDULER_MINUTE,
        id="daily_news_debate",
        replace_existing=True,
        coalesce=True,
        misfire_grace_time=60 * 60,
    )
    _scheduler.start()


def stop_scheduler() -> None:
    if _scheduler.running:
        _scheduler.shutdown(wait=False)

import asyncio  # Python's async toolkit (we use it to sleep without blocking)
import logging  # Python's built-in logging system
import re  # regular expressions (pattern matching on text)

from apscheduler.schedulers.asyncio import AsyncIOScheduler  # runs jobs on a schedule (like cron)

from .config import settings  # the shared app settings
from .graph.graph import build_graph, new_debate_state, run_config  # the debate workflow and its helpers
from .services.redis_service import (  # all the Redis functions the job needs
    acquire_daily_lock,  # claim today's run (only one caller wins)
    mark_daily_done,  # keep the lock after success so it cannot run twice
    recent_source_urls,  # article URLs debated recently
    release_daily_lock,  # give the lock back after a final failure
    save_debate,  # store the finished debate
)
from .timeutil import today_iso  # today's date as text

# A logger named after this module.
logger = logging.getLogger(__name__)

# The scheduler object that will trigger the daily job, using the configured timezone.
_scheduler = AsyncIOScheduler(timezone=settings.SCHEDULER_TIMEZONE)


# Turns a topic sentence into a short URL-safe id.
def _slugify(topic: str) -> str:
    # Lowercase it, replace every run of non-letters/digits with "-", trim "-" from the ends,
    # cut to 60 characters, trim "-" again, and use "topic" if nothing is left.
    return re.sub(r"[^a-z0-9]+", "-", topic.lower()).strip("-")[:60].strip("-") or "topic"


# Runs the graph and saves the result, retrying on failure.
async def generate_debate(date: str) -> str | None:
    """Run the graph and save the result, retrying transient failures.

    The caller must already hold the daily lock. On success the lock is kept
    (marked done) so a second replica or a repeated trigger is a no-op; after the
    final failure it is released so a later trigger can try again.
    """
    # How many attempts to make (at least one).
    attempts = max(1, settings.DAILY_RUN_ATTEMPTS)
    # Attempts are numbered 1, 2, 3, ...
    for attempt in range(1, attempts + 1):
        try:
            # Get the article URLs used recently so the fetcher can skip them.
            seen_urls = await recent_source_urls()
            # Run the whole debate workflow and wait for its final state.
            final_state = await build_graph().ainvoke(new_debate_state(seen_urls), config=run_config(date))
            # Save the result under its date and a slug of its topic.
            debate_id = await save_debate(final_state["date"], _slugify(final_state["topic"]), final_state)
            # Keep the lock for 36 hours so today's run is not repeated.
            await mark_daily_done(date)
            # Record success in the logs.
            logger.info("Saved debate %s", debate_id)
            # Done: return the new debate's id.
            return debate_id
        # Anything went wrong in this attempt.
        except Exception:
            # Log the full error with its traceback.
            logger.exception("Daily debate attempt %d/%d failed", attempt, attempts)
            # If more attempts remain, wait before trying again.
            if attempt < attempts:
                await asyncio.sleep(settings.DAILY_RUN_RETRY_SECONDS)

    # Every attempt failed: release the lock so a later trigger can retry.
    await release_daily_lock(date)
    # Log the final failure.
    logger.error("Daily debate for %s failed after %d attempts", date, attempts)
    # Signal failure to the caller.
    return None


# The job the scheduler runs each day.
async def run_daily_debate() -> str | None:
    # Today's date as text.
    date = today_iso()
    # Try to claim today's run; if another process already has it, skip.
    if not await acquire_daily_lock(date):
        logger.info("Debate for %s already generated or running; skipping", date)
        return None
    # We own the run: generate the debate.
    return await generate_debate(date)


# Starts the daily scheduler (called at app start-up).
def start_scheduler() -> None:
    # Do nothing if the scheduler is switched off in settings.
    if not settings.SCHEDULER_ENABLED:
        logger.info("In-process scheduler disabled (SCHEDULER_ENABLED=false)")
        return
    # Register the daily job.
    _scheduler.add_job(
        # The function to run.
        run_daily_debate,
        # Use a "cron" schedule (specific time of day).
        "cron",
        # Hour of day to run.
        hour=settings.SCHEDULER_HOUR,
        # Minute of the hour to run.
        minute=settings.SCHEDULER_MINUTE,
        # A fixed name for this job.
        id="daily_news_debate",
        # If a job with this name already exists, replace it instead of failing.
        replace_existing=True,
        # If several runs were missed, run just once.
        coalesce=True,
        # Still run if the app was down at the scheduled time but is back within an hour.
        misfire_grace_time=60 * 60,
    )
    # Start the scheduler.
    _scheduler.start()


# Stops the scheduler (called when the app shuts down).
def stop_scheduler() -> None:
    # Only stop it if it is actually running.
    if _scheduler.running:
        # Do not wait for running jobs to finish.
        _scheduler.shutdown(wait=False)

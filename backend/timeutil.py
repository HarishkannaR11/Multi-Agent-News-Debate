from datetime import datetime  # the standard date/time class
from zoneinfo import ZoneInfo  # lets us ask for the time in a named timezone (e.g. "UTC")

from .config import settings  # the shared app settings (we need the timezone name)


# Returns today's date as text like "2026-10-01".
def today_iso() -> str:
    """Today's date in the scheduler's timezone, so the daily job and the id it saves under agree."""
    # Get "now" in the configured timezone, keep only the date part, and format it as YYYY-MM-DD.
    return datetime.now(ZoneInfo(settings.SCHEDULER_TIMEZONE)).date().isoformat()

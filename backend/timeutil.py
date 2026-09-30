from datetime import datetime
from zoneinfo import ZoneInfo

from .config import settings


def today_iso() -> str:
    """Today's date in the scheduler's timezone, so the daily job and the id it saves under agree."""
    return datetime.now(ZoneInfo(settings.SCHEDULER_TIMEZONE)).date().isoformat()

import json  # converts Python dicts to JSON text
import logging  # Python's built-in logging system

from .config import settings  # the shared app settings (log level and format)


# A formatter that prints each log record as one line of JSON.
class JsonFormatter(logging.Formatter):
    """One JSON object per line: CloudWatch Logs Insights and most log shippers parse it directly."""

    # Called by the logging system to turn one log record into a string.
    def format(self, record: logging.LogRecord) -> str:
        # Build a dictionary with the fields we want in every log line.
        entry = {
            # When it happened, e.g. 2026-10-01T12:00:00+0000.
            "time": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            # Severity: INFO, WARNING, ERROR, ...
            "level": record.levelname,
            # Which part of the code logged it (module name).
            "logger": record.name,
            # The human-readable message with any %s values filled in.
            "message": record.getMessage(),
        }
        # If this log came from an exception, include the full traceback.
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        # Convert to JSON; default=str makes unknown types (like dates) printable instead of crashing.
        return json.dumps(entry, default=str)


# Sets up logging for the whole app (called once at start-up).
def configure_logging() -> None:
    # A handler sends log lines somewhere; StreamHandler writes to the console.
    handler = logging.StreamHandler()
    # If JSON logging is requested, use the JSON formatter.
    if settings.LOG_FORMAT == "json":
        handler.setFormatter(JsonFormatter())
    # Otherwise use a plain readable line: time, level, logger name, message.
    else:
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    # Get the root logger (the parent of every logger in the app).
    root = logging.getLogger()
    # Replace any existing handlers with ours so lines are not printed twice.
    root.handlers[:] = [handler]
    # Only show messages at or above the configured level.
    root.setLevel(settings.LOG_LEVEL.upper())

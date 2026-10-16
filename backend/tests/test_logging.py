import json  # to parse the log line back into a dictionary
import logging  # Python's logging system (we build a log record by hand)

from backend.logging_config import JsonFormatter  # the class that turns log records into JSON text


# The formatter must output one valid JSON object per record, including the error traceback.
def test_json_formatter_emits_one_parseable_object_with_exception():
    # Raise and catch an error so that a real exception exists to attach to the log record.
    try:
        raise ValueError("boom")
    except ValueError:
        import sys

        # Build a log record by hand: logger name, level, file, line, message template, its arguments, error info.
        record = logging.LogRecord("x.y", logging.ERROR, __file__, 1, "failed %s", ("job",), sys.exc_info())

    # Format it and parse the JSON back; failing to parse would fail the test.
    entry = json.loads(JsonFormatter().format(record))
    # Level, logger name and the filled-in message ("failed %s" with "job") are present.
    assert entry["level"] == "ERROR" and entry["logger"] == "x.y" and entry["message"] == "failed job"
    # The traceback text includes the error type and message.
    assert "ValueError: boom" in entry["exception"]

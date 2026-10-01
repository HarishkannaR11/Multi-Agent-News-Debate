import json
import logging

from backend.logging_config import JsonFormatter


def test_json_formatter_emits_one_parseable_object_with_exception():
    try:
        raise ValueError("boom")
    except ValueError:
        import sys

        record = logging.LogRecord("x.y", logging.ERROR, __file__, 1, "failed %s", ("job",), sys.exc_info())

    entry = json.loads(JsonFormatter().format(record))
    assert entry["level"] == "ERROR" and entry["logger"] == "x.y" and entry["message"] == "failed job"
    assert "ValueError: boom" in entry["exception"]

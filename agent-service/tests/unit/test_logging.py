import json
import logging
import sys

from flock_agent.common.logging import JsonFormatter


def make_record(**extra: object) -> logging.LogRecord:
    record = logging.makeLogRecord(
        {"name": "flock.test", "levelno": logging.INFO, "levelname": "INFO", "msg": "hello %s"}
    )
    record.args = ("world",)
    for key, value in extra.items():
        setattr(record, key, value)
    return record


def test_formats_a_single_json_line() -> None:
    line = JsonFormatter().format(make_record())

    payload = json.loads(line)
    assert "\n" not in line
    assert payload["level"] == "INFO"
    assert payload["logger"] == "flock.test"
    assert payload["message"] == "hello world"
    assert "timestamp" in payload


def test_includes_extra_fields() -> None:
    payload = json.loads(JsonFormatter().format(make_record(request_id="r-1", job_id="j-2")))

    assert payload["request_id"] == "r-1"
    assert payload["job_id"] == "j-2"


def test_includes_exception() -> None:
    try:
        raise ValueError("boom")
    except ValueError:
        record = make_record()
        record.exc_info = sys.exc_info()

    payload = json.loads(JsonFormatter().format(record))

    assert "ValueError: boom" in payload["exception"]

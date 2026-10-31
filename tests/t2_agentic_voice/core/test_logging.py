"""Structured logging: events are key/value records, filtered by level."""

from __future__ import annotations

import json
import logging
import sys
from collections.abc import Iterator

import pytest
from t2_agentic_voice.core.logging import configure_logging, get_logger


@pytest.fixture(autouse=True)
def _reset() -> Iterator[None]:
    yield
    configure_logging()


def test_json_events_carry_their_context(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging("INFO", "json")
    get_logger("tests.core").info("thing_done", count=3, label="café")
    event = json.loads(capsys.readouterr().out.strip())
    assert event["event"] == "thing_done"
    assert (event["count"], event["label"]) == (3, "café")
    assert (event["level"], event["logger_name"]) == ("info", "tests.core")


def test_events_below_the_level_are_dropped(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging("WARNING", "console")
    log = get_logger("tests.core")
    log.info("quiet")
    log.warning("loud")
    out = capsys.readouterr().out
    assert "quiet" not in out
    assert "loud" in out


def test_standard_library_lines_take_the_same_format(capsys: pytest.CaptureFixture[str]) -> None:
    """A framework's or a library's own logging comes out structured, once, after a
    reconfiguration too."""
    configure_logging("INFO", "json")
    configure_logging("INFO", "json")
    logging.getLogger("some.library").warning("disk %s is low", "/data")
    lines = capsys.readouterr().out.strip().splitlines()
    assert len(lines) == 1
    event = json.loads(lines[0])
    assert (event["event"], event["level"]) == ("disk /data is low", "warning")
    assert event["logger_name"] == "some.library"


def test_a_frameworks_own_handlers_are_taken_over(capsys: pytest.CaptureFixture[str]) -> None:
    server = logging.getLogger("tests.server")
    own = logging.StreamHandler()
    server.addHandler(own)
    server.propagate = False
    try:
        configure_logging("INFO", "json", take_over=["tests.server"])
        server.warning("started")
        event = json.loads(capsys.readouterr().out.strip())
        assert (event["event"], event["logger_name"]) == ("started", "tests.server")
        assert own not in server.handlers
    finally:
        server.handlers.clear()


def test_a_failing_output_is_reported_not_raised(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    configure_logging("INFO", "json")

    class Closed:
        def write(self, text: str) -> int:
            raise ValueError("closed")

    monkeypatch.setattr(sys, "stdout", Closed())
    logging.getLogger("some.library").error("lost")
    monkeypatch.undo()
    assert "Logging error" in capsys.readouterr().err

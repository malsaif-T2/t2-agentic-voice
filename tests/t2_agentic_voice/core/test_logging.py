"""Structured logging: events are key/value records, filtered by level."""

from __future__ import annotations

import json
import logging
import sys

import pytest
from t2_agentic_voice.core.logging import configure_logging, get_logger, logging_unchanged


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


def test_what_a_block_does_to_logging_is_undone() -> None:
    """A package that sets up logging on import (groq reads `GROQ_LOG`, TD-003): the root
    handler it adds is removed and closed, and the named loggers' levels are put back, while a
    handler already there stays."""
    root = logging.getLogger()
    there = logging.NullHandler()
    root.addHandler(there)
    named = logging.getLogger("tests.imported")
    named.setLevel(logging.WARNING)
    added = logging.StreamHandler()
    try:
        with logging_unchanged("tests.imported", "tests.untouched"):
            root.addHandler(added)
            named.setLevel(logging.DEBUG)
            logging.getLogger("tests.untouched").setLevel(logging.INFO)
        assert added not in root.handlers
        assert there in root.handlers
        assert named.level == logging.WARNING
        assert logging.getLogger("tests.untouched").level == logging.NOTSET
    finally:
        root.removeHandler(there)
        root.removeHandler(added)
        named.setLevel(logging.NOTSET)


def test_what_a_failing_block_does_to_logging_is_undone_too() -> None:
    root = logging.getLogger()
    added = logging.NullHandler()
    with pytest.raises(ImportError), logging_unchanged("tests.failing"):
        root.addHandler(added)
        logging.getLogger("tests.failing").setLevel(logging.DEBUG)
        raise ImportError("made up")
    assert added not in root.handlers
    assert logging.getLogger("tests.failing").level == logging.NOTSET

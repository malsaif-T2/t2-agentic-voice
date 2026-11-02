"""Structured logging on the standard library: an event is a record of its module's logger, with
its fields; `configure_logging` writes the library's lines, and those of the loggers it is
given, to the stream it is given, filtered by level, and configures nothing else. What
importing the library does: test_logging_import.py."""

from __future__ import annotations

import ast
import io
import json
import logging
import re
from pathlib import Path

import pytest
from pydantic import SecretStr
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.logging import (
    FIELDS,
    LIBRARY,
    TRANSPORT_LOGGERS,
    configure_logging,
    get_logger,
    logging_unchanged,
)
from t2_agentic_voice.core.settings.join import JoinSettings
from t2_agentic_voice.core.settings.logs import LogFormat, LoggingSettings

from tests.leaks import holding, shown
from tests.t2_agentic_voice.core.settings_support import LONG_SECRET, MADE_UP_KEY

SOURCE = Path(__file__).resolve().parents[3] / "packages" / "t2-agentic-voice" / "src" / LIBRARY
# A module's logger, as the library's modules make theirs (`get_logger(__name__)`).
MODULE = f"{LIBRARY}.tests"
# A console line: its UTC time stamp, its padded level and event, its logger, then its fields.
CONSOLE = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+Z \[info     \] thing_done {21}"
    rf"\[{re.escape(MODULE)}\] count=3 label=café"
)


class Kept(logging.Handler):
    """An app's own handler: the records it is given."""

    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


def test_a_library_line_reaches_an_apps_handler_once_the_app_adds_one(
    unconfigured_logging: None, capsys: pytest.CaptureFixture[str]
) -> None:
    """The design's 3.3: the event is the record's message and its fields the record's
    `fields`, a record of the line that logged; nothing is written before the app's handler."""
    log = get_logger(MODULE)
    log.warning("before_any_handler", count=1)
    kept, library = Kept(), logging.getLogger(LIBRARY)
    library.addHandler(kept)
    library.setLevel(logging.INFO)
    log.info("thing_done", count=3, label="café")
    (record,) = kept.records
    assert (record.name, record.levelno, record.getMessage()) == (
        MODULE,
        logging.INFO,
        "thing_done",
    )
    assert getattr(record, FIELDS) == {"count": 3, "label": "café"}
    assert record.filename == Path(__file__).name
    assert capsys.readouterr() == ("", "")


def test_configure_logging_writes_to_the_stream_it_is_given(
    capsys: pytest.CaptureFixture[str],
) -> None:
    stream = io.StringIO()
    configure_logging("INFO", "json", stream=stream)
    get_logger(MODULE).info("thing_done", count=3, label="café")
    event = json.loads(stream.getvalue())
    assert event["event"] == "thing_done"
    assert (event["count"], event["label"]) == (3, "café")
    assert (event["level"], event["logger_name"]) == ("info", MODULE)
    assert capsys.readouterr() == ("", "")


def test_a_console_line_reads_as_it_always_has(capsys: pytest.CaptureFixture[str]) -> None:
    """The default the commands keep: standard output, plain console lines (tests/conftest.py
    calls `configure_logging()`)."""
    get_logger(MODULE).info("thing_done", count=3, label="café")
    assert CONSOLE.fullmatch(capsys.readouterr().out.strip())


def test_events_below_the_level_are_dropped(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging("WARNING", "console")
    log = get_logger(MODULE)
    log.info("quiet")
    log.warning("loud")
    configure_logging("DEBUG", "console")
    log.debug("detail")
    out = capsys.readouterr().out
    assert "quiet" not in out
    assert "loud" in out and "detail" in out


def test_the_root_logger_and_another_librarys_are_left_alone(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """No handler on the root logger, its level kept, another library's lines left to
    the app."""
    root, other = logging.getLogger(), logging.getLogger("some.library")
    before = (list(root.handlers), root.level, other.level, other.propagate)
    configure_logging("DEBUG", "json")
    assert (list(root.handlers), root.level, other.level, other.propagate) == before
    other.warning("disk %s is low", "/data")
    assert capsys.readouterr().out == ""


def test_the_loggers_named_take_the_same_lines(capsys: pytest.CaptureFixture[str]) -> None:
    """An app's own loggers, its plain standard-library lines included, formatted once."""
    configure_logging("INFO", "json", loggers=["tests.app"])
    logging.getLogger("tests.app.module").warning("disk %s is low", "/data")
    get_logger("tests.app.command").info("app_done", items=2)
    first, second = (json.loads(line) for line in capsys.readouterr().out.splitlines())
    assert (first["event"], first["level"]) == ("disk /data is low", "warning")
    assert first["logger_name"] == "tests.app.module"
    assert (second["event"], second["items"], second["logger_name"]) == (
        "app_done",
        2,
        "tests.app.command",
    )


def test_a_second_call_replaces_the_first() -> None:
    """The handler an earlier call put on any logger is gone; only the latest stream writes."""
    first, second = io.StringIO(), io.StringIO()
    configure_logging(stream=first, loggers=["tests.first"])
    configure_logging(stream=second)
    get_logger(MODULE).info("library_line")
    get_logger("tests.first").warning("first_line")
    assert (first.getvalue(), logging.getLogger("tests.first").handlers) == ("", [])
    assert "library_line" in second.getvalue() and "first_line" not in second.getvalue()


def test_the_webrtc_stack_is_held_at_warning() -> None:
    """Plan 003's reading of step 4: aioice's INFO lines hold IP addresses and aiortc's DEBUG
    lines SDP. A level set below WARNING is raised, a stricter one kept, and a logger under one
    with no level of its own takes the held one's; no handler is added."""
    logging.getLogger("aiortc").setLevel(logging.DEBUG)
    logging.getLogger("aioice.ice").setLevel(logging.INFO)
    logging.getLogger("aioice.turn").setLevel(logging.ERROR)
    configure_logging("DEBUG")
    levels = {name: logging.getLogger(name).level for name in ("aiortc", "aioice", "aioice.ice")}
    assert levels == dict.fromkeys(levels, logging.WARNING)
    assert logging.getLogger("aioice.turn").level == logging.ERROR
    assert logging.getLogger("aiortc.rtcpeerconnection").getEffectiveLevel() == logging.WARNING
    handlers = [h for name in TRANSPORT_LOGGERS for h in logging.getLogger(name).handlers]
    assert all(isinstance(h, logging.NullHandler) for h in handlers)


@pytest.mark.parametrize("content", [False, True])
def test_no_address_or_sdp_reaches_an_apps_root_handler_unless_content_is_on(
    content: bool, caplog: pytest.LogCaptureFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    """Adversarial: an app whose root logger takes DEBUG, and a WebRTC stack set to DEBUG
    before the app configures logging. `logging.content`, which only `dev` allows, lets them
    through (the control)."""
    caplog.set_level(logging.DEBUG)
    logging.getLogger("aioice").setLevel(logging.DEBUG)
    logging.getLogger("aiortc.rtcpeerconnection").setLevel(logging.DEBUG)
    settings = VoiceSettings(env="dev", logging=LoggingSettings(content=content))
    configure_logging(settings.logging.level, content=settings.logging.content)
    logging.getLogger("aioice.ice").info("Check %s -> %s", "192.0.2.10:5000", "198.51.100.7:6000")
    logging.getLogger("aiortc.rtcpeerconnection").debug("c=IN IP4 192.0.2.10")
    surfaces = shown(caplog=caplog, capsys=capsys)
    assert holding("192.0.2.10", surfaces) == (["log records"] if content else [])


def test_fields_never_replace_what_the_line_says(capsys: pytest.CaptureFixture[str]) -> None:
    """Adversarial: fields named as a record's own attributes or as the line's keys break
    nothing and change neither the event, its level, its time nor its logger, each kept under
    another name; an event holding `%s` is written as it is."""
    configure_logging("INFO", "json")
    get_logger(MODULE).warning(
        "real_event %s",
        name="forged",
        message="forged",
        msg="forged",
        args="forged",
        levelname="CRITICAL",
        level="critical",
        timestamp="forged",
        logger_name="forged",
        logger="forged",
        field_level="kept",
    )
    out, err = capsys.readouterr()
    event = json.loads(out)
    assert (event["event"], event["level"], event["logger_name"]) == (
        "real_event %s",
        "warning",
        MODULE,
    )
    assert event["timestamp"] != "forged" and event["name"] == event["message"] == "forged"
    assert (event["field_level"], event["field_field_level"]) == ("kept", "critical")
    assert event["field_timestamp"] == event["field_logger_name"] == event["field_logger"]
    assert "logger" not in event and err == ""


@pytest.mark.parametrize("fmt", ["console", "json"])
def test_a_field_named_as_a_formatters_directive_stays_a_field_on_one_line(
    fmt: LogFormat, capsys: pytest.CaptureFixture[str]
) -> None:
    """Adversarial: a field named `exception`, `stack` or `exc_info` is a field like another,
    renamed: the console renderer would write its text raw on lines of its own (a forged line),
    and `exc_info` would add the traceback the library never logs (plan 003's step 8)."""
    forged = f"x\n2026-11-02T00:00:00.000000Z [info     ] join_accepted [{LIBRARY}] subject=admin"
    configure_logging("INFO", fmt)
    try:
        raise RuntimeError(f"held {MADE_UP_KEY}")
    except RuntimeError:
        get_logger(MODULE).warning(
            "refused", exception=forged, stack=forged, exc_info=True, stack_info=True
        )
    out = capsys.readouterr().out
    assert out.count("\n") == 1 and out.endswith("\n")
    assert "join_accepted" in out and MADE_UP_KEY not in out and "Traceback" not in out
    if fmt == "json":
        event = json.loads(out)
        assert event["field_exception"] == event["field_stack"] == forged
        assert event["field_exc_info"] is event["field_stack_info"] is True


def test_no_secret_reaches_a_line_or_a_record(
    caplog: pytest.LogCaptureFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    """Invariant 5 (GP-19): a secret logged as a field, alone or inside the settings, is in no
    console line, no record an app's handler sees, and no field's repr."""
    caplog.set_level(logging.DEBUG)
    configure_logging("DEBUG", "console")
    settings = VoiceSettings(
        env="test", join=JoinSettings(keys={"k1": SecretStr(LONG_SECRET)}, current_kid="k1")
    )
    log = get_logger(MODULE)
    log.debug("key_read", key=SecretStr(MADE_UP_KEY))
    log.error("settings_read", settings=settings, join=settings.join)
    surfaces = shown(caplog=caplog, capsys=capsys)  # each record's fields too
    assert "key_read" in surfaces["stdout"] and "settings_read" in surfaces["stdout"]
    assert holding(MADE_UP_KEY, surfaces) == [] and holding(LONG_SECRET, surfaces) == []


def test_a_failing_output_is_reported_not_raised(capsys: pytest.CaptureFixture[str]) -> None:
    class Closed(io.StringIO):
        def write(self, text: str) -> int:
            raise ValueError("closed")

    configure_logging("INFO", "json", stream=Closed())
    get_logger(MODULE).error("lost")
    assert "Logging error" in capsys.readouterr().err


def test_every_library_module_logs_under_the_librarys_name() -> None:
    """The design's 10.2: each logger of the library's is its module's, `get_logger(__name__)`,
    so it sits under `t2_agentic_voice`."""
    named = []
    for path in sorted(SOURCE.rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "get_logger":
                named.append((path.name, ast.unparse(node)))
    assert named and all(call == "get_logger(__name__)" for _, call in named), named


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

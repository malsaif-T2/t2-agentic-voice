"""Structured logging on the standard library's `logging`: the single logging entry point
(ARCH-OWNER, ARCH-PRINT; the design's 3.3 and 10.2).

Usage:
    from t2_agentic_voice.core.logging import get_logger

    log = get_logger(__name__)
    log.info("order_created", items=3, duration_ms=34)

Event names are snake_case constants and context goes in key/value pairs (never f-strings),
so logs stay machine-queryable. Never log secrets or personal data.

The library's loggers sit under `t2_agentic_voice`, whose logger has a `NullHandler`: importing
the library configures nothing and prints nothing, it never adds a handler to the root logger
or touches another library's logger, and its lines reach an output only once the app gives
them one. An event is a standard-library record of its module's logger: its message is the
event name and its fields are the record's `fields` attribute, so an app's own handlers and
formatters see both. `configure_logging` is the helper an app may call instead of configuring
logging its own way. Pipecat logs through loguru, which `voice` owns (plan 003, Q2).
"""

from __future__ import annotations

import json
import logging
import sys
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from functools import partial
from typing import TextIO

import structlog
from structlog.typing import EventDict, Processor, WrappedLogger

from t2_agentic_voice.core.settings.logs import LogFormat, LogLevel

# The library's own logger: every module's `get_logger(__name__)` sits under it.
LIBRARY = "t2_agentic_voice"
# The record attribute that holds an event's key/value fields. They are one `extra` key, since a
# record refuses an `extra` key that names one of its own attributes (`name`, `message`).
FIELDS = "fields"
# The WebRTC stack's loggers, whose lines below WARNING hold what a call carries: aioice's INFO
# lines its IP addresses, aiortc's DEBUG lines its SDP (plan 003, the reading of step 4).
TRANSPORT_LOGGERS = ("aiortc", "aioice")

logging.getLogger(LIBRARY).addHandler(logging.NullHandler())


class StructuredLogger:
    """One module's events, as records of the standard-library logger of its name; a level the
    logger does not take costs one check."""

    __slots__ = ("_logger",)

    def __init__(self, logger: logging.Logger) -> None:
        self._logger = logger

    def debug(self, event: str, **fields: object) -> None:
        """The event at DEBUG, the only level that may hold call content (`logging.content`)."""
        self._log(logging.DEBUG, event, fields)

    def info(self, event: str, **fields: object) -> None:
        """The event at INFO: identifiers, timings and outcomes only."""
        self._log(logging.INFO, event, fields)

    def warning(self, event: str, **fields: object) -> None:
        """The event at WARNING."""
        self._log(logging.WARNING, event, fields)

    def error(self, event: str, **fields: object) -> None:
        """The event at ERROR."""
        self._log(logging.ERROR, event, fields)

    def _log(self, level: int, event: str, fields: Mapping[str, object]) -> None:
        if self._logger.isEnabledFor(level):
            # The record names the line that logged, two calls up, not this module.
            self._logger.log(level, event, extra={FIELDS: dict(fields)}, stacklevel=3)


def get_logger(name: str) -> StructuredLogger:
    """The structured logger of the standard-library logger `name`: the library's modules pass
    `__name__`, so theirs sit under `t2_agentic_voice`; an app's sit under its own package."""
    return StructuredLogger(logging.getLogger(name))


def configure_logging(
    level: LogLevel = "INFO",
    fmt: LogFormat = "console",
    *,
    stream: TextIO | None = None,
    loggers: Sequence[str] = (),
    content: bool = False,
) -> None:
    """Write the library's lines, and those of the loggers named in `loggers` (an app's own
    package, a framework's), to `stream` as structured lines, console or JSON, from `level` up.
    Call it once at startup with the settings' `logging` values; a second call replaces the
    first's handler. What it does, and nothing else:
    - one handler of its own on `t2_agentic_voice` and on each logger in `loggers`, whose levels
      it sets to `level`; the handler an earlier call put on any logger is removed and closed;
    - `stream` None writes to the standard output of the moment (a test swaps it);
    - unless `content` (`logging.content`, which only `dev` allows), the WebRTC stack's loggers
      are held at WARNING (`hold_transport_loggers`).
    The root logger, any other handler and whether a logger propagates are left alone: an app
    that also configured the root logger sees the library's lines there too. A framework that
    installs handlers of its own (uvicorn with a `log_config`) prints its lines twice when
    named; give it none (`log_config=None`) instead."""
    number = logging.getLevelNamesMapping()[level]
    handler = _Lines(stream, number)
    handler.setFormatter(_formatter(fmt))
    _remove_earlier()
    for name in (LIBRARY, *loggers):
        logger = logging.getLogger(name)
        logger.setLevel(number)
        logger.addHandler(handler)
    if not content:
        hold_transport_loggers()


def hold_transport_loggers() -> None:
    """Hold each of `TRANSPORT_LOGGERS`, and each logger under it that has a level of its own, at
    WARNING, keeping a stricter level. No handler is added: their lines still go wherever the
    app sends them, only fewer of them. A logger under one with no level of its own takes the
    held one's."""
    tops = [logging.getLogger(name) for name in TRANSPORT_LOGGERS]  # made held when not made yet
    under = tuple(f"{name}." for name in TRANSPORT_LOGGERS)
    leveled = [one for one in _loggers() if one.name.startswith(under) and one.level]
    for logger in [*tops, *leveled]:
        if logger.level < logging.WARNING:
            logger.setLevel(logging.WARNING)


class _Lines(logging.Handler):
    """Each record, formatted, as one line written to the handler's stream, or to the standard
    output of the moment when it has none, flushed, in order."""

    def __init__(self, stream: TextIO | None, level: int) -> None:
        super().__init__(level)
        self._stream = stream

    def emit(self, record: logging.LogRecord) -> None:
        try:
            stream = sys.stdout if self._stream is None else self._stream
            stream.write(self.format(record) + "\n")
            stream.flush()
        except Exception:
            self.handleError(record)


def _formatter(fmt: LogFormat) -> logging.Formatter:
    """A record as one structured line: its event, level, UTC time and logger, then its fields."""
    renderer: Processor
    if fmt == "json":
        # ensure_ascii=False keeps non-ASCII text readable in the output.
        renderer = structlog.processors.JSONRenderer(
            serializer=partial(json.dumps, ensure_ascii=False)
        )
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=False)
    return structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=[
            _fields,
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
        ],
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.format_exc_info,
            renderer,
        ],
    )


def _fields(_logger: WrappedLogger, _method: str, event: EventDict) -> EventDict:
    """A record's fields, which never replace its event, level, time or logger, and its logger's
    name under the key the lines have always had."""
    record: logging.LogRecord = event["_record"]
    fields = getattr(record, FIELDS, None)
    if isinstance(fields, dict):
        for key, value in fields.items():
            event.setdefault(key, value)
    event["logger_name"] = record.name
    return event


def _loggers() -> list[logging.Logger]:
    """Every logger made so far, the root logger aside."""
    made = list(logging.Logger.manager.loggerDict.values())
    return [logger for logger in made if isinstance(logger, logging.Logger)]


def _remove_earlier() -> None:
    """The handler an earlier `configure_logging` put on any logger, removed and closed."""
    for logger in _loggers():
        for handler in [h for h in logger.handlers if isinstance(h, _Lines)]:
            logger.removeHandler(handler)
            handler.close()


@contextmanager
def logging_unchanged(*names: str) -> Iterator[None]:
    """Undo what the block does to the standard library's logging: a handler it adds to the root
    logger is removed and closed, and each named logger's level is put back. For a package that
    sets up logging when it is imported: groq reads `GROQ_LOG` (TD-003)."""
    root = logging.getLogger()
    handlers = list(root.handlers)
    levels = {name: logging.getLogger(name).level for name in names}
    try:
        yield
    finally:
        for handler in [h for h in root.handlers if h not in handlers]:
            root.removeHandler(handler)
            handler.close()
        for name, level in levels.items():
            logging.getLogger(name).setLevel(level)

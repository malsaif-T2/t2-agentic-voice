"""Structured logging: the single logging entry point (ARCH-OWNER, ARCH-PRINT).

Usage:
    from t2_agentic_voice.core.logging import get_logger

    log = get_logger(__name__)
    log.info("order_created", items=3, duration_ms=34)

Event names are snake_case constants and context goes in key/value pairs (never f-strings),
so logs stay machine-queryable. Never log secrets or personal data.

Lines written through the standard library's `logging` (a framework's own, a library's
warnings) take the same format and the same context, on the same output, so nothing a server
or a library writes escapes the structured format. A framework that installs handlers of its
own before the application starts (a web server's loggers) is named in `take_over`, so its
lines come here too.
"""

from __future__ import annotations

import json
import logging
import sys
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from functools import partial
from typing import cast

import structlog
from structlog.typing import EventDict, FilteringBoundLogger, Processor, WrappedLogger

from t2_agentic_voice.core.config import LogFormat, LogLevel


def configure_logging(
    level: LogLevel = "INFO", fmt: LogFormat = "console", take_over: Sequence[str] = ()
) -> None:
    """Configure structlog, and the standard library's logging through it, process-wide; call
    once at startup, with the Settings' values (again after a framework set up its loggers)."""
    renderer: Processor
    if fmt == "json":
        # ensure_ascii=False keeps non-ASCII text readable in the output.
        renderer = structlog.processors.JSONRenderer(
            serializer=partial(json.dumps, ensure_ascii=False)
        )
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=False)
    context: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
    ]
    structlog.configure(
        processors=[
            *context,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelNamesMapping()[level]),
        logger_factory=structlog.PrintLoggerFactory(),
        # Not caching keeps reconfiguration (tests, reloads) effective for existing loggers.
        cache_logger_on_first_use=False,
    )
    _route_standard_logging(level, renderer, context, take_over)


class _Bridge(logging.Handler):
    """Standard-library records, formatted by structlog, written where the application's events
    go and as they do: to the current standard output (tests swap it), flushed, in order."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            sys.stdout.write(self.format(record) + "\n")
            sys.stdout.flush()
        except Exception:
            self.handleError(record)


def _route_standard_logging(
    level: LogLevel, renderer: Processor, context: list[Processor], take_over: Sequence[str]
) -> None:
    """One bridge on the root logger (a reconfiguration replaces it). The root logger's own
    level is left alone, so libraries write their warnings and above unless they set a level."""
    root = logging.getLogger()
    for old in [h for h in root.handlers if isinstance(h, _Bridge)]:
        root.removeHandler(old)
    bridge = _Bridge(level=logging.getLevelNamesMapping()[level])
    bridge.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            foreign_pre_chain=[*context, _logger_name],
            processors=[
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                structlog.processors.format_exc_info,
                renderer,
            ],
        )
    )
    root.addHandler(bridge)
    for name in take_over:
        framework = logging.getLogger(name)
        framework.handlers.clear()
        framework.propagate = True


def _logger_name(_logger: WrappedLogger, _method: str, event: EventDict) -> EventDict:
    """A standard-library record's logger, under the key the application's events use."""
    if (record := event.get("_record")) is not None:
        event.setdefault("logger_name", record.name)
    return event


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


def get_logger(name: str) -> FilteringBoundLogger:
    """A lazily configured logger that tags every event with `logger_name=name`.

    Lazy means module-level loggers pick up the configuration applied later at startup. (The
    key cannot be `logger`: that name collides with structlog's own `wrap_logger` argument.)
    """
    return cast(FilteringBoundLogger, structlog.get_logger(logger_name=name))

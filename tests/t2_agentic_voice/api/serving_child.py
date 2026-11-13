"""The child process of test_serving.py: `serve()` itself, on the fakes, on the port it is given,
with a global tracer, meter and logger provider that keep everything they are given (so FastAPI's
telemetry, were it on, would land there) and `FASTAPI_OTEL_AUTO_CONFIGURE=true` in its
environment, set by the parent. It stops once the stop file appears, then writes what it found
to the result file: whether voice's entry point started on a selector event loop, and how many
spans, metrics and log records the global providers got.

Run as `python -m tests.t2_agentic_voice.api.serving_child PORT FOLDER` from the repository's
root."""

from __future__ import annotations

import asyncio
import json
import sys
import threading
import time
from pathlib import Path
from typing import Any, ClassVar

import uvicorn
from opentelemetry import _logs, metrics, trace
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs.export import InMemoryLogExporter, SimpleLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from t2_agentic_voice.adapters import phrase_cache, used_tokens
from t2_agentic_voice.api.server import serve

from tests.t2_agentic_voice.api.runtime_support import (
    FakePhraseCache,
    FakeUsedTokens,
    Harness,
    dev_settings,
)
from tests.t2_agentic_voice.fakes import FakeCalls

STOP = "stop"
RESULT = "result.json"


class _LoopCalls(FakeCalls):
    """The fake entry point, noting the loop it was started on."""

    selector: ClassVar[bool | None] = None

    async def start(self) -> None:
        _LoopCalls.selector = isinstance(asyncio.get_running_loop(), asyncio.SelectorEventLoop)
        await super().start()


class _Server(uvicorn.Server):
    """uvicorn's server, kept, so the stop file can stop it."""

    made: ClassVar[list[_Server]] = []

    def __init__(self, config: uvicorn.Config) -> None:
        super().__init__(config)
        _Server.made.append(self)


def _stop_when(stop: Path) -> None:
    while not stop.exists():
        time.sleep(0.05)
    for server in _Server.made:
        server.should_exit = True


def main(port: int, folder: Path) -> None:
    spans, logs = InMemorySpanExporter(), InMemoryLogExporter()  # type: ignore[no-untyped-call]
    tracer_provider = TracerProvider()
    tracer_provider.add_span_processor(SimpleSpanProcessor(spans))
    trace.set_tracer_provider(tracer_provider)
    reader = InMemoryMetricReader()
    metrics.set_meter_provider(MeterProvider(metric_readers=[reader]))
    logger_provider = LoggerProvider()
    logger_provider.add_log_record_processor(SimpleLogRecordProcessor(logs))
    _logs.set_logger_provider(logger_provider)
    setattr(phrase_cache, "PhraseCache", FakePhraseCache)  # noqa: B010 - a stand-in
    setattr(used_tokens, "SqliteUsedTokens", FakeUsedTokens)  # noqa: B010 - a stand-in
    setattr(uvicorn, "Server", _Server)  # noqa: B010 - a stand-in
    harness = Harness(dev_settings(folder), calls=_LoopCalls())
    threading.Thread(target=_stop_when, args=(folder / STOP,), daemon=True).start()
    serve(lambda: harness.runtime, port=port)
    data = reader.get_metrics_data()
    points = 0 if data is None else sum(len(m.scope_metrics) for m in data.resource_metrics)
    found: dict[str, Any] = {
        "selector": _LoopCalls.selector,
        "closed": harness.calls.closed,
        "spans": len(spans.get_finished_spans()),
        "metrics": points,
        "logs": len(logs.get_finished_logs()),
    }
    (folder / RESULT).write_text(json.dumps(found), encoding="utf-8")


if __name__ == "__main__":
    main(int(sys.argv[1]), Path(sys.argv[2]))

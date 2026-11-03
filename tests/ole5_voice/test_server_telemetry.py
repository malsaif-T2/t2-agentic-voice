"""FastAPI's own telemetry in the Ole5 app's server (ole5_voice/server.py): off, so a global
tracer, meter or logger provider receives nothing from the app (D-023), as plan 003's serving
criterion asks of both shapes; this file holds the mount's, Track F's tests the sidecar's."""

from __future__ import annotations

import json
import subprocess
import sys

from tests.isolation import child_shell

_TELEMETRY = """
import json, os
os.environ["FASTAPI_OTEL_AUTO_CONFIGURE"] = "true"
from opentelemetry import metrics, trace
from opentelemetry._logs import set_logger_provider
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs.export import InMemoryLogRecordExporter, SimpleLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

spans, logs, reader = InMemorySpanExporter(), InMemoryLogRecordExporter(), InMemoryMetricReader()
tracing = TracerProvider()
tracing.add_span_processor(SimpleSpanProcessor(spans))
trace.set_tracer_provider(tracing)
metrics.set_meter_provider(MeterProvider(metric_readers=[reader]))
logging = LoggerProvider()
logging.add_log_record_processor(SimpleLogRecordProcessor(logs))
set_logger_provider(logging)

from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient
from ole5_voice.server import build_app
from ole5_voice.settings import AppSettings, Settings
from pydantic import SecretStr
from t2_agentic_voice import VoiceSettings

class Minter:
    def mint(self, caller, *, consent):
        return "made-up-token"

def fail():
    raise RuntimeError("a made-up failure")

def counts(app):
    router = APIRouter()
    router.add_api_route("/fail", fail)
    app.include_router(router, prefix="/voice")
    with TestClient(app, raise_server_exceptions=False) as client:
        client.get("/")
        consent = {"version": None, "record_audio": False}
        client.post("/token", json={"code": "x", "consent": consent})
        client.get("/voice/fail")
    data = reader.get_metrics_data()
    points = sum(
        len(metric.data.data_points)
        for resource in (data.resource_metrics if data else ())
        for scope in resource.scope_metrics
        for metric in scope.metrics
    )
    found = {"spans": len(spans.get_finished_spans()), "points": points}
    found["logs"] = len(logs.get_finished_logs())
    spans.clear(); logs.clear()
    return found

app_settings = AppSettings(access_code=SecretStr("x" * 20))
settings = Settings(app=app_settings, voice=VoiceSettings(env="dev"))
ole5 = counts(build_app(settings, router=APIRouter(), minter=Minter()))
control = counts(FastAPI(telemetry={"auto_configure": False}))
print(json.dumps({"ole5": ole5, "control": control}))
"""


def test_fastapis_telemetry_reaches_no_global_provider() -> None:
    """In a child process with a global tracer, meter and logger provider and
    FASTAPI_OTEL_AUTO_CONFIGURE=true, the Ole5 app's requests (the page, the token route and a
    route that fails) give no span, metric or log record; a FastAPI app with its telemetry left
    on, as a control, gives them."""
    child = subprocess.run(
        [sys.executable, "-c", _TELEMETRY],
        env=child_shell(),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
        check=False,
    )
    assert child.returncode == 0, child.stderr
    found = json.loads(child.stdout.strip().splitlines()[-1])
    assert found["ole5"] == {"spans": 0, "points": 0, "logs": 0}
    assert min(found["control"].values()) > 0, found  # the providers do catch FastAPI's

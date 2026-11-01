"""The tracing helpers: OpenInference spans, redacted, never installed globally, never raising an
exporter's failure into the caller, and deaf to the `OTEL_*` variables they can keep out (plan
002's decision log; docs/SECURITY.md, invariants 5 and 8). Spans come from the SDK's in-memory
exporter, or a collector on 127.0.0.1."""

from __future__ import annotations

import http.server
import threading
import time
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest
import requests
from opentelemetry import trace
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExporter, SpanExportResult
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import Status, StatusCode
from requests.adapters import HTTPAdapter
from t2_agentic_voice.core import tracing as tracing_module
from t2_agentic_voice.core.config import Settings
from t2_agentic_voice.core.redaction import Redactor
from t2_agentic_voice.core.tracing import Tracing

MADE_UP_KEY = "gsk_made-up-key-for-tests-0123456789"
PHONE = "0512345678"
RESOURCE = {"service.name": "t2-agentic-voice", "openinference.project.name": "golden-set"}
NOBODY = "http://127.0.0.1:9"  # the discard port: nothing answers
SENT_HEADERS = {"host", "user-agent", "content-type", "content-length", "accept-encoding"}
Received = list[tuple[str, dict[str, str], bytes]]  # each request's path, headers and body


def _settings(tmp_path: Path, **tracing: object) -> Settings:
    values = {"env": "test", "var_dir": tmp_path, "groq": {"api_key": MADE_UP_KEY}}
    return Settings.model_validate(values | {"tracing": {"project": "golden-set"} | tracing})


def _one_turn(tracing: Tracing, text: str = "hello there") -> None:
    with (
        tracing.turn(session_id="run-1") as turn,
        tracing.speech_to_text(turn, model="m-1", language="ar", audio_seconds=1.5) as stt,
    ):
        stt.record(text=text, language="ar", billed_seconds=10.0)


def _turns(tracing: Tracing, count: int) -> None:
    for _ in range(count):
        with tracing.turn(session_id="more"):
            pass


def _private(**kwargs: Any) -> tuple[Tracing, InMemorySpanExporter]:
    exporter = InMemorySpanExporter()
    return Tracing(exporter=exporter, **({"project": "golden-set"} | kwargs)), exporter


def _finished(tracing: Tracing, exporter: InMemorySpanExporter) -> dict[str, ReadableSpan]:
    tracing.shutdown()
    return {span.name: span for span in exporter.get_finished_spans()}


def _exported_text(spans: Sequence[ReadableSpan]) -> str:
    """Everything a span exports, as text: names, attributes, events, links, status, resource."""
    parts: list[object] = []
    for span in spans:
        parts += [span.name, dict(span.attributes or {}), span.status.description]
        parts += [(e.name, dict(e.attributes or {})) for e in span.events]
        parts += [dict(link.attributes or {}) for link in span.links]
        parts += [dict(span.resource.attributes), span.instrumentation_scope]
    return repr(parts)


def test_a_turn_and_its_speech_to_text_span_carry_openinference_names() -> None:
    tracing, exporter = _private()
    _one_turn(tracing)
    spans = _finished(tracing, exporter)
    turn, stt = spans["turn"], spans["speech_to_text"]
    assert dict(turn.attributes or {}) == {
        "openinference.span.kind": "CHAIN",
        "session.id": "run-1",
    }
    assert dict(stt.attributes or {}) == {
        "openinference.span.kind": "LLM",
        "llm.model_name": "m-1",
        "stt.audio_seconds": 1.5,
        "stt.language_sent": "ar",
        "output.value": "hello there",
        "output.mime_type": "text/plain",
        "stt.language": "ar",
        "stt.billed_seconds": 10.0,
    }
    assert turn.parent is None and stt.parent == turn.context
    assert dict(turn.resource.attributes) == RESOURCE
    assert turn.instrumentation_scope is not None
    assert (turn.instrumentation_scope.name, tracing.dropped_spans) == ("t2_agentic_voice", 0)


def test_the_teams_provider_is_used_and_left_as_it_is(tmp_path: Path) -> None:
    """Even with an endpoint set. With `include_transcripts` off, only the transcript goes."""
    exporter = InMemorySpanExporter()
    team = TracerProvider(shutdown_on_exit=False)
    team.add_span_processor(SimpleSpanProcessor(exporter))
    settings = _settings(tmp_path, endpoint=f"{NOBODY}/v1/traces", include_transcripts=False)
    tracing = Tracing.from_settings(settings, tracer_provider=team)
    with (
        team.get_tracer("team").start_as_current_span("request") as own,
        tracing.speech_to_text(own, model="m", language=None, audio_seconds=2.0) as stt,
    ):
        stt.record(text="hello there", language="en", billed_seconds=None)
    request, stt_span = exporter.get_finished_spans()[::-1]
    assert stt_span.parent == request.context
    attributes = dict(stt_span.attributes or {})
    assert "output.value" not in attributes and "stt.language_sent" not in attributes
    assert attributes["stt.language"] == "en"
    assert "hello there" not in _exported_text([stt_span])
    tracing.shutdown()
    exporter.clear()
    _one_turn(tracing)  # the team's provider still works after the library's shutdown
    assert (len(exporter.get_finished_spans()), tracing.dropped_spans) == (2, 0)


def test_off_with_neither_and_never_global(tmp_path: Path, settings: Settings) -> None:
    """With no provider and no endpoint, tracing is off; none installs a provider globally."""
    before = trace.get_tracer_provider()
    team = TracerProvider(shutdown_on_exit=False)
    Tracing.from_settings(_settings(tmp_path, endpoint=f"{NOBODY}/v1/traces")).shutdown()
    for tracing, recording in (
        (Tracing(), False),
        (Tracing.from_settings(settings), False),
        (_private()[0], True),
        (Tracing.from_settings(settings, tracer_provider=team), True),
    ):
        with tracing.turn(session_id="run-1") as turn:
            assert turn.is_recording() is recording
            _one_turn(tracing)
        tracing.shutdown()
    assert trace.get_tracer_provider() is before
    assert isinstance(before, trace.ProxyTracerProvider)
    with pytest.raises(ValueError, match="not both"):
        Tracing(tracer_provider=team, exporter=InMemorySpanExporter())


def test_the_redaction_hook_runs_on_every_text_value() -> None:
    """The team's own values on the turn's span too; a bytes value (audio) and a mapping are
    dropped, and an exception is recorded by its type alone."""
    tracing, exporter = _private(project=f"golden {PHONE}", redactor=Redactor([r"05\d{8}"]))
    with tracing.turn(session_id=f"call-{PHONE}", name=f"turn {PHONE}") as turn:
        turn.set_attribute("note", f"number {PHONE}")
        turn.set_attributes({"heard": [f"a {PHONE}", "b"], "audio": b"\x00", "map": {"k": 1}})
        turn.add_event(f"heard {PHONE}", {"text": PHONE})
        turn.add_link(turn.get_span_context(), {"why": PHONE})
        turn.update_name(f"renamed {PHONE}")
        turn.record_exception(ValueError(f"bad {PHONE}"), {"where": PHONE})
        turn.set_status(Status(StatusCode.ERROR, f"failed for {PHONE}"))
        with tracing.speech_to_text(turn, model=PHONE, language=None, audio_seconds=1.0) as stt:
            stt.record(text=f"my number is {PHONE}", language=None, billed_seconds=None)
    spans = _finished(tracing, exporter)
    assert PHONE not in _exported_text(list(spans.values()))
    turn_span, stt_span = spans["renamed [redacted]"], spans["speech_to_text"]
    attributes = dict(turn_span.attributes or {})
    assert (attributes["session.id"], attributes["note"]) == (
        "call-[redacted]",
        "number [redacted]",
    )
    assert attributes["heard"] == ("a [redacted]", "b")
    assert "audio" not in attributes and "map" not in attributes
    events = {event.name: dict(event.attributes or {}) for event in turn_span.events}
    assert events["exception"] == {"where": "[redacted]", "exception.type": "ValueError"}
    assert turn_span.status.description == "failed for [redacted]"
    assert dict(stt_span.attributes or {})["output.value"] == "my number is [redacted]"
    assert turn_span.resource.attributes["openinference.project.name"] == "golden [redacted]"


def test_no_secret_reaches_a_span_or_a_log_line(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The made-up key in the settings, in the resource variables, in what was said (redacted)
    and in an exception's message: no attribute, event, status, resource or log line holds it,
    and the exception reaches the caller unchanged."""
    monkeypatch.setenv("OTEL_RESOURCE_ATTRIBUTES", f"leak={MADE_UP_KEY}")
    monkeypatch.setenv("OTEL_SERVICE_NAME", MADE_UP_KEY)
    settings = _settings(tmp_path, redact=[r"gsk_[\w-]+"])
    tracing, exporter = _private(redactor=Redactor(settings.tracing.redact))
    failure = RuntimeError(f"the key {MADE_UP_KEY} was refused")
    with (
        pytest.raises(RuntimeError) as raised,
        tracing.turn(session_id="run-1") as turn,
        tracing.speech_to_text(turn, model="m", language="en", audio_seconds=1.0) as stt,
    ):
        stt.record(text=f"my key is {MADE_UP_KEY}", language="en", billed_seconds=10.0)
        raise failure
    assert raised.value is failure
    spans = _finished(tracing, exporter)
    for span in spans.values():
        assert (span.status.status_code.name, span.status.description) == ("ERROR", "RuntimeError")
        assert (span.attributes or {})["error.type"] == "RuntimeError"
    shown = _exported_text(list(spans.values())) + capsys.readouterr().out + caplog.text
    assert MADE_UP_KEY not in shown and "[redacted]" in shown
    assert settings.groq.api_key is not None and MADE_UP_KEY not in repr(settings)


class _Failing(SpanExporter):
    """An exporter that raises, or says it failed; its close raises too."""

    def __init__(self, *, raises: bool) -> None:
        self.raises = raises

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        if self.raises:
            raise ConnectionError(f"refused with {MADE_UP_KEY}")
        return SpanExportResult.FAILURE

    def shutdown(self) -> None:
        raise OSError(f"cannot close with {MADE_UP_KEY}")


@pytest.mark.parametrize("raises", [True, False])
def test_an_exporter_that_fails_never_reaches_the_caller(
    raises: bool, capsys: pytest.CaptureFixture[str]
) -> None:
    """Its spans are counted as dropped, and logged once by the failure's type alone."""
    tracing = Tracing(exporter=_Failing(raises=raises))
    _one_turn(tracing)
    tracing.shutdown()
    tracing.shutdown()  # twice is harmless
    assert tracing.dropped_spans == 2
    out = capsys.readouterr().out
    assert out.count("span_export_failed") == 1 and "span_exporter_close_failed" in out
    assert ("ConnectionError" in out) is raises and MADE_UP_KEY not in out


class _Hanging(SpanExporter):
    def __init__(self) -> None:
        self.entered, self.release = threading.Event(), threading.Event()

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        self.entered.set()
        self.release.wait(10)
        return SpanExportResult.SUCCESS


def test_an_exporter_that_hangs_never_holds_the_caller(monkeypatch: pytest.MonkeyPatch) -> None:
    """The queue holds two spans while the first batch hangs; the next is dropped, and the two
    still queued when `shutdown` gives up are dropped too, all counted, as is a later span."""
    for name, value in (("_QUEUE_SPANS", 2), ("_BATCH_SPANS", 1), ("_CLOSE_S", 0.2)):
        monkeypatch.setattr(tracing_module, name, value)
    exporter = _Hanging()
    tracing = Tracing(exporter=exporter)
    try:
        started = time.monotonic()
        _turns(tracing, 1)
        assert exporter.entered.wait(5)
        _turns(tracing, 3)
        assert tracing.dropped_spans == 1
        tracing.shutdown()
        assert time.monotonic() - started < 2.0
        assert tracing.dropped_spans == 3
        _turns(tracing, 1)
        assert tracing.dropped_spans == 4
    finally:
        exporter.release.set()


SHELL = {
    "OTEL_RESOURCE_ATTRIBUTES": "team=made-up,service.name=made-up",
    "OTEL_SERVICE_NAME": "made-up-service",
    "OTEL_EXPERIMENTAL_RESOURCE_DETECTORS": "host,process",
    "OTEL_TRACES_SAMPLER": "always_off",
    "OTEL_BSP_MAX_QUEUE_SIZE": "1",
    "OTEL_BSP_MAX_EXPORT_BATCH_SIZE": "1",
    "OTEL_BSP_SCHEDULE_DELAY": "1",
    "OTEL_BSP_EXPORT_TIMEOUT": "1",
    "OTEL_ATTRIBUTE_COUNT_LIMIT": "1",
    "OTEL_ATTRIBUTE_VALUE_LENGTH_LIMIT": "3",
    "OTEL_SPAN_ATTRIBUTE_COUNT_LIMIT": "1",
    "OTEL_SPAN_ATTRIBUTE_VALUE_LENGTH_LIMIT": "3",
    "OTEL_PYTHON_SDK_INTERNAL_METRICS_ENABLED": "true",
    "OTEL_PYTHON_METER_PROVIDER": "made_up_meter_provider",  # loading it would raise
}


def _described(spans: Sequence[ReadableSpan]) -> list[tuple[str, object, object]]:
    return [(s.name, dict(s.attributes or {}), dict(s.resource.attributes)) for s in spans]


def test_otel_variables_change_no_span_resource_or_queue(monkeypatch: pytest.MonkeyPatch) -> None:
    tracing, exporter = _private()
    _one_turn(tracing)
    tracing.shutdown()
    baseline = _described(exporter.get_finished_spans())
    for name, value in SHELL.items():
        monkeypatch.setenv(name, value)
    tracing, exporter = _private()
    _one_turn(tracing)
    _turns(tracing, 3)
    tracing.shutdown()
    spans = exporter.get_finished_spans()
    assert (len(spans), tracing.dropped_spans) == (5, 0)
    assert _described(spans[:2]) == baseline  # the speech-to-text span, then its turn


def test_otel_sdk_disabled_still_turns_a_private_provider_off(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The SDK reads it whatever is passed (TD-005): the library says so, and exports nothing."""
    monkeypatch.setenv("OTEL_SDK_DISABLED", "true")
    tracing, exporter = _private()
    _one_turn(tracing)
    assert _finished(tracing, exporter) == {}
    assert "tracing_disabled_by_sdk" in capsys.readouterr().out


@contextmanager
def _collector(status: int) -> Iterator[tuple[str, Received]]:
    received: Received = []  # an OTLP/HTTP collector on 127.0.0.1

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            received.append((self.path, {k.lower(): v for k, v in self.headers.items()}, body))
            self.send_response(status)
            self.send_header("Content-Length", "0")
            self.end_headers()

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}/v1/traces", received
    finally:
        server.shutdown()
        server.server_close()


def test_otlp_over_http_sends_only_its_own_headers_and_trust(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The exporter's variables, set in the shell, change nothing: no header (a token among
    them), no other endpoint, no compression or timeout, no certificate or client key, no
    credential provider (each of these would change the request, or fail it, if read)."""
    monkeypatch.setenv("NO_PROXY", "127.0.0.1")
    token = f"Bearer {MADE_UP_KEY}"
    shell = SHELL | {
        "OTEL_EXPORTER_OTLP_HEADERS": f"authorization={token},x-made-up=1",
        "OTEL_EXPORTER_OTLP_TRACES_HEADERS": f"Authorization={token},Content-Type=text/plain",
        "OTEL_EXPORTER_OTLP_ENDPOINT": NOBODY,
        "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT": f"{NOBODY}/v1/traces",
        "OTEL_EXPORTER_OTLP_COMPRESSION": "gzip",
        "OTEL_EXPORTER_OTLP_TRACES_COMPRESSION": "gzip",
        "OTEL_EXPORTER_OTLP_TIMEOUT": "0.000001",
        "OTEL_EXPORTER_OTLP_TRACES_TIMEOUT": "0.000001",
        "OTEL_PYTHON_EXPORTER_OTLP_HTTP_CREDENTIAL_PROVIDER": "made_up_provider",
        "OTEL_PYTHON_EXPORTER_OTLP_HTTP_TRACES_CREDENTIAL_PROVIDER": "made_up_provider",
    }
    for kind in ("CERTIFICATE", "CLIENT_KEY", "CLIENT_CERTIFICATE"):
        for name in (f"OTEL_EXPORTER_OTLP_{kind}", f"OTEL_EXPORTER_OTLP_TRACES_{kind}"):
            shell[name] = str(tmp_path / f"made-up-{kind.lower()}.pem")
    for name, value in shell.items():
        monkeypatch.setenv(name, value)
    sent: list[dict[str, object]] = []
    send = HTTPAdapter.send

    def spy(adapter: HTTPAdapter, request: requests.PreparedRequest, **kwargs: Any) -> Any:
        sent.append(kwargs)
        return send(adapter, request, **kwargs)

    monkeypatch.setattr(HTTPAdapter, "send", spy)
    with _collector(200) as (endpoint, received):
        tracing = Tracing.from_settings(_settings(tmp_path, endpoint=endpoint))
        _one_turn(tracing)
        tracing.shutdown()
    [(path, headers, body)] = received
    assert (path, tracing.dropped_spans, set(headers) <= SENT_HEADERS) == ("/v1/traces", 0, True)
    assert headers["content-type"] == "application/x-protobuf"
    assert MADE_UP_KEY not in repr(headers) and MADE_UP_KEY.encode() not in body
    assert [(kwargs["verify"], kwargs["cert"]) for kwargs in sent] == [(True, None)]
    request = ExportTraceServiceRequest()
    request.ParseFromString(body)
    [resource_spans] = request.resource_spans
    resource = {a.key: a.value.string_value for a in resource_spans.resource.attributes}
    names = sorted(span.name for scope in resource_spans.scope_spans for span in scope.spans)
    assert (resource, names, b"run-1" in body) == (RESOURCE, ["speech_to_text", "turn"], True)


def test_a_backend_that_refuses_never_reaches_the_caller(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("NO_PROXY", "127.0.0.1")
    with _collector(400) as (endpoint, received):
        tracing = Tracing.from_settings(_settings(tmp_path, endpoint=endpoint))
        _one_turn(tracing)
        tracing.shutdown()
    assert (len(received), tracing.dropped_spans) == (1, 2)

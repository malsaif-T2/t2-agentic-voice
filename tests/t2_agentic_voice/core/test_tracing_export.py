"""The private provider (`core/tracing_export.py`): its bounded queue sends within its delay and
never raises a failing, hung or slow exporter into the caller, and the provider and its exporter
are deaf to the `OTEL_*` variables they keep out, a malformed header variable included (plan
002's decision log; docs/SECURITY.md, invariant 5). Spans go to the in-memory exporter or to a
collector on 127.0.0.1."""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest
import requests
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult
from requests.adapters import HTTPAdapter
from t2_agentic_voice.core import tracing_export
from t2_agentic_voice.core.tracing import Tracing

from tests.t2_agentic_voice.core.tracing_support import (
    MADE_UP_KEY,
    NOBODY,
    RESOURCE,
    SENT_HEADERS,
    TOKEN,
    collector,
    finished,
    one_turn,
    private,
    settings_with,
    turns,
)

# The last entry is malformed: the SDK logs such an entry with its text.
ENV_HEADERS = f"Authorization={TOKEN},x-made-up=1,Content-Type=text/plain,{TOKEN}"
# Entries the SDK decodes into a value and a name holding a line break, which requests refuses
# with the header in its error.
BROKEN_HEADERS = f"authorization=Bearer%0A{MADE_UP_KEY},x%0Ay=1"


@pytest.fixture(autouse=True)
def _no_proxy_and_no_netrc(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Requests to 127.0.0.1 go direct, and requests reads an empty .netrc of the test's own."""
    monkeypatch.setenv("NO_PROXY", "127.0.0.1")
    (tmp_path / "empty-netrc").write_text("", encoding="utf-8")
    monkeypatch.setenv("NETRC", str(tmp_path / "empty-netrc"))


class _Failing(SpanExporter):
    """An exporter that raises, or says it failed; its close raises too."""

    raises = True

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        if self.raises:
            raise ConnectionError(f"refused with {MADE_UP_KEY}")
        return SpanExportResult.FAILURE

    def shutdown(self) -> None:
        raise OSError(f"cannot close with {MADE_UP_KEY}")


@pytest.mark.parametrize("raises", [True, False])
def test_an_exporter_that_fails_never_reaches_the_caller(
    raises: bool, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Its spans are counted as dropped, and logged once by the failure's type alone."""
    monkeypatch.setattr(_Failing, "raises", raises)
    tracing = Tracing(exporter=_Failing())
    one_turn(tracing)
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
    """Two spans queue behind a hung batch; the rest, and a later span, are counted dropped."""
    for name, value in (("QUEUE_SPANS", 2), ("BATCH_SPANS", 1), ("CLOSE_S", 0.2)):
        monkeypatch.setattr(tracing_export, name, value)
    exporter = _Hanging()
    tracing = Tracing(exporter=exporter)
    try:
        started = time.monotonic()
        turns(tracing, 1)
        assert exporter.entered.wait(5)
        turns(tracing, 3)
        assert tracing.dropped_spans == 1
        tracing.shutdown()
        assert time.monotonic() - started < 2.0
        assert tracing.dropped_spans == 3
        turns(tracing, 1)
        assert tracing.dropped_spans == 4
    finally:
        exporter.release.set()


def test_a_span_is_sent_within_the_delay_with_no_full_batch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fewer spans than a batch still leave once the delay passes, before any `shutdown`."""
    monkeypatch.setattr(tracing_export, "DELAY_S", 0.05)
    tracing, exporter = private()
    try:
        one_turn(tracing)
        deadline = time.monotonic() + 2.0
        while len(exporter.get_finished_spans()) < 2 and time.monotonic() < deadline:
            time.sleep(0.01)
        assert len(exporter.get_finished_spans()) == 2
    finally:
        tracing.shutdown()


SHELL = {
    "OTEL_RESOURCE_ATTRIBUTES": "team=made-up,service.name=made-up",
    "OTEL_SERVICE_NAME": "made-up-service",
    "OTEL_EXPERIMENTAL_RESOURCE_DETECTORS": "host,process",
    "OTEL_TRACES_SAMPLER": "always_off",
    "OTEL_TRACES_SAMPLER_ARG": "0",
    "OTEL_BSP_MAX_QUEUE_SIZE": "1",
    "OTEL_BSP_MAX_EXPORT_BATCH_SIZE": "1",
    "OTEL_BSP_SCHEDULE_DELAY": "1",
    "OTEL_BSP_EXPORT_TIMEOUT": "1",
    "OTEL_ATTRIBUTE_COUNT_LIMIT": "1",
    "OTEL_ATTRIBUTE_VALUE_LENGTH_LIMIT": "3",
    "OTEL_SPAN_ATTRIBUTE_COUNT_LIMIT": "1",
    "OTEL_SPAN_ATTRIBUTE_VALUE_LENGTH_LIMIT": "3",
    "OTEL_SPAN_EVENT_COUNT_LIMIT": "0",
    "OTEL_SPAN_LINK_COUNT_LIMIT": "0",
    "OTEL_EVENT_ATTRIBUTE_COUNT_LIMIT": "0",
    "OTEL_LINK_ATTRIBUTE_COUNT_LIMIT": "0",
    "OTEL_PYTHON_SDK_INTERNAL_METRICS_ENABLED": "true",
    "OTEL_PYTHON_METER_PROVIDER": "made_up_meter_provider",  # loading it would raise
}


def _turn_with_an_event_and_a_link(tracing: Tracing) -> None:
    with tracing.turn(session_id="run-1") as turn:
        turn.add_event("heard", {"words": "two words"})
        turn.add_link(turn.get_span_context(), {"why": "the same turn"})
        with tracing.speech_to_text(turn, model="m-1", language="ar", audio_seconds=1.5) as stt:
            stt.record(text="hello there", language="ar", billed_seconds=10.0)


def _described(spans: Sequence[ReadableSpan]) -> list[tuple[object, ...]]:
    return [
        (
            s.name,
            dict(s.attributes or {}),
            dict(s.resource.attributes),
            [(e.name, dict(e.attributes or {})) for e in s.events],
            [dict(link.attributes or {}) for link in s.links],
        )
        for s in spans
    ]


def test_otel_variables_change_no_span_resource_or_queue(monkeypatch: pytest.MonkeyPatch) -> None:
    """The resource, sampler, batch and every limit variable: the span, event and link limits
    and their attributes' included, so the turn's event and link keep their attributes."""
    tracing, exporter = private()
    _turn_with_an_event_and_a_link(tracing)
    baseline = _described(list(finished(tracing, exporter).values()))
    for name, value in SHELL.items():
        monkeypatch.setenv(name, value)
    tracing, exporter = private()
    _turn_with_an_event_and_a_link(tracing)
    turns(tracing, 3)
    tracing.shutdown()
    spans = exporter.get_finished_spans()
    assert (len(spans), tracing.dropped_spans) == (5, 0)
    assert _described(spans[:2]) == baseline  # the speech-to-text span, then its turn
    assert [len(s.events) for s in spans[:2]] == [0, 1] and len(spans[1].links) == 1


def test_otel_sdk_disabled_still_turns_a_private_provider_off(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The SDK reads it whatever is passed (TD-005): the library says so, and exports nothing."""
    monkeypatch.setenv("OTEL_SDK_DISABLED", "true")
    tracing, exporter = private()
    one_turn(tracing)
    assert finished(tracing, exporter) == {}
    assert "tracing_disabled_by_sdk" in capsys.readouterr().out


def _spy_on_sends(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    sent: list[dict[str, Any]] = []
    send = HTTPAdapter.send

    def spy(adapter: HTTPAdapter, request: requests.PreparedRequest, **kwargs: Any) -> Any:
        sent.append(kwargs)
        return send(adapter, request, **kwargs)

    monkeypatch.setattr(HTTPAdapter, "send", spy)
    return sent


@pytest.mark.parametrize("form", ["", "TRACES_"])
def test_otlp_over_http_sends_only_its_own_headers_and_trust(
    form: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """The exporter's variables change no header (a token, even malformed), endpoint, compression,
    timeout, certificate, client key or credential provider: each would change the request."""
    shell = SHELL | {
        f"OTEL_EXPORTER_OTLP_{form}HEADERS": ENV_HEADERS,
        "OTEL_EXPORTER_OTLP_ENDPOINT": NOBODY,
        "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT": f"{NOBODY}/v1/traces",
        "OTEL_EXPORTER_OTLP_COMPRESSION": "gzip",
        "OTEL_EXPORTER_OTLP_TRACES_COMPRESSION": "gzip",
        "OTEL_EXPORTER_OTLP_TIMEOUT": "0.000001",
        "OTEL_EXPORTER_OTLP_TRACES_TIMEOUT": "0.000001",
        "OTEL_PYTHON_EXPORTER_OTLP_HTTP_CREDENTIAL_PROVIDER": "made_up_provider",
        "OTEL_PYTHON_EXPORTER_OTLP_HTTP_TRACES_CREDENTIAL_PROVIDER": "made_up_provider",
    }
    (tmp_path / "netrc").write_text(f"machine 127.0.0.1 login made-up password {MADE_UP_KEY}")
    shell["NETRC"] = str(tmp_path / "netrc")  # requests would send it as a login
    for kind in ("CERTIFICATE", "CLIENT_KEY", "CLIENT_CERTIFICATE"):
        for name in (f"OTEL_EXPORTER_OTLP_{kind}", f"OTEL_EXPORTER_OTLP_TRACES_{kind}"):
            shell[name] = str(tmp_path / f"made-up-{kind.lower()}.pem")
    for name, value in shell.items():
        monkeypatch.setenv(name, value)
    sent = _spy_on_sends(monkeypatch)
    with collector(200) as (endpoint, received):
        tracing = Tracing.from_settings(settings_with(tmp_path, endpoint=endpoint))
        one_turn(tracing)
        tracing.shutdown()
    [(path, headers, body)] = received
    assert (path, tracing.dropped_spans, set(headers) <= SENT_HEADERS) == ("/v1/traces", 0, True)
    assert headers["content-type"] == "application/x-protobuf"
    assert MADE_UP_KEY not in repr(headers) and MADE_UP_KEY.encode() not in body
    assert MADE_UP_KEY not in caplog.text  # the SDK quotes a malformed header variable
    assert logging.getLogger("opentelemetry.util.re").filters == []
    assert [(kwargs["verify"], kwargs["cert"]) for kwargs in sent] == [(True, None)]
    request = ExportTraceServiceRequest.FromString(body)
    [resource_spans] = request.resource_spans
    resource = {a.key: a.value.string_value for a in resource_spans.resource.attributes}
    names = sorted(span.name for scope in resource_spans.scope_spans for span in scope.spans)
    assert (resource, names, b"run-1" in body) == (RESOURCE, ["speech_to_text", "turn"], True)


@pytest.mark.parametrize("form", ["", "TRACES_"])
def test_a_header_variable_with_a_line_break_reaches_no_log_line_and_drops_no_span(
    form: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A `%0A` in the variable decodes to a line break, which requests refuses, quoting the
    header, before it is sent: the exporter would log that at ERROR and lose every batch. The
    session replaces the headers first, so the request goes out with its own alone."""
    caplog.set_level(logging.DEBUG)
    monkeypatch.setenv(f"OTEL_EXPORTER_OTLP_{form}HEADERS", BROKEN_HEADERS)
    with collector(200) as (endpoint, received):
        tracing = Tracing.from_settings(settings_with(tmp_path, endpoint=endpoint))
        one_turn(tracing)
        tracing.shutdown()
    [(_, headers, body)] = received
    assert (set(headers) <= SENT_HEADERS, tracing.dropped_spans) == (True, 0)
    assert MADE_UP_KEY not in repr(headers) and MADE_UP_KEY.encode() not in body
    shown = caplog.text + "".join(capsys.readouterr())
    assert MADE_UP_KEY not in shown and "Failed to export" not in shown


def test_a_backend_that_refuses_never_reaches_the_caller(tmp_path: Path) -> None:
    with collector(400) as (endpoint, received):
        tracing = Tracing.from_settings(settings_with(tmp_path, endpoint=endpoint))
        one_turn(tracing)
        tracing.shutdown()
    assert (len(received), tracing.dropped_spans) == (1, 2)


def test_a_backend_that_never_answers_is_given_up_on_within_the_export_timeout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The export's own timeout, not the exporter's 10 s or the queue's close limit, ends it:
    its spans are counted dropped and `shutdown` returns at once."""
    monkeypatch.setattr(tracing_export, "EXPORT_TIMEOUT_S", 0.2)
    with collector(200, hold=threading.Event()) as (endpoint, received):
        tracing = Tracing.from_settings(settings_with(tmp_path, endpoint=endpoint))
        one_turn(tracing)
        started = time.monotonic()
        tracing.shutdown()
        took = time.monotonic() - started
    assert (len(received) >= 1, tracing.dropped_spans) == (True, 2)
    assert took < 1.5  # the queue's close limit is 3 s

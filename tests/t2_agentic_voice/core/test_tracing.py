"""The tracing helpers: OpenInference spans, redacted, never global, a turn always the root of its
trace (plan 002's decision log; docs/SECURITY.md, invariants 5 and 8). The private provider's
queue and exporter are tested in test_tracing_export.py. Spans come from the in-memory exporter."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import Status, StatusCode
from pydantic import SecretStr
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.logging import configure_logging
from t2_agentic_voice.core.redaction import Redactor
from t2_agentic_voice.core.tracing import Tracing

from tests.leaks import holding, shown
from tests.t2_agentic_voice.core.tracing_support import (
    JOIN_KEY,
    MADE_UP_KEY,
    NOBODY,
    PHONE,
    RESOURCE,
    TURN_SECRET,
    exported_text,
    finished,
    one_turn,
    private,
    settings_with,
)


def test_a_turn_and_its_speech_to_text_span_carry_openinference_names() -> None:
    tracing, exporter = private()
    one_turn(tracing)
    spans = finished(tracing, exporter)
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
    assert (turn.parent, stt.parent) == (None, turn.context)
    scope = turn.instrumentation_scope.name if turn.instrumentation_scope else None
    assert (scope, tracing.dropped_spans) == ("t2_agentic_voice", 0)
    assert dict(turn.resource.attributes) == RESOURCE


def test_the_teams_provider_is_used_and_left_as_it_is(tmp_path: Path) -> None:
    """Even with an endpoint set. With `include_transcripts` off, only the transcript goes."""
    exporter = InMemorySpanExporter()
    team = TracerProvider(shutdown_on_exit=False)
    team.add_span_processor(SimpleSpanProcessor(exporter))
    settings = settings_with(tmp_path, endpoint=f"{NOBODY}/v1/traces", include_transcripts=False)
    tracing = Tracing.from_settings(settings, tracer_provider=team)
    with (
        team.get_tracer("team").start_as_current_span("request") as own,
        tracing.speech_to_text(own, model="m", language=None, audio_seconds=2.0) as stt,
    ):
        stt.record(text="hello there", language="en", billed_seconds=None)
    request, stt_span = exporter.get_finished_spans()[::-1]
    assert stt_span.parent == request.context
    attributes = dict(stt_span.attributes or {})
    assert {"output.value", "stt.language_sent"}.isdisjoint(attributes)
    assert attributes["stt.language"] == "en"
    assert "hello there" not in exported_text([stt_span])
    tracing.shutdown()
    exporter.clear()  # the team's provider still works after the library's shutdown
    one_turn(tracing)
    assert (len(exporter.get_finished_spans()), tracing.dropped_spans) == (2, 0)


def test_a_turn_is_the_root_of_its_trace_even_inside_a_teams_current_span() -> None:
    """The turn starts from an empty context, not from whatever span the app has current."""
    exporter = InMemorySpanExporter()
    team = TracerProvider(shutdown_on_exit=False)
    team.add_span_processor(SimpleSpanProcessor(exporter))
    tracing = Tracing(tracer_provider=team)
    with team.get_tracer("team").start_as_current_span("request"):
        one_turn(tracing)
    spans = {span.name: span for span in exporter.get_finished_spans()}
    assert spans["turn"].parent is None
    assert spans["turn"].context.trace_id != spans["request"].context.trace_id
    assert spans["speech_to_text"].parent == spans["turn"].context


def test_off_with_neither_and_never_global(tmp_path: Path, settings: VoiceSettings) -> None:
    """With no provider and no endpoint, tracing is off; none installs a provider globally."""
    before = trace.get_tracer_provider()
    team = TracerProvider(shutdown_on_exit=False)
    Tracing.from_settings(settings_with(tmp_path, endpoint=f"{NOBODY}/v1/traces")).shutdown()
    for tracing, recording in (
        (Tracing(), False),
        (Tracing.from_settings(settings), False),
        (private()[0], True),
        (Tracing.from_settings(settings, tracer_provider=team), True),
    ):
        with tracing.turn(session_id="run-1") as turn:
            assert turn.is_recording() is recording
            one_turn(tracing)
        tracing.shutdown()
    assert trace.get_tracer_provider() is before and isinstance(before, trace.ProxyTracerProvider)
    with pytest.raises(ValueError, match="not both"):
        Tracing(tracer_provider=team, exporter=InMemorySpanExporter())


def test_the_redaction_hook_runs_on_every_text_value() -> None:
    """The team's own values on the turn's span too, and every attribute's key, on the span, an
    event and a link; a bytes value (audio) and a mapping are dropped, and an exception is
    recorded by its type alone."""
    tracing, exporter = private(project=f"golden {PHONE}", redactor=Redactor([r"05\d{8}"]))
    with tracing.turn(session_id=f"call-{PHONE}", name=f"turn {PHONE}") as turn:
        turn.set_attribute("note", f"number {PHONE}")
        turn.set_attribute(f"caller.{PHONE}", "known")
        turn.set_attributes({"heard": [f"a {PHONE}", "b"], "audio": b"\x00", "map": {"k": 1}})
        turn.add_event(f"heard {PHONE}", {"text": PHONE, f"heard.{PHONE}": 1})
        turn.add_link(turn.get_span_context(), {"why": PHONE, f"link.{PHONE}": True})
        turn.update_name(f"renamed {PHONE}")
        turn.record_exception(ValueError(f"bad {PHONE}"), {"where": PHONE})
        turn.set_status(Status(StatusCode.ERROR, f"failed for {PHONE}"))
        with tracing.speech_to_text(turn, model=PHONE, language=None, audio_seconds=1.0) as stt:
            stt.record(text=f"my number is {PHONE}", language=None, billed_seconds=None)
    spans = finished(tracing, exporter)
    assert PHONE not in exported_text(list(spans.values()))
    turn_span, stt_span = spans["renamed [redacted]"], spans["speech_to_text"]
    attributes = dict(turn_span.attributes or {})
    assert (attributes["session.id"], attributes["note"]) == (
        "call-[redacted]",
        "number [redacted]",
    )
    assert attributes["caller.[redacted]"] == "known"
    assert attributes["heard"] == ("a [redacted]", "b")
    assert "audio" not in attributes and "map" not in attributes
    events = {event.name: dict(event.attributes or {}) for event in turn_span.events}
    assert events["heard [redacted]"] == {"text": "[redacted]", "heard.[redacted]": 1}
    assert events["exception"] == {"where": "[redacted]", "exception.type": "ValueError"}
    [link] = turn_span.links
    assert dict(link.attributes or {}) == {"why": "[redacted]", "link.[redacted]": True}
    assert turn_span.status.description == "failed for [redacted]"
    assert dict(stt_span.attributes or {})["output.value"] == "my number is [redacted]"
    assert turn_span.resource.attributes["openinference.project.name"] == "golden [redacted]"


def _secrets(tmp_path: Path, in_files: bool) -> dict[str, object]:
    """The settings' join keys and TURN secret, made up, inline (the Groq key is inline in
    `settings_with`'s settings already) or each in its file, the Groq key's too."""
    if not in_files:
        return {"join": {"keys": {"k1": JOIN_KEY}}, "server": {"turn_secret": TURN_SECRET}}
    (groq := tmp_path / "groq.key").write_text(MADE_UP_KEY, encoding="utf-8")
    (keys := tmp_path / "join.keys").write_text(json.dumps({"k1": JOIN_KEY}), encoding="utf-8")
    (turn := tmp_path / "turn.secret").write_text(TURN_SECRET, encoding="utf-8")
    files: dict[str, object] = {"join": {"keys_file": keys}, "server": {"turn_secret_file": turn}}
    return files | {"groq": {"api_key_file": groq}}  # in place of the inline key


@pytest.mark.parametrize("in_files", [False, True])
def test_no_secret_reaches_a_span_or_a_log_line(
    in_files: bool,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The made-up Groq key in the resource variables, in what was said (redacted) and in an
    exception's message, and the settings' made-up Groq key, join key and TURN secret, inline
    or in their files: no attribute, event, status, resource or log line of the private
    provider the settings build holds one, at DEBUG too, and the exception reaches the caller
    unchanged."""
    monkeypatch.setenv("OTEL_RESOURCE_ATTRIBUTES", f"leak={MADE_UP_KEY}")
    monkeypatch.setenv("OTEL_SERVICE_NAME", MADE_UP_KEY)
    exporter = InMemorySpanExporter()  # in place of the OTLP exporter the endpoint asks for
    monkeypatch.setattr("t2_agentic_voice.core.tracing.otlp_exporter", lambda _: exporter)
    settings = settings_with(
        tmp_path,
        groups=_secrets(tmp_path, in_files),
        endpoint=f"{NOBODY}/v1/traces",
        redact=[r"gsk_[\w-]+"],
    )
    configure_logging("DEBUG", "json")  # tests/conftest.py undoes it
    caplog.set_level(logging.DEBUG)
    tracing = Tracing.from_settings(settings)
    failure = RuntimeError(f"the key {MADE_UP_KEY} was refused")
    with (
        pytest.raises(RuntimeError) as raised,
        tracing.turn(session_id="run-1") as turn,
        tracing.speech_to_text(turn, model="m", language="en", audio_seconds=1.0) as stt,
    ):
        stt.record(text=f"my key is {MADE_UP_KEY}", language="en", billed_seconds=10.0)
        raise failure
    assert raised.value is failure
    spans = finished(tracing, exporter)
    for span in spans.values():
        assert (span.status.status_code.name, span.status.description) == ("ERROR", "RuntimeError")
        assert (span.attributes or {})["error.type"] == "RuntimeError"
    surfaces = shown(caplog=caplog, capsys=capsys)
    surfaces["spans"] = exported_text(list(spans.values()))
    assert set(spans) == {"turn", "speech_to_text"} and "[redacted]" in surfaces["spans"]
    for secret in (MADE_UP_KEY, JOIN_KEY, TURN_SECRET):
        assert holding(secret, surfaces) == [], secret
    assert (settings.groq.api_key is None) is in_files and MADE_UP_KEY not in repr(settings)
    assert settings.groq.resolved_api_key() == SecretStr(MADE_UP_KEY)  # but it is there

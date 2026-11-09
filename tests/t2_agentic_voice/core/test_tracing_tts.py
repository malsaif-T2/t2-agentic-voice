"""What a call's traces carry beside the turn and its speech-to-text span (core/tracing_tts.py):
the settings' digest, unchanged when a secret or the file holding one changes, changed by any
other setting; the resource attributes; the text-to-speech span, redacted and holding no text;
and `CallTrace`, one call's spans opened and ended as it goes, holding no secret."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from openinference.semconv.trace import SpanAttributes
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.redaction import Redactor
from t2_agentic_voice.core.tracing import Tracing
from t2_agentic_voice.core.tracing_export import VERSION
from t2_agentic_voice.core.tracing_tts import (
    AGENT_NAME,
    CONSENT_VERSION,
    LIBRARY_VERSION,
    MODELS,
    PIPECAT_VERSION,
    SETTINGS_DIGEST,
    CallTrace,
    ReplyNumbers,
    resource_attributes,
    settings_digest,
)

from tests.leaks import holding
from tests.t2_agentic_voice.core.tracing_support import (
    JOIN_KEY,
    MADE_UP_KEY,
    TURN_SECRET,
    exported_text,
    finished,
    private,
)

OTHER_KEY = "gsk_another-made-up-key-for-tests-98765"
OTHER_JOIN_KEY = "another-made-up-join-key-for-tests-98765"
OTHER_TURN_SECRET = "another-made-up-turn-secret-for-tests-987"
NUMBERS = ReplyNumbers(
    characters=21, chunks=4, requests=1, cache_hits=1, first_audio_ms=180.0, cut_short=False
)


def _settings(tmp_path: Path, **groups: object) -> VoiceSettings:
    return VoiceSettings.model_validate({"env": "test", "storage": {"var_dir": tmp_path}} | groups)


def _secrets(
    tmp_path: Path, key: str, join: str, turn: str, *, in_files: bool
) -> dict[str, object]:
    """The settings' Groq key, join keys and TURN secret, inline or each in its own file."""
    if not in_files:
        return {
            "groq": {"api_key": key},
            "join": {"keys": {"k1": join}},
            "server": {"turn_secret": turn},
        }
    folder = tmp_path / key[-5:]
    folder.mkdir()
    (groq := folder / "groq.key").write_text(key, encoding="utf-8")
    (keys := folder / "join.keys").write_text(json.dumps({"k1": join}), encoding="utf-8")
    (secret := folder / "turn.secret").write_text(turn, encoding="utf-8")
    return {
        "groq": {"api_key_file": groq},
        "join": {"keys_file": keys},
        "server": {"turn_secret_file": secret},
    }


@pytest.mark.parametrize("in_files", [False, True], ids=["inline", "in-files"])
def test_the_settings_digest_leaves_out_every_secret_and_its_file(
    tmp_path: Path, in_files: bool
) -> None:
    """Another Groq key, join key and TURN secret, inline or in other files, give the same
    digest as the first, and as none at all; another setting gives another digest. The digest
    holds none of the secrets."""
    first = _settings(
        tmp_path, **_secrets(tmp_path, MADE_UP_KEY, JOIN_KEY, TURN_SECRET, in_files=in_files)
    )
    other = _settings(
        tmp_path,
        **_secrets(tmp_path, OTHER_KEY, OTHER_JOIN_KEY, OTHER_TURN_SECRET, in_files=in_files),
    )
    digest = settings_digest(first)
    assert digest == settings_digest(other) == settings_digest(_settings(tmp_path))
    assert len(digest) == 64 and int(digest, 16) >= 0
    for secret in (MADE_UP_KEY, JOIN_KEY, TURN_SECRET):
        assert secret not in digest
    changed = _settings(tmp_path, stt={"model": "whisper-large-v3-turbo"})
    assert settings_digest(changed) != digest


def test_the_resource_attributes_name_the_versions_the_digest_the_agent_and_the_consent(
    settings: VoiceSettings,
) -> None:
    found = resource_attributes(
        settings, agent="echo-test", models=("m-1", "m-2"), consent_version="v1"
    )
    assert found[LIBRARY_VERSION] == VERSION and isinstance(found[PIPECAT_VERSION], str)
    assert found[SETTINGS_DIGEST] == settings_digest(settings)
    assert (found[AGENT_NAME], found[MODELS], found[CONSENT_VERSION]) == (
        "echo-test",
        ["m-1", "m-2"],
        "v1",
    )
    unversioned = resource_attributes(settings, agent="echo-test", models=(), consent_version=None)
    assert CONSENT_VERSION not in unversioned


def test_a_call_trace_opens_and_ends_each_span_under_its_parent() -> None:
    """The call's root and each turn's root carry `session.id` and the resource attributes;
    the speech-to-text and text-to-speech spans sit under their turn's, a reply that answers no
    turn (or whose turn has ended) under the call's; a span still open at `close` ends then;
    and a report for a span never opened changes nothing."""
    tracing, exporter = private(redactor=None)
    trace = CallTrace(tracing, call_id="call-7", resource={AGENT_NAME: "echo-test"})
    trace.started()
    trace.turn_opened(0)
    trace.stt_sent(0, model="m-1", language="en", audio_seconds=2.0)
    trace.stt_heard(0, text="hello there", language="en", billed_seconds=10.0)
    trace.tts_started(1, 0, model="m-2", voice="troy", language="en")
    trace.tts_ended(1, NUMBERS)
    trace.turn_ended(0, {"turn.dropped": False, "turn.ttfa_ms": 400.0})
    trace.tts_started(2, 0, model="m-2", voice="troy", language="en")  # its turn has ended
    trace.stt_sent(1, model="m-1", language=None, audio_seconds=1.0)  # opens turn 1 too
    trace.tts_started(3, None, model="m-2", voice="troy", language="en")
    trace.stt_heard(9, text="", language=None, billed_seconds=None)  # never sent
    trace.tts_ended(9, NUMBERS)
    trace.turn_ended(9, {})
    trace.close({"call.turns": 2})
    spans = finished(tracing, exporter)
    assert set(spans) == {"call", "turn", "speech_to_text", "text_to_speech"}
    every = exporter.get_finished_spans()
    roots = {s.name: s for s in every if s.parent is None}
    sessions = {(s.attributes or {}).get(SpanAttributes.SESSION_ID) for s in roots.values()}
    assert sessions == {"call-7"}
    assert all((s.attributes or {})[AGENT_NAME] == "echo-test" for s in every if s.parent is None)
    assert (roots["call"].attributes or {})["call.turns"] == 2
    under_call = [
        s for s in every if s.parent and s.parent.span_id == roots["call"].context.span_id
    ]
    assert len(under_call) == 2 and {s.name for s in under_call} == {"text_to_speech"}
    tts = next(
        s for s in every if s.name == "text_to_speech" and (s.attributes or {}).get("tts.requests")
    )
    assert (tts.attributes or {})["tts.first_audio_ms"] == 180.0
    assert (tts.attributes or {})[SpanAttributes.LLM_MODEL_NAME] == "m-2"
    assert len([s for s in every if s.name == "turn"]) == 2


def test_a_reply_with_no_first_audio_leaves_its_time_out_and_a_closed_trace_reopens_none() -> None:
    tracing, exporter = private()
    trace = CallTrace(tracing, call_id="call-8", resource={})
    trace.tts_started(0, None, model="m-2", voice="troy", language="en")  # opens the call's span
    no_audio = ReplyNumbers(
        characters=0, chunks=0, requests=0, cache_hits=1, first_audio_ms=None, cut_short=True
    )
    trace.tts_ended(0, no_audio)
    trace.close({})
    spans = finished(tracing, exporter)
    attributes = spans["text_to_speech"].attributes or {}
    assert "tts.first_audio_ms" not in attributes and attributes["tts.cut_short"] is True


def test_no_secret_reaches_a_call_traces_spans(tmp_path: Path) -> None:
    """The resource attributes of settings holding the made-up Groq key, join key and TURN
    secret, and a text holding the key, which the team's redaction hook names: no span holds a
    secret."""
    secrets = _secrets(tmp_path, MADE_UP_KEY, JOIN_KEY, TURN_SECRET, in_files=False)
    settings = _settings(tmp_path, **secrets)
    tracing, exporter = private(redactor=Redactor([r"gsk_[\w-]+"]))
    resource = resource_attributes(settings, agent="echo-test", models=("m",), consent_version=None)
    trace = CallTrace(tracing, call_id="call-9", resource=resource)
    trace.turn_opened(0)
    trace.tts_started(1, 0, model="m", voice=f"v {MADE_UP_KEY}", language="en")
    trace.tts_ended(1, NUMBERS)
    trace.close({})
    shown = exported_text(list(finished(tracing, exporter).values()))
    for secret in (MADE_UP_KEY, JOIN_KEY, TURN_SECRET):
        assert holding(secret, {"spans": shown}) == []
    assert "[redacted]" in shown


def test_a_tool_call_is_a_span_under_its_turn_naming_what_failed() -> None:
    """D-078: its name, whether it worked and what failed; one left open ends with its turn."""
    tracing, exporter = private(redactor=None)
    trace = CallTrace(tracing, call_id="call-7", resource={AGENT_NAME: "echo-test"})
    trace.started()
    trace.turn_opened(0)
    trace.tool_began(0, "t-1", tool="search_help")
    trace.tool_ended("t-1", ok=False, failure="timeout at search")
    trace.tool_began(0, "t-2", tool="search_help")  # the turn ends first
    trace.tool_began(9, "t-3", tool="search_help")  # no such turn is open: no span
    trace.tool_ended("t-4", ok=True, failure=None)  # never began
    trace.turn_ended(0, {})
    trace.close({})
    tracing.shutdown()
    every = exporter.get_finished_spans()
    turn = next(s for s in every if s.name == "turn")
    tools = [s for s in every if s.name == "tool"]
    assert len(tools) == 2 and all(
        s.parent and s.parent.span_id == turn.context.span_id for s in tools
    )
    failed = dict(tools[0].attributes or {})
    assert failed["tool.ok"] is False and failed["tool.failure"] == "timeout at search"
    assert failed[SpanAttributes.TOOL_NAME] == "search_help"
    assert "tool.ok" not in dict(tools[1].attributes or {})


def _spoken_call(tracing: Tracing) -> None:
    trace = CallTrace(tracing, call_id="call-7", resource={AGENT_NAME: "echo-test"})
    trace.started()
    trace.turn_opened(0)
    trace.tool_began(0, "t-1", tool="search_help", arguments='{"query": "made up 123"}')
    trace.tool_ended("t-1", ok=True, failure=None)
    trace.tts_started(1, 0, model="m-2", voice="troy", language="en")
    trace.tts_ended(1, NUMBERS, text="Made-up reply 123.")
    trace.turn_ended(0, {}, heard="made-up words 123", said="Made-up reply 123.")
    trace.close({})
    tracing.shutdown()


def test_each_span_holds_what_was_said_when_transcripts_are_on_and_redacted() -> None:
    """D-079: the turn what was heard and said, the reply its text, the tool its arguments."""
    tracing, exporter = private(redactor=lambda text: text.replace("123", "[redacted]"))
    _spoken_call(tracing)
    spans = {s.name: dict(s.attributes or {}) for s in exporter.get_finished_spans()}
    assert spans["turn"][SpanAttributes.INPUT_VALUE] == "made-up words [redacted]"
    assert spans["turn"][SpanAttributes.OUTPUT_VALUE] == "Made-up reply [redacted]."
    assert spans["text_to_speech"][SpanAttributes.INPUT_VALUE] == "Made-up reply [redacted]."
    assert spans["tool"][SpanAttributes.INPUT_VALUE] == '{"query": "made up [redacted]"}'


def test_no_span_holds_what_was_said_with_transcripts_off() -> None:
    tracing, exporter = private(redactor=None, include_transcripts=False)
    _spoken_call(tracing)
    assert "made" not in exported_text(exporter.get_finished_spans()).lower()

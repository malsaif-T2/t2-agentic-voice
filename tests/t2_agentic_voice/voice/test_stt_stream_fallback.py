"""When a call's stream cannot answer (voice/stt_stream.py, stt_streamed.py; plan 010's 5.1), on
ElevenLabs' adapter and a fake Scribe v3 Live socket: a lost socket or a commit left unanswered
sends the turn by request after all, and the rest of the call goes by request, logged once with
no words; a stream that does not open leaves the call to requests; the call's end closes the
stream and cancels a request waiting on it; an overlap keeps its requests, and its audio, like a
turn's heard before the stream was ready or open as it opened, is committed at its close and its
words never reach a later turn; the pipeline streams only with the setting on, and the runtime's
start says once
when the setting is on and its calls cannot stream."""

from __future__ import annotations

import asyncio
from contextlib import AsyncExitStack

import pytest
from pydantic import SecretStr
from t2_agentic_voice.adapters.elevenlabs_stt import ElevenLabsSTT
from t2_agentic_voice.api.providers import Providers
from t2_agentic_voice.api.providers import opened as runtime_opened
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.identity import Caller, Consent
from t2_agentic_voice.core.logging import FIELDS
from t2_agentic_voice.core.settings.stt import SttSettings
from t2_agentic_voice.core.tracing import Tracing
from t2_agentic_voice.voice import stt_stream
from t2_agentic_voice.voice.calls import VoiceCalls
from t2_agentic_voice.voice.file_transport import file_output
from t2_agentic_voice.voice.session.session_events import Transcribed, Transcribing
from t2_agentic_voice.voice.stt_stream import CallStream, StreamHooks
from t2_agentic_voice.voice.turn_hold import TurnHeldFrame

from tests.leaks import holding, shown
from tests.t2_agentic_voice.adapters.live_support import BATCH_WORDS, FakeScribe, refused
from tests.t2_agentic_voice.adapters.provider_support import KEY, closed
from tests.t2_agentic_voice.fakes import FakePhrases, FakeSpeechToText, FakeTextToSpeech
from tests.t2_agentic_voice.session_fakes import AGENT
from tests.t2_agentic_voice.voice.kit import PauseAnalyzer, ToneVAD, audio_frames
from tests.t2_agentic_voice.voice.stream_kit import Step, heard, held_turn, loud_s, opened, stopped
from tests.t2_agentic_voice.voice.stream_kit import closed as turn_closed

FULL = "I want to reset my password"


def _lost(caplog: pytest.LogCaptureFixture) -> list[dict[str, object]]:
    """The fields of each `stt_stream_lost` line."""
    return [getattr(r, FIELDS) for r in caplog.records if r.getMessage() == "stt_stream_lost"]


def test_a_lost_socket_sends_the_turn_by_request_and_the_rest_of_the_call_too(
    caplog: pytest.LogCaptureFixture,
) -> None:
    scribe = FakeScribe([closed(1011), FULL])
    call = heard(scribe, [*held_turn(), *held_turn()], turns=2)
    assert call.words("held") == [BATCH_WORDS, BATCH_WORDS]  # the second never streamed
    assert len(call.batch.requests) == 2 and scribe.commits() == 1
    ((line),) = _lost(caplog)
    assert (line["at"], line["kind"], line["reason"]) == (
        "call",
        "connection_lost",
        "ConnectionClosedError",
    )
    assert scribe.closes == 1
    assert holding(FULL, shown(caplog=caplog)) == [] and holding(KEY, shown(caplog=caplog)) == []


def test_a_commit_left_unanswered_sends_the_turn_by_request(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(stt_stream, "FINAL_WAIT_S", 0.1)
    scribe = FakeScribe([None])
    call = heard(scribe, held_turn())
    assert call.words("held") == [BATCH_WORDS] and len(call.batch.requests) == 1
    (held,), (sent,) = call.of("held"), call.session.of(Transcribing)
    assert held.sent_at == sent.at and held.at > sent.at  # timed from the commit, one request
    ((line),) = _lost(caplog)
    assert (line["kind"], line["reason"]) == ("timeout", "no_final")


def test_a_stream_that_does_not_open_leaves_the_call_to_requests(
    caplog: pytest.LogCaptureFixture,
) -> None:
    scribe = FakeScribe(started=(refused("auth_error", FULL),))
    call = heard(scribe, [0.1, *held_turn()], lead=False)
    assert call.words("held") == [BATCH_WORDS] and scribe.commits() == 0
    ((line),) = _lost(caplog)
    assert (line["at"], line["kind"], line["reason"]) == ("open", "rejected", "auth_error")
    assert holding(FULL, shown(caplog=caplog)) == []


def test_the_calls_end_closes_the_stream_and_cancels_a_request_waiting_on_it() -> None:
    scribe = FakeScribe([None])
    call = heard(scribe, [*held_turn(), 0.3], ended=True)  # ended within the commit's wait
    assert call.sent() == ["held"] and call.session.of(Transcribed) == []
    assert scribe.closes == 1 and call.batch.requests == []


def test_an_overlap_keeps_its_requests_and_its_words_reach_no_later_turn() -> None:
    scribe = FakeScribe(["words over the reply", FULL])
    mark: Step = lambda stt: stt.hear_overlap(0, 750)  # noqa: E731
    overlap: list[Step] = [*opened(), 0.1, mark, *stopped(), 0.05, TurnHeldFrame()]
    overlap += turn_closed()
    call = heard(scribe, [*overlap, *held_turn()], turns=2)
    assert call.sent()[:2] == ["window", "overlap"] and len(call.batch.requests) == 2
    assert call.words("turn") == [BATCH_WORDS, FULL]  # the overlap's own reuses its part
    assert scribe.commits() == 2  # the overlap's audio committed at its close, words dropped


def test_a_turn_open_as_the_stream_opens_has_its_audio_committed_at_its_close() -> None:
    """The caller already speaks as the stream opens (its connection takes 0.3 s here): the
    turn goes by request, and its audio fed since is committed as it closes, its words dropped,
    so none of it reaches the next turn's."""
    scribe = FakeScribe(["words of the first turn", FULL], open_s=0.3)
    first: list[Step] = [*opened(), 0.6, *audio_frames(1.0), *stopped(), 0.05, TurnHeldFrame()]
    silence: list[Step] = list(audio_frames(3.0, loud=False))
    call = heard(scribe, [*first, *turn_closed(), *silence, *held_turn()], lead=False, turns=2)
    assert call.words("held") == [BATCH_WORDS, FULL] and len(call.batch.requests) == 1
    assert loud_s(scribe) == [1.0, 0.5]  # the first turn's speech since the open, the second's


def test_a_turn_before_the_stream_heard_its_lead_goes_by_request() -> None:
    scribe = FakeScribe(["words of the first turn", FULL])
    silence: list[Step] = list(audio_frames(2.2, loud=False))
    call = heard(scribe, [0.1, *held_turn(), *silence, *held_turn()], lead=False, turns=2)
    assert call.words("held") == [BATCH_WORDS, FULL] and len(call.batch.requests) == 1
    assert scribe.commits() == 2


@pytest.mark.parametrize("on", [True, False], ids=["on", "off by default"])
def test_the_pipeline_streams_only_with_the_setting_on(settings: VoiceSettings, on: bool) -> None:
    given = settings.model_copy(update={"stt": SttSettings(streaming=on)})
    stt = ElevenLabsSTT(api_key=SecretStr(KEY), timeout_s=2.0, opener=FakeScribe().opener)
    calls = VoiceCalls(
        agent=AGENT,
        settings=given,
        stt=stt,
        tts=FakeTextToSpeech(),
        phrases=FakePhrases.of(AGENT),
        tracing=Tracing(),
        emit=lambda event: None,
    )
    pipeline = calls._pipeline(
        "call-1",
        (ToneVAD(), PauseAnalyzer()),
        caller=Caller(subject="made-up"),
        consent=Consent(version=None, record_audio=False),
        language=AGENT.languages[0],
        output=file_output(),
    )
    kind = CallStream if on else StreamHooks
    assert type(pipeline.stt_bridge.stream) is kind


@pytest.mark.parametrize(
    ("stt", "streams", "reasons"),
    [
        (SttSettings(streaming=True, provider="groq"), False, ["provider_does_not_stream"]),
        (SttSettings(streaming=True, live_language="detected"), True, ["live_language"]),
        (SttSettings(streaming=True), True, []),
        (SttSettings(), False, []),
    ],
    ids=["a batch provider", "detected", "session", "off"],
)
def test_the_start_says_once_when_its_calls_cannot_stream(
    stt: SttSettings, streams: bool, reasons: list[str], caplog: pytest.LogCaptureFixture
) -> None:
    given = ElevenLabsSTT(api_key=SecretStr(KEY), timeout_s=2.0) if streams else None
    providers = Providers(stt=given or FakeSpeechToText(), tts=FakeTextToSpeech())

    async def start() -> None:
        async with AsyncExitStack() as stack:
            await runtime_opened(providers, AGENT, VoiceSettings(env="test", stt=stt), stack)

    asyncio.run(start())
    lines = [getattr(r, FIELDS) for r in caplog.records if r.getMessage() == "streaming_off"]
    assert [line["reason"] for line in lines] == reasons

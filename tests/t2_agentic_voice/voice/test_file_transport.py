"""The file-fed transport (voice/file_transport.py): a call whose caller is a clip, through the
same Pipecat modules as a call over WebRTC, with the fakes' detectors and providers."""

from __future__ import annotations

import asyncio
import time

import pytest
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.errors import InvalidRequestError, T2VoiceError
from t2_agentic_voice.core.identity import Caller, Consent
from t2_agentic_voice.domain.ports.speech_to_text import AudioClip
from t2_agentic_voice.voice import file_transport
from t2_agentic_voice.voice.file_transport import FRAME_S, FedCall, feed_file, pace
from t2_agentic_voice.voice.protocol import State
from t2_agentic_voice.voice.session.commands import Command, HangUp, Send, Speak
from t2_agentic_voice.voice.session.session_events import (
    ClausePlayed,
    ClauseQueued,
    Connected,
    Ending,
    SessionEvent,
    Synthesizing,
    Transcribed,
    Transcribing,
    TurnClosed,
    TurnOpened,
)

from tests.t2_agentic_voice.fakes import FakeSpeechToText, tone
from tests.t2_agentic_voice.session_fakes import AGENT
from tests.t2_agentic_voice.voice.kit import Built, voice_calls

CALLER, CONSENT = Caller(subject="made-up"), Consent(version=None, record_audio=False)


def _feed(built: Built, clip: AudioClip, *, lead_s: float = 0.4, tail_s: float = 1.5) -> FedCall:
    async def run() -> FedCall:
        await built.calls.start()
        try:
            return await feed_file(
                built.calls,
                clip,
                call_id="call-1",
                caller=CALLER,
                consent=CONSENT,
                language=AGENT.languages[0],
                lead_s=lead_s,
                tail_s=tail_s,
            )
        finally:
            await built.calls.aclose()

    return asyncio.run(asyncio.wait_for(run(), timeout=60))


def test_a_file_fed_call_greets_hears_a_turn_and_says_it_back(settings: VoiceSettings) -> None:
    """The tail waits out the hold after Smart Turn's "complete" (`turns.complete_hold_ms`) as
    well, so the turn ends and its reply plays before the clip's call ends."""
    built = voice_calls(settings, stt=FakeSpeechToText(["hello there"]))
    hold_s = settings.turns.complete_hold_ms / 1000
    fed = _feed(built, AudioClip(pcm16=tone(0.8, 16_000)), tail_s=1.5 + hold_s)
    kinds = [type(e) for e in fed.events if type(e).__name__ not in ("CallerAudio", "AgentAudio")]
    assert kinds[0] is Connected and kinds[-1] is Ending
    played = [e for e in fed.events if isinstance(e, ClausePlayed)]
    assert [(e.reply_id, e.clause) for e in played] == [(0, 0), (1, 0)]
    for kind in (TurnOpened, TurnClosed, Transcribing, Transcribed, Synthesizing, ClauseQueued):
        assert kind in kinds
    (heard,) = [e for e in fed.events if isinstance(e, Transcribed)]
    assert heard.transcript is not None and heard.transcript.text == "hello there"
    assert fed.started_at >= played[0].at + 0.4
    assert isinstance(fed.commands[-1][1], HangUp)
    assert [c.text for _, c in fed.commands if isinstance(c, Speak)][-1] == "hello there"
    assert built.tts.calls == [("hello there", "en")] and len(built.stt.calls) == 1


def test_the_pacer_plays_a_minute_of_frames_within_100_ms_of_real_time() -> None:
    """60 s of 20 ms frames, each due at an absolute deadline on `time.perf_counter`: the last
    leaves within 100 ms (the agent's tolerance) of when it is due, and the minute takes
    within 100 ms of a minute, though asyncio's clock steps at 15.6 ms on Windows."""
    sent: list[float] = []
    frames = round(60 / FRAME_S)

    def frame(due: float) -> bytes | None:
        return b"\x00\x00" if len(sent) < frames else None

    async def send(audio: bytes) -> None:
        sent.append(time.perf_counter())

    began = time.perf_counter()
    asyncio.run(pace(frame, send))
    assert len(sent) == frames
    last_due = began + (frames - 1) * FRAME_S
    assert abs(sent[-1] - last_due) < 0.1
    assert abs((sent[-1] - sent[0]) - (frames - 1) * FRAME_S) < 0.1


def test_a_clip_at_another_rate_is_refused(settings: VoiceSettings) -> None:
    built = voice_calls(settings)
    with pytest.raises(InvalidRequestError, match="16 kHz"):
        _feed(built, AudioClip(pcm16=tone(0.2, 8_000), sample_rate=8_000))


def test_a_call_whose_greeting_never_plays_is_given_up(
    settings: VoiceSettings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The transport feeds silence for at most `GREETING_WAIT_S` waiting for the greeting, so
    a session that never greets fails the call rather than hanging the run."""
    monkeypatch.setattr(file_transport, "GREETING_WAIT_S", 0.2)
    built = voice_calls(settings)
    built.script.greet = False
    with pytest.raises(T2VoiceError, match="greeting"):
        _feed(built, AudioClip(pcm16=tone(0.2, 16_000)))
    assert built.stt.calls == []


def test_a_session_that_hangs_up_stops_the_feed(settings: VoiceSettings) -> None:
    """The session ends the call in the middle of the clip (a limit, say): the feed stops, the
    call's stream ends, and what it did is returned; its messages went nowhere."""
    built = voice_calls(settings)

    def more(event: SessionEvent) -> list[Command]:
        if isinstance(event, TurnOpened):
            return [Send(message=State(state="thinking")), HangUp(reason="max_call")]
        return []

    built.script.more = more
    fed = _feed(built, AudioClip(pcm16=tone(3.0, 16_000)), tail_s=3.0)
    assert [c.reason for _, c in fed.commands if isinstance(c, HangUp)] == ["max_call"]
    assert not any(isinstance(e, Ending) for e in fed.events)
    assert built.script.sessions[0].closed

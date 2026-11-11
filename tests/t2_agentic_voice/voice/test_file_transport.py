"""The file-fed transport (voice/file_transport.py): a call whose caller is a clip, through the
same Pipecat modules as a call over WebRTC, with the fakes' detectors and providers."""

from __future__ import annotations

import asyncio
import math
import time
from collections.abc import Callable

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


_TICK_S = 0.015625  # the step of asyncio's clock on Windows under Python 3.12 (1/64 s)


class _SteppingClock:
    """`time.perf_counter` and `asyncio.sleep` for `pace`, as Windows gives them at worst, with
    no time passing in the test: asyncio reads a clock that steps every `_TICK_S`, so a sleep
    is timed from the step before it starts and ends at the first step after that, 1 ms of
    scheduling later. A sleep ends up to a step later than asked (earlier, when the step it was
    timed from lags the clock); a pacer that slept a frame's length each time would slip about
    11 ms a frame on it, 34 s over the minute."""

    def __init__(self) -> None:
        self.now = 1_000.0

    def perf_counter(self) -> float:
        return self.now

    async def sleep(self, delay: float) -> None:
        read = math.floor(self.now / _TICK_S) * _TICK_S  # what asyncio's clock says now
        self.now = math.ceil((read + delay) / _TICK_S) * _TICK_S + 0.001


def _paced(seconds: float, perf_counter: Callable[[], float]) -> tuple[float, list[float]]:
    """`seconds` of 20 ms frames through `pace`: when it began, and when each frame left, both
    on `perf_counter`."""
    sent: list[float] = []
    frames = round(seconds / FRAME_S)

    def frame(due: float) -> bytes | None:
        return b"\x00\x00" if len(sent) < frames else None

    async def send(audio: bytes) -> None:
        sent.append(perf_counter())

    began = perf_counter()
    asyncio.run(pace(frame, send))
    assert len(sent) == frames
    return began, sent


def test_the_pacer_plays_a_minute_of_frames_within_100_ms_of_real_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """60 s of 20 ms frames, each due at an absolute deadline on `time.perf_counter`: the last
    leaves within 100 ms (the agent's tolerance) of when it is due, and the minute takes
    within 100 ms of a minute, though asyncio's clock steps at 15.6 ms on Windows. The minute
    runs on `_SteppingClock`, that clock at its worst, so it takes no real time and the bounds
    stay the minute's own; then one real second shows the pacer keeps time on the real clock,
    with the same bounds (a frame's tolerance, which does not grow with the window)."""
    clock = _SteppingClock()
    with monkeypatch.context() as patch:
        patch.setattr(file_transport, "time", clock)  # `pace` reads `time.perf_counter`
        patch.setattr(file_transport, "asyncio", clock)  # and waits with `asyncio.sleep`
        minute = _paced(60.0, clock.perf_counter)
    second = _paced(1.0, time.perf_counter)
    for seconds, (began, sent) in ((60.0, minute), (1.0, second)):
        frames = round(seconds / FRAME_S)
        last_due = began + (frames - 1) * FRAME_S
        assert abs(sent[-1] - last_due) < 0.1, seconds
        assert abs((sent[-1] - sent[0]) - (frames - 1) * FRAME_S) < 0.1, seconds


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

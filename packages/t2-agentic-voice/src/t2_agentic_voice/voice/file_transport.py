"""The file-fed transport: one call whose caller is a clip of audio instead of a browser, through
the same voice modules as a call over WebRTC (the speech detector, the turn analyzer, the speech
bridges, the session bridge and the session), its output captured, never sent. Internal, for the
tests, `poe eot` and runs T1 and T2, which reach it through testing's `turn_ends` and
`echo_timings` (plan 003's decision log); the public `AudioCall` and its parity test come later
(the design's 9.5). Each call fed gets its own speech detector and turn analyzer, built off the
event loop as voice/calls.py builds a call's, so no state passes from one clip to the next;
`calls.start` warmed the models once before (its import of onnxruntime is the slow part).

The session greets the caller once connected, and the drop rule covers any reply, the greeting
included (session/io.py): a turn whose speech began while the greeting played, or within 300 ms
after it, is not answered. So the transport feeds digital silence until the greeting's last
clause has played (its `ClausePlayed`, or its `ClauseFailed`), and only then the clip's lead:
the clip never overlaps the greeting, and a lead over the rule's 0.3 s (the registration's 1 s)
keeps its first speech from being dropped. The greeting is a fixed phrase, played from the
phrase audio `calls` was built with (voice's `PhraseAudio`), so a file-fed call sends no request
for it: the requests that synthesized it are the phrase cache's, before the first call, and they
count in run T's budget as `PhraseCache.declare` returns them (adapters/phrase_cache.py: one for
each request it packed, about n / `max_chars` for a phrase of n characters, none for a phrase its
folder held). A call whose phrase audio is silence of no length, as testing's `turn_ends` gives
its own, has played its greeting once connected, so its lead starts there.

The clip is fed at real-time pace, so Pipecat's timers run as in a call: 20 ms frames, each due
at an absolute deadline on `time.perf_counter` (the call's start plus n frames), since relative
sleeps drift and asyncio's clock steps at about 15.6 ms on Windows under Python 3.12. The spike
held 60 s within the 100 ms tolerance on one `asyncio.sleep` a frame (its end 4.9 ms early), but
sent frames up to 30 ms early and 19 ms late at the 99th percentile; a hybrid pacer was exact, at
about 43% of a core, so `pace` keeps the one sleep a frame. Smart Turn stalls audio 100 to 163 ms
at each speech stop, which the timings must allow for (plan 003's appendix, "Changes to the
plan's interfaces", item 23). The output writes each frame as long as it plays, against
deadlines of its own on `time.perf_counter`, as a WebRTC track takes it, so each clause's
`ClausePlayed` comes when it would in a call. The call builds no aiortc peer.
"""

from __future__ import annotations

import asyncio
import math
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from t2_agentic_voice.core.errors import InvalidRequestError, T2VoiceError
from t2_agentic_voice.core.events import CallId
from t2_agentic_voice.core.identity import Caller, Consent
from t2_agentic_voice.domain.declaration import Language
from t2_agentic_voice.domain.ports.speech_to_text import AudioClip
from t2_agentic_voice.voice.calls import VoiceCalls
from t2_agentic_voice.voice.session.commands import Command
from t2_agentic_voice.voice.session.session_events import (
    ClauseFailed,
    ClausePlayed,
    SessionEvent,
)

if TYPE_CHECKING:  # imported when a call is fed: importing this module imports no Pipecat
    from pipecat.transports.base_output import BaseOutputTransport

# One frame of the caller's audio: 20 ms at the speech detector's 16 kHz, mono PCM16.
FRAME_S = 0.02
RATE = 16_000
_FRAME_BYTES = round(FRAME_S * RATE) * 2
_SILENCE = bytes(_FRAME_BYTES)
# How long the transport feeds silence waiting for the greeting to play before it gives the
# call up (the agent's bound, far over any greeting).
GREETING_WAIT_S = 60.0


@dataclass(frozen=True, kw_only=True)
class FedCall:
    """What one file-fed call did: when the clip's first frame was due (`started_at`, on the
    call's clock; the greeting and the lead's silence come first), every event the Pipecat side
    handed the session, in order, and every command the session gave, in order, each with when
    it reached `Commands.run` on the call's clock (the echo's `Speak` of the heard words is the
    echo's text ready)."""

    started_at: float
    events: tuple[SessionEvent, ...]
    commands: tuple[tuple[float, Command], ...]


async def pace(
    frame: Callable[[float], bytes | None], send: Callable[[bytes], Awaitable[None]]
) -> None:
    """Send frame n, as `frame(due)` gives it once it is due, at the start plus n times
    `FRAME_S` on `time.perf_counter`, one `asyncio.sleep` a frame, until `frame` gives None."""
    start = time.perf_counter()
    n = 0
    while True:
        due = start + n * FRAME_S
        delay = due - time.perf_counter()
        if delay > 0:
            await asyncio.sleep(delay)
        audio = frame(due)
        if audio is None:
            return
        await send(audio)
        n += 1


class _Feed:
    """The caller's frames: silence until the greeting has played, then `lead_s` of silence,
    the clip and `tail_s` of silence; `started_at` is when the clip's first frame was due, on
    the call's clock (`clock_now`)."""

    def __init__(
        self, clip: AudioClip, *, lead_s: float, tail_s: float, clock_now: Callable[[], float]
    ) -> None:
        pcm = clip.pcm16 + bytes(-len(clip.pcm16) % _FRAME_BYTES)
        self._clip = [pcm[i : i + _FRAME_BYTES] for i in range(0, len(pcm), _FRAME_BYTES)]
        self._lead_s = lead_s
        self._tail = math.ceil(tail_s / FRAME_S)
        self._clock_now = clock_now
        self.greeted = False
        self.ending = False
        self.gave_up = False
        self.started_at: float | None = None
        self._first: float | None = None
        self._clip_due: float | None = None
        self._sent = 0

    def frame(self, due: float) -> bytes | None:
        now = time.perf_counter()
        first = self._first = due if self._first is None else self._first
        if self.ending:
            return None
        if self._clip_due is None:
            if not self.greeted:
                self.gave_up = due - first > GREETING_WAIT_S
                return None if self.gave_up else _SILENCE
            self._clip_due = now + self._lead_s
        if due < self._clip_due:
            return _SILENCE
        if self._sent == 0:
            self.started_at = self._clock_now() + (due - now)
        sent, self._sent = self._sent, self._sent + 1
        if sent < len(self._clip):
            return self._clip[sent]
        return _SILENCE if sent < len(self._clip) + self._tail else None


async def feed_file(
    calls: VoiceCalls,
    clip: AudioClip,
    *,
    call_id: CallId,
    caller: Caller,
    consent: Consent,
    language: Language,
    lead_s: float,
    tail_s: float,
) -> FedCall:
    """Run one call of `calls` (started: each call fed gets its own detectors), held in
    `language`, whose caller is digital silence (zeros) until the greeting has played, then
    `lead_s` of silence, then `clip` (mono PCM16 at the speech detector's 16 kHz), then `tail_s`
    of silence, fed at real-time pace. After the last frame the caller leaves (an `Ending`,
    `caller_left`); what the call did is returned once its session has hung up. Every aiortc
    peer it may build gets no ICE server (it builds none). InvalidRequestError for a clip at
    another rate; T2VoiceError when the greeting has not played within `GREETING_WAIT_S`.
    Track E's test: with a greeting that plays for a while, the clip's first frame is due after
    the greeting's last `ClausePlayed` plus `lead_s`."""
    from pipecat.frames.frames import InputAudioRawFrame

    if clip.sample_rate != RATE:
        raise InvalidRequestError("A file-fed call takes 16 kHz audio.")
    detectors = await asyncio.to_thread(calls._detectors)
    pipeline = calls._pipeline(
        call_id,
        detectors,
        caller=caller,
        consent=consent,
        language=language,
        output=file_output(),
        record=True,
    )
    feed = _Feed(clip, lead_s=lead_s, tail_s=tail_s, clock_now=pipeline.setup.clock.now)

    def watch(event: SessionEvent) -> None:
        greeting = isinstance(event, ClausePlayed | ClauseFailed) and event.reply_id == 0
        feed.greeted = feed.greeted or greeting

    pipeline.events.watch = watch
    await pipeline.start(calls._session(pipeline))
    pipeline.connect()

    async def send(audio: bytes) -> None:
        feed.ending = pipeline.ending
        frame = InputAudioRawFrame(audio=audio, sample_rate=RATE, num_channels=1)
        await pipeline.worker.queue_frame(frame)

    await pace(feed.frame, send)
    pipeline.leave("caller_left")
    await pipeline.finished.wait()
    if feed.gave_up or feed.started_at is None:
        raise T2VoiceError("The file-fed call's greeting never played.")
    given = pipeline.commands.given or []
    return FedCall(
        started_at=feed.started_at,
        events=tuple(pipeline.events.handed or ()),
        commands=tuple(given),
    )


def file_output() -> BaseOutputTransport:
    """The output of a file-fed call: Pipecat's own output transport, whose audio goes nowhere,
    each frame taking as long as it plays, against deadlines on `time.perf_counter`, and whose
    messages are dropped."""
    from pipecat.frames.frames import (
        OutputAudioRawFrame,
        OutputTransportMessageFrame,
        OutputTransportMessageUrgentFrame,
        StartFrame,
    )
    from pipecat.transports.base_output import BaseOutputTransport

    from t2_agentic_voice.voice.transport import transport_params

    class FileOutput(BaseOutputTransport):
        def __init__(self) -> None:
            super().__init__(transport_params(), name="t2v-file-output")
            self._played_to = 0.0

        async def start(self, frame: StartFrame) -> None:
            await super().start(frame)
            await self.set_transport_ready(frame)

        async def write_audio_frame(self, frame: OutputAudioRawFrame) -> bool:
            plays = len(frame.audio) / 2 / frame.num_channels / frame.sample_rate
            self._played_to = max(self._played_to, time.perf_counter()) + plays
            await asyncio.sleep(self._played_to - time.perf_counter())
            return True

        async def send_message(
            self, frame: OutputTransportMessageFrame | OutputTransportMessageUrgentFrame
        ) -> None:
            return None

    return FileOutput()

"""Fakes for the library's tests (plan 003, step 10). Each implements one protocol and nothing
else, so a test of one part runs without the parts it calls; tests/t2_agentic_voice/test_fakes.py
checks each against its protocol:

- `FakeSpeechToText` and `FakeTextToSpeech`: the ports (domain/ports/);
- `FakeClock`: a call's `Clock` (voice/session/io.py), whose time moves only when a test moves it;
- `FakePhrases`: the runtime's fixed phrases' audio (io.py's `PhraseAudio`), refusing any text
  not declared;
- `FakeCalls`: voice's entry point as api uses it (voice/calls.py's `Calls`);
- `capturing_output`: a Pipecat output transport that keeps every frame it is given and writes
  nowhere, for the end of a test's pipeline in place of SmallWebRTC's (`quiet_pipecat` first);
- the session's I/O (voice/session/io.py, with its events and commands) in session_fakes.py: the
  commands, and the Pipecat side that hands a session every event; a session in
  fake_session.py; and the slow work that answers a turn in responder_fakes.py.

This module and those import no Pipecat, as a team's testing kit runs with none
(D-017): `capturing_output` imports it when it is called.
"""

from __future__ import annotations

import asyncio
import heapq
import itertools
import time
from collections.abc import AsyncIterator, Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from t2_agentic_voice import ConfigurationError, InvalidRequestError, NotFoundError, ProviderError
from t2_agentic_voice.core.events import CallId
from t2_agentic_voice.core.identity import Caller, Consent
from t2_agentic_voice.core.settings.tts import LanguageTag
from t2_agentic_voice.domain.declaration import Language, VoiceAgent
from t2_agentic_voice.domain.fixed_phrases import fixed_phrases
from t2_agentic_voice.domain.ports.speech_to_text import AudioClip, DataFlow, Transcript
from t2_agentic_voice.domain.ports.text_to_speech import AudioChunk
from t2_agentic_voice.voice.calls import CallPhase, Candidate

if TYPE_CHECKING:
    from pipecat.frames.frames import Frame, OutputAudioRawFrame
    from pipecat.transports.base_output import BaseOutputTransport
    from pipecat.transports.base_transport import TransportParams

FAKE_FLOW = DataFlow(
    provider="Fake", processed_in="this process", stored_in="nowhere", retention="none"
)
# Two 16-bit samples, +1024 and -1024: a tone at half the sample rate, loud enough to count as
# sound above any noise floor, with no offset.
_TONE = (1024).to_bytes(2, "little", signed=True) + (-1024).to_bytes(2, "little", signed=True)
# The time of day a fake clock starts at.
WALL_START = datetime(2026, 11, 2, 9, 0, tzinfo=UTC)


def tone(seconds: float, sample_rate: int) -> bytes:
    """`seconds` of the fakes' tone as mono PCM16 at `sample_rate`, in whole samples."""
    samples = round(seconds * sample_rate)
    return (_TONE * (samples // 2 + 1))[: samples * 2]


class FakeSpeechToText:
    """A `SpeechToText` that answers from a script, one entry per call: a text (heard in the
    language asked for, billed as Groq bills, at least 10 s), a `Transcript`, or a
    `ProviderError` to raise. With the script used up, it hears nothing. It records each call,
    and waits `delay_s` first, so a test can cancel it mid-call; `closed` says whether it was
    closed."""

    name = "fake"
    data_flow = FAKE_FLOW

    def __init__(
        self, script: Sequence[str | Transcript | ProviderError] = (), *, delay_s: float = 0.0
    ) -> None:
        self.script = list(script)
        self.delay_s = delay_s
        self.calls: list[tuple[AudioClip, str | None, str | None]] = []
        self.closed = False

    async def transcribe(
        self, clip: AudioClip, *, language: str | None, prompt: str | None
    ) -> Transcript:
        self.calls.append((clip, language, prompt))
        if self.delay_s:
            await asyncio.sleep(self.delay_s)
        entry = self.script.pop(0) if self.script else ""
        if isinstance(entry, ProviderError):
            raise entry
        if isinstance(entry, Transcript):
            return entry
        return Transcript(text=entry, language=language, billed_seconds=max(10.0, clip.seconds))

    async def aclose(self) -> None:
        self.closed = True


class FakeTextToSpeech:
    """A `TextToSpeech` that says every text as the fakes' tone, `seconds_per_char` a character
    at `sample_rate`, in chunks of `chunk_s`, so every clause has audio (Pipecat marks a
    text-to-speech service that gives silence three times unusable: plan 003's appendix, item
    9). It speaks `languages`, each text up to `limit` characters (a longer one is a rejected
    `ProviderError`, as the port says); the first chunk of each take carries `remaining`
    (requests, tokens), the last `cut_short` for a text in `cut_short`, and a text in `failures`
    raises its error before any audio. It records each request and each language checked, each
    check of a language it speaks giving `sent_at` as the provider's time (None: none), waits
    `delay_s` before the first chunk, so a test can cancel it mid-take, and says whether it was
    closed."""

    name = "fake"
    data_flow = FAKE_FLOW

    def __init__(
        self,
        *,
        languages: Collection[str] = ("ar-SA", "ar", "en"),
        limit: int | None = 200,
        sample_rate: int = 24_000,
        seconds_per_char: float = 0.06,
        chunk_s: float = 0.1,
        remaining: tuple[int | None, int | None] = (None, None),
        cut_short: Collection[str] = (),
        failures: Mapping[str, ProviderError] | None = None,
        delay_s: float = 0.0,
        sent_at: datetime | None = None,
    ) -> None:
        self.languages = languages
        self.limit = limit
        self.sample_rate = sample_rate
        self.seconds_per_char = seconds_per_char
        self.chunk_s = chunk_s
        self.remaining = remaining
        self.cut_short = cut_short
        self.failures = dict(failures or {})
        self.delay_s = delay_s
        self.sent_at = sent_at
        self.calls: list[tuple[str, str]] = []
        self.checked: list[str] = []
        self.closed = False

    def max_chars(self, language: str) -> int | None:
        return self.limit

    async def synthesize(self, text: str, *, language: str) -> AsyncIterator[AudioChunk]:
        self.calls.append((text, language))
        if self.limit is not None and len(text) > self.limit:
            raise ProviderError("rejected", False)
        if text in self.failures:
            raise self.failures[text]
        if self.delay_s:
            await asyncio.sleep(self.delay_s)
        audio = tone(len(text) * self.seconds_per_char, self.sample_rate)
        step = max(2, round(self.chunk_s * self.sample_rate) * 2)
        pieces = [audio[i : i + step] for i in range(0, len(audio), step)]
        requests, tokens = self.remaining
        for index, piece in enumerate(pieces):
            first, last = index == 0, index == len(pieces) - 1
            yield AudioChunk(
                pcm16=piece,
                sample_rate=self.sample_rate,
                remaining_requests=requests if first else None,
                remaining_tokens=tokens if first else None,
                cut_short=last and text in self.cut_short,
            )

    async def check_language(self, language: str) -> datetime | None:
        self.checked.append(language)
        if language not in self.languages:
            raise ConfigurationError(
                f"The fake speaks no {language!r}. FIX: pass it in the fake's `languages`."
            )
        return self.sent_at

    async def aclose(self) -> None:
        self.closed = True


class FakePhrases:
    """The runtime's fixed phrases' audio (`PhraseAudio`): each text declared in its language,
    said as `seconds` of the fakes' tone at `sample_rate`; LookupError for any other, as the
    phrase cache refuses text not declared at the start. Every text asked for is kept, found or
    not (`asked`), so a test can tell that no heard words reached the cache."""

    def __init__(
        self,
        declared: Iterable[tuple[str, LanguageTag]] = (),
        *,
        seconds: float = 0.5,
        sample_rate: int = 24_000,
    ) -> None:
        self.declared = set(declared)
        self.seconds = seconds
        self.sample_rate = sample_rate
        self.asked: list[tuple[str, LanguageTag]] = []

    @classmethod
    def of(cls, agent: VoiceAgent) -> FakePhrases:
        """The phrases the runtime declares for `agent` (`fixed_phrases`): each language's
        greeting, echo frame and spoken notices."""
        return cls((phrase.text, phrase.language) for phrase in fixed_phrases(agent))

    def audio(self, text: str, *, language: LanguageTag) -> AudioChunk:
        self.asked.append((text, language))
        if (text, language) not in self.declared:
            raise LookupError("not a phrase declared at the start")
        return AudioChunk(pcm16=tone(self.seconds, self.sample_rate), sample_rate=self.sample_rate)


class FakeClock:
    """A call's `Clock` whose time moves only when a test moves it (`advance`): `now` starts at
    `start`, and `wall` at WALL_START plus the same seconds. A `sleep` returns once the clock has
    moved past its end; each sleep asked for is recorded."""

    def __init__(self, *, start: float = 100.0) -> None:
        self._start = self._now = start
        self._sleepers: list[tuple[float, int, asyncio.Future[None]]] = []
        self._order = itertools.count()
        self.sleeps: list[float] = []

    def now(self) -> float:
        return self._now

    def wall(self) -> datetime:
        return WALL_START + timedelta(seconds=self._now - self._start)

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        if seconds <= 0:
            await asyncio.sleep(0)
            return
        woken = asyncio.get_running_loop().create_future()
        heapq.heappush(self._sleepers, (self._now + seconds, next(self._order), woken))
        await woken

    async def advance(self, seconds: float) -> None:
        """Move the clock `seconds` on: each sleep that ends by then wakes at its own end, in
        order, and what it woke runs (a few turns of the event loop) before the next wakes; a
        sleep a woken task starts is woken too when it ends in time."""
        end = self._now + seconds
        while self._sleepers and self._sleepers[0][0] <= end:
            due, _, woken = heapq.heappop(self._sleepers)
            self._now = max(self._now, due)
            if not woken.done():
                woken.set_result(None)
            await _settle()
        self._now = end
        await _settle()


async def _settle(turns: int = 10) -> None:
    """Let the tasks a test woke run for a few turns of the event loop."""
    for _ in range(turns):
        await asyncio.sleep(0)


class FakeCalls:
    """voice's entry point as api's tests need it (voice/calls.py's `Calls`), starting no
    pipeline: it answers an offer with a text that names the call, refusing one in `refused`
    (as the F7 offer, or one it cannot read) and a call ID it already holds, and refusing any
    offer before `start`. A call is `connecting` until the test calls `connect`, and `ended`
    once ended, until the test calls `forget` (as `VoiceCalls` forgets a call once its peer has
    closed): its phase is then None, as for a call never held, and an ended call takes no
    candidates. It keeps each call's offer, caller, consent, language and candidates, the calls
    ended, and how often it was started and closed."""

    def __init__(self, *, refused: Collection[str] = ()) -> None:
        self.refused = refused
        self.offers: dict[CallId, tuple[str, Caller, Consent, Language]] = {}
        self.candidates: dict[CallId, list[Candidate]] = {}
        self.phases: dict[CallId, CallPhase] = {}
        self.ended: list[CallId] = []
        self.started = self.closed = 0

    async def start(self) -> None:
        self.started += 1

    async def answer(
        self, call_id: CallId, offer: str, *, caller: Caller, consent: Consent, language: Language
    ) -> str:
        if not self.started:
            raise RuntimeError("an offer came before start(). FIX: start the calls first.")
        if offer in self.refused or call_id in self.phases:
            raise InvalidRequestError("The offer was refused.")
        self.offers[call_id] = (offer, caller, consent, language)
        self.candidates[call_id] = []
        self.phases[call_id] = "connecting"
        return f"answer to {call_id}"

    async def add_candidates(self, call_id: CallId, candidates: Sequence[Candidate]) -> None:
        if self.phases.get(call_id, "ended") == "ended":
            raise NotFoundError("No such call.")
        if any(c.candidate and not c.candidate.startswith("candidate:") for c in candidates):
            raise InvalidRequestError("A candidate could not be read.")
        self.candidates[call_id].extend(candidates)

    def phase(self, call_id: CallId) -> CallPhase | None:
        return self.phases.get(call_id)

    def connect(self, call_id: CallId) -> None:
        """The call's ICE completed (a test's step: a real call's peer reports it)."""
        self.phases[call_id] = "connected"

    async def end(self, call_id: CallId) -> None:
        if self.phases.get(call_id, "ended") != "ended":
            self.phases[call_id] = "ended"
            self.ended.append(call_id)

    def forget(self, call_id: CallId) -> None:
        """Forget an ended call, as `VoiceCalls` does once its peer has closed (a test's step).
        Its offer stays in `offers`."""
        if self.phases.get(call_id) == "ended":
            del self.phases[call_id]

    async def aclose(self) -> None:
        for call_id in list(self.phases):
            await self.end(call_id)
        self.closed += 1


def quiet_pipecat() -> None:
    """Switch Pipecat's loguru namespace off, as voice does before it first imports Pipecat (Q2),
    so its banner and its lines with call content reach no sink: called before a test imports
    Pipecat itself."""
    from loguru import logger

    logger.disable("pipecat")


@dataclass
class Captured:
    """What a `capturing_output` transport was given: every frame that reached it going
    downstream, in order; each audio frame it wrote and each message it sent, with when it did;
    and when it had handled each interruption, its queued audio dropped (each time on
    `time.perf_counter`). No audio already in the transport's queue when an interruption is
    handled starts after it. A frame still waiting in a processor's input queue when the
    interruption reaches it is overtaken (Pipecat 1.15.0 takes a system frame first: its
    `FrameProcessorQueue`) and written in full after it, so a stop test lets its audio start
    writing before it stops."""

    frames: list[Frame] = field(default_factory=list)
    audio: list[tuple[float, OutputAudioRawFrame]] = field(default_factory=list)
    messages: list[tuple[float, object]] = field(default_factory=list)
    interruptions: list[float] = field(default_factory=list)

    def audio_s(self) -> float:
        """How long the audio written plays."""
        return sum(len(f.audio) / 2 / f.num_channels / f.sample_rate for _, f in self.audio)


def capturing_output(
    captured: Captured, *, params: TransportParams | None = None, realtime: bool = True
) -> BaseOutputTransport:
    """A Pipecat output transport for the end of a test's pipeline, in place of SmallWebRTC's:
    Pipecat's own output transport, which queues the audio in chunks and drops what is queued
    on an interruption, writing to `captured` instead of a WebRTC track, so "no audio frame of
    that turn is sent after a stop" is checked where a call checks it (plan 003's appendix, item
    7). `params` are the call's transport parameters (by default Pipecat's, audio out on, which
    write 2 s of silence after the end). Each write takes as long as its audio plays when
    `realtime`, as SmallWebRTC's waits for its track, so audio queues as in a call; otherwise at
    once. It calls `quiet_pipecat` before it imports Pipecat."""
    quiet_pipecat()
    from pipecat.frames.frames import (
        InterruptionFrame,
        OutputTransportMessageFrame,
        OutputTransportMessageUrgentFrame,
        StartFrame,
    )
    from pipecat.processors.frame_processor import FrameDirection
    from pipecat.transports.base_output import BaseOutputTransport
    from pipecat.transports.base_transport import TransportParams

    class CapturingOutput(BaseOutputTransport):
        async def start(self, frame: StartFrame) -> None:
            await super().start(frame)
            await self.set_transport_ready(frame)

        async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
            if direction == FrameDirection.DOWNSTREAM:
                captured.frames.append(frame)
            await super().process_frame(frame, direction)
            if isinstance(frame, InterruptionFrame):  # its queued audio dropped by now
                captured.interruptions.append(time.perf_counter())

        async def write_audio_frame(self, frame: OutputAudioRawFrame) -> bool:
            captured.audio.append((time.perf_counter(), frame))
            if realtime:
                await asyncio.sleep(len(frame.audio) / 2 / frame.num_channels / frame.sample_rate)
            return True

        async def send_message(
            self, frame: OutputTransportMessageFrame | OutputTransportMessageUrgentFrame
        ) -> None:
            captured.messages.append((time.perf_counter(), frame.message))

    params = params or TransportParams(audio_out_enabled=True)
    return CapturingOutput(params, name="capturing-output")

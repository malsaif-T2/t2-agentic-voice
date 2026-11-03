"""The text-to-speech bridge (voice/tts_bridge.py), with the session bridge before it and, after
it, the clause gate, the fakes' capturing output (Pipecat's own output transport, writing
nowhere) and the output tap: each clause's events as the session reads them, and a stop."""

from __future__ import annotations

import asyncio
import logging
import struct
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest
from t2_agentic_voice.core.errors import ProviderError
from t2_agentic_voice.core.events import Event
from t2_agentic_voice.core.logging import FIELDS
from t2_agentic_voice.domain.ports.text_to_speech import AudioChunk, TextToSpeech
from t2_agentic_voice.voice.pipecat_events import FailureReport
from t2_agentic_voice.voice.session.commands import Speak, StopSpeaking
from t2_agentic_voice.voice.session.io import SYSTEM_CLOCK
from t2_agentic_voice.voice.session.session_events import (
    ClauseFailed,
    ClausePlayed,
    ClauseQueued,
    Synthesizing,
)
from t2_agentic_voice.voice.session_bridge import (
    CallEvents,
    SessionBridge,
    SessionCommands,
    SpeakFrame,
)
from t2_agentic_voice.voice.transport import ClauseGate, OutputTap
from t2_agentic_voice.voice.tts_bridge import ClauseTTSBridge

from tests.t2_agentic_voice.fakes import Captured, FakeTextToSpeech, capturing_output, tone
from tests.t2_agentic_voice.voice.kit import Recorder, run_pipeline, until

if TYPE_CHECKING:
    from pipecat.processors.frame_processor import FrameProcessor

_ClauseEvent = Synthesizing | ClauseQueued | ClausePlayed | ClauseFailed

SECOND = AudioChunk(pcm16=tone(1.0, 24_000), sample_rate=24_000)
SILENT = AudioChunk(pcm16=b"", sample_rate=24_000)


def _speak(reply: int, text: str, *, clause: int = 0, audio: AudioChunk | None = None) -> Speak:
    return Speak(reply_id=reply, clause=clause, turn_id=4, text=text, language="en", audio=audio)


@dataclass
class Rig:
    """One clause path: its stream, session, commands, bridge, output and public events."""

    events: CallEvents
    session: Recorder
    commands: SessionCommands
    tts: ClauseTTSBridge
    captured: Captured
    emitted: list[Event]

    def keyed(self, kind: type[_ClauseEvent]) -> list[tuple[int, int]]:
        return [(e.reply_id, e.clause) for e in self.session.of(kind)]


def _rig(port: TextToSpeech, *, realtime: bool = False) -> tuple[Rig, list[FrameProcessor]]:
    from pipecat.transports.base_transport import TransportParams

    events, session, emitted = CallEvents(SYSTEM_CLOCK), Recorder(), list[Event]()
    report = FailureReport(call_id="call-1", emit=emitted.append, clock=SYSTEM_CLOCK)
    bridge = SessionBridge(events)
    tts = ClauseTTSBridge(tts=port, events=events, report=report, timeout_s=6.0)
    commands = SessionCommands(
        bridge, events, listen=lambda language: None, send=_nowhere, hang_up=lambda reason: None
    )
    captured = Captured()
    params = TransportParams(audio_out_enabled=True, audio_out_end_silence_secs=0)
    output = capturing_output(captured, params=params, realtime=realtime)
    processors = [bridge, tts, ClauseGate(events), output, OutputTap(events, tts.played)]
    return Rig(events, session, commands, tts, captured, emitted), processors


async def _nowhere(message: object) -> None:
    return None


def _run(port: TextToSpeech, body: Callable[[Rig], Awaitable[None]], **options: bool) -> Rig:
    rig, processors = _rig(port, **options)

    async def feed(worker: object) -> None:
        rig.events.start(rig.session)
        await body(rig)
        await rig.events.close()

    asyncio.run(run_pipeline(processors, feed))
    return rig


def test_each_clause_reports_its_request_its_first_audio_and_its_end() -> None:
    """A clause with text sends one request (`Synthesizing`), reports its first audio queued
    (`ClauseQueued`, after the request) and its end at the output (`ClausePlayed`, with the
    audio and chunks that came, the headroom on the first chunk and the take cut short); a
    cached phrase plays with no request; clauses play in the order asked for."""
    port = FakeTextToSpeech(remaining=(7, 900), cut_short={"Hello there"})

    async def body(rig: Rig) -> None:
        await rig.commands.run(_speak(0, "Hello there"))
        await rig.commands.run(_speak(1, "Welcome", audio=SECOND))
        await rig.commands.run(_speak(1, "and more", clause=1))
        await until(lambda: len(rig.session.of(ClausePlayed)) == 3)

    rig = _run(port, body)
    assert rig.keyed(ClausePlayed) == [(0, 0), (1, 0), (1, 1)]
    assert rig.keyed(Synthesizing) == [(0, 0), (1, 1)]
    assert port.calls == [("Hello there", "en"), ("and more", "en")]
    first, cached, last = rig.session.of(ClausePlayed)
    (sent, _) = rig.session.of(Synthesizing)
    queued = {(e.reply_id, e.clause): e for e in rig.session.of(ClauseQueued)}
    assert queued[0, 0].requested_at == sent.at <= queued[0, 0].at <= first.at
    assert queued[1, 0].requested_at is None
    assert (first.remaining_requests, first.remaining_tokens, first.cut_short) == (7, 900, True)
    assert first.audio_s == pytest.approx(11 * 0.06) and first.chunks == 7
    assert (cached.audio_s, cached.chunks, cached.remaining_requests) == (1.0, 1, None)
    assert not last.cut_short and rig.captured.audio_s() >= 11 * 0.06 + 1.0 + 8 * 0.06


def test_a_clause_with_no_audio_is_queued_then_played_at_its_place_and_sends_no_frame() -> None:
    """A cached phrase of no length, or a clause of spaces, reports `ClauseQueued` then
    `ClausePlayed` once the audio before it has left the output, never `ClauseFailed`, sending
    no frame and no request (voice/session/io.py's replies)."""
    port = FakeTextToSpeech()

    async def body(rig: Rig) -> None:
        await rig.commands.run(_speak(0, "Hello"))
        await rig.commands.run(_speak(1, "Welcome", audio=SILENT))
        await rig.commands.run(_speak(2, "   "))
        await until(lambda: len(rig.session.of(ClausePlayed)) == 3)

    rig = _run(port, body)
    keyed = [
        (type(e).__name__, e.reply_id)
        for e in rig.session.events
        if isinstance(e, ClauseQueued | ClausePlayed) and e.reply_id
    ]
    assert keyed == [
        ("ClauseQueued", 1),
        ("ClausePlayed", 1),
        ("ClauseQueued", 2),
        ("ClausePlayed", 2),
    ]
    assert rig.keyed(ClausePlayed) == [(0, 0), (1, 0), (2, 0)] and not rig.session.of(ClauseFailed)
    _, empty, spaces = rig.session.of(ClausePlayed)
    assert (empty.audio_s, empty.chunks, spaces.audio_s, spaces.chunks) == (0.0, 0, 0.0, 0)
    assert port.calls == [("Hello", "en")] and rig.keyed(Synthesizing) == [(0, 0)]
    assert rig.captured.audio_s() == pytest.approx(0.3, abs=0.04)  # Hello's, in 40 ms chunks


class _OddSpeech(FakeTextToSpeech):
    """The fakes' text-to-speech, with three odd takes: `half` fails after its first chunk,
    `bug` raises what no port may, and `none` answers with no audio, cut short."""

    async def synthesize(self, text: str, *, language: str) -> AsyncIterator[AudioChunk]:
        if text == "half":
            yield AudioChunk(pcm16=tone(0.2, 24_000), sample_rate=24_000)
            raise ProviderError("connection_lost", True)
        if text == "bug":
            raise ValueError("the adapter's own text")
        if text == "none":
            yield AudioChunk(pcm16=b"", sample_rate=24_000, cut_short=True)
            return
        async for chunk in super().synthesize(text, language=language):
            yield chunk


def test_a_failed_request_is_its_clauses_failure_and_a_line_naming_its_turn(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A `ProviderError` before any audio, or after some, is the clause's `ClauseFailed` with
    its kind, and no `ClausePlayed` follows; an adapter's own exception fails it as
    `server_error`, logged by its type alone; a request that gives no audio plays as a clause
    of none; each failure is a `provider_failed` line naming the turn the reply answers, and
    no public event, which the session emits from the `ClauseFailed`; the clauses after play
    on."""
    limited = ProviderError("rate_limited", True, 2.0)
    port = _OddSpeech(failures={"Busy": limited})

    async def body(rig: Rig) -> None:
        for reply, text in enumerate(["Busy", "half", "bug", "none", "after"]):
            await rig.commands.run(_speak(reply, text))
        await until(lambda: len(rig.session.of(ClausePlayed)) == 2)
        await asyncio.sleep(0.3)  # a stop frame of the half take would come by now

    rig = _run(port, body)
    failed = {e.reply_id: (e.failure, e.retryable) for e in rig.session.of(ClauseFailed)}
    assert failed == {
        0: ("rate_limited", True),
        1: ("connection_lost", True),
        2: ("server_error", False),
    }
    assert rig.keyed(ClausePlayed) == [(3, 0), (4, 0)] and (1, 0) in rig.keyed(ClauseQueued)
    none = rig.session.of(ClausePlayed)[0]
    assert (none.audio_s, none.chunks, none.cut_short) == (0.0, 0, True)
    lines = [getattr(r, FIELDS) for r in caplog.records if r.getMessage() == "provider_failed"]
    assert [(line["service"], line["kind"], line["turn_id"]) for line in lines] == [
        ("text_to_speech", "rate_limited", 4),
        ("text_to_speech", "connection_lost", 4),
        ("text_to_speech", "server_error", 4),
    ]
    assert rig.emitted == []
    assert "tts_request_failed" in caplog.text and "own text" not in caplog.text


def test_an_unusable_bridge_fails_each_clause_and_a_dropped_one_is_never_spoken() -> None:
    port = FakeTextToSpeech()

    async def body(rig: Rig) -> None:
        rig.events.dropped.add((5, 0))
        await rig.tts.queue_frame(SpeakFrame(speak=_speak(5, "Dropped")))
        await rig.tts.set_usable(False)
        await rig.commands.run(_speak(0, "Hello"))
        await until(lambda: bool(rig.session.of(ClauseFailed)))

    rig = _run(port, body)
    assert [e.failure for e in rig.session.of(ClauseFailed)] == ["server_error"]
    assert port.calls == [] and not rig.session.of(Synthesizing)


def test_outside_a_clause_the_bridge_speaks_nothing_and_names_contexts_as_pipecat_does() -> None:
    events = CallEvents(SYSTEM_CLOCK)
    report = FailureReport(call_id="call-1", emit=lambda event: None, clock=SYSTEM_CLOCK)
    tts = ClauseTTSBridge(tts=FakeTextToSpeech(), events=events, report=report, timeout_s=6.0)

    async def frames() -> list[object]:
        return [frame async for frame in tts.run_tts("text", "context")]

    assert asyncio.run(frames()) == []
    assert len(tts.create_context_id()) == 36  # Pipecat's own, a UUID
    tts.played((9, 9))  # a clause it never spoke: nothing
    assert events.handed is None


def test_a_stop_drops_every_clause_asked_for_so_far_and_no_event_of_them_follows() -> None:
    """The greeting playing, an echo whose request is in flight and a notice queued behind it:
    a `StopSpeaking` drops all three (voice/session/commands.py's `StopSpeaking`). No audio
    frame of them leaves the output after the interruption, no event of them reaches the
    session after the stop, and the next clause asked for plays."""
    port = FakeTextToSpeech(delay_s=0.4)
    marks: dict[str, float] = {}

    async def body(rig: Rig) -> None:
        await rig.commands.run(_speak(0, "Welcome", audio=SECOND))
        await rig.commands.run(_speak(1, "heard words"))
        await rig.commands.run(_speak(2, "A notice", audio=SECOND))
        await until(lambda: bool(rig.captured.audio) and bool(port.calls))
        await rig.commands.run(StopSpeaking(reply_id=2))
        marks["stopped"] = len(rig.session.events)
        await asyncio.sleep(0.5)
        marks["asked"] = time.perf_counter()
        await rig.commands.run(_speak(3, "Again", audio=SECOND))
        await until(lambda: (3, 0) in rig.keyed(ClausePlayed))

    rig = _run(port, body, realtime=True)
    dropped = {(0, 0), (1, 0), (2, 0)}
    after = rig.session.events[int(marks["stopped"]) :]
    keys = [(e.reply_id, e.clause) for e in after if isinstance(e, _ClauseEvent)]
    assert not dropped & set(keys) and (3, 0) in keys
    (interrupted,) = rig.captured.interruptions
    assert all(at < interrupted or at > marks["asked"] for at, _ in rig.captured.audio)
    assert rig.captured.audio_s() < 1.0 + 1.0 + 0.1  # the greeting cut, the next whole
    assert rig.keyed(ClausePlayed) == [(3, 0)]


def test_a_stop_before_a_clauses_first_audio_leaves_no_context_of_it() -> None:
    """TD-064's stop part: a clause whose request is in flight when a stop comes has registered
    its text-to-speech context but opened no audio context, so Pipecat's interruption leaves it;
    the bridge drops it at the stop, and the next clause plays and leaves none either."""
    port = FakeTextToSpeech(delay_s=0.5)
    held: dict[str, list[str]] = {}

    async def body(rig: Rig) -> None:
        await rig.commands.run(_speak(0, "never heard"))
        await until(lambda: bool(port.calls))
        held["in flight"] = list(rig.tts._tts_contexts)
        await rig.commands.run(StopSpeaking(reply_id=0))
        await until(lambda: not rig.tts._tts_contexts, timeout=1.0)
        await rig.commands.run(_speak(1, "Again", audio=SECOND))
        await until(lambda: (1, 0) in rig.keyed(ClausePlayed))
        held["after"] = list(rig.tts._tts_contexts)

    rig = _run(port, body)
    assert held == {"in flight": ["t2v-clause-0-0"], "after": []}
    assert rig.keyed(ClauseQueued) == [(1, 0)]  # the stopped clause's audio never came


class _Numbered(FakeTextToSpeech):
    """The fakes' text-to-speech, saying every text as `samples` numbered samples (1, 2, ...),
    streamed in pieces of `piece` samples, `gap_s` apart: every sample that leaves the output
    can be counted and placed."""

    def __init__(self, *, samples: int, piece: int, gap_s: float) -> None:
        super().__init__()
        self.samples, self.piece, self.gap_s = samples, piece, gap_s

    async def synthesize(self, text: str, *, language: str) -> AsyncIterator[AudioChunk]:
        self.calls.append((text, language))
        numbered = struct.pack(f"<{self.samples}h", *range(1, self.samples + 1))
        for start in range(0, len(numbered), self.piece * 2):
            await asyncio.sleep(self.gap_s)
            piece = numbered[start : start + self.piece * 2]
            yield AudioChunk(pcm16=piece, sample_rate=self.sample_rate)


def test_a_clause_streamed_behind_a_cached_one_leaves_the_output_whole() -> None:
    """The echo turn's two clauses: the cached frame (half a second, queued at once), then the
    heard words, streamed in pieces that are not whole output chunks (40 ms), 100 ms apart, so
    they are still coming when the frame's stop frame clears the audio the output holds short
    of a chunk (Pipecat's `_bot_stopped_speaking`). Every sample of both leaves the output, in
    order: the bridge hands the output whole chunks only."""
    port = _Numbered(samples=25_000, piece=2_500, gap_s=0.1)
    cached = AudioChunk(pcm16=struct.pack("<h", -5) * 12_000, sample_rate=24_000)

    async def body(rig: Rig) -> None:
        await rig.commands.run(_speak(0, "Welcome", audio=cached))
        await rig.commands.run(_speak(0, "heard words", clause=1))
        await until(lambda: len(rig.session.of(ClausePlayed)) == 2)

    rig = _run(port, body, realtime=True)
    sent = b"".join(frame.audio for _, frame in rig.captured.audio)
    samples = struct.unpack(f"<{len(sent) // 2}h", sent)
    assert samples.count(-5) == 12_000
    assert [s for s in samples if s > 0] == list(range(1, 25_001))
    assert max(i for i, s in enumerate(samples) if s < 0) < samples.index(1)
    played = [e.audio_s for e in rig.session.of(ClausePlayed)]
    assert played == pytest.approx([0.5, 25_000 / 24_000])


def test_audio_at_another_rate_reaches_the_output_at_its_rate_in_whole_chunks() -> None:
    """A provider's audio at 16 kHz, in pieces of 33 ms, and a cached phrase's at 48 kHz are
    resampled in the bridge to the pipeline's 24 kHz, so the output's own resampler, whose held
    audio a stop frame also discards, passes them through; every audio frame the bridge pushes
    is whole output chunks (40 ms, 1920 bytes), the take's last padded with silence."""
    from pipecat.frames.frames import TTSAudioRawFrame

    port = FakeTextToSpeech(sample_rate=16_000, chunk_s=0.033)
    cached = AudioChunk(pcm16=tone(0.25, 48_000), sample_rate=48_000)

    async def body(rig: Rig) -> None:
        await rig.commands.run(_speak(0, "Welcome", audio=cached))
        await rig.commands.run(_speak(1, "Hello there"))
        await until(lambda: len(rig.session.of(ClausePlayed)) == 2)

    rig = _run(port, body)
    frames = [f for f in rig.captured.frames if isinstance(f, TTSAudioRawFrame)]
    assert len(frames) > 2
    assert all(f.sample_rate == 24_000 and len(f.audio) % 1920 == 0 for f in frames)
    assert rig.captured.audio_s() == pytest.approx(0.25 + 11 * 0.06, abs=0.08)
    cached_played, spoken = rig.session.of(ClausePlayed)
    assert (cached_played.audio_s, spoken.audio_s) == pytest.approx((0.25, 11 * 0.06), abs=0.01)


def test_a_logger_records_no_spoken_text(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG, logger="t2_agentic_voice")

    async def body(rig: Rig) -> None:
        await rig.commands.run(_speak(0, "a private phrase"))
        await until(lambda: bool(rig.session.of(ClausePlayed)))

    _run(FakeTextToSpeech(), body)
    assert "private" not in caplog.text

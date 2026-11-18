"""The streaming text-to-speech in the call (voice/tts_stream.py, D-121) with a fake socket, in
the text-to-speech bridge's rig (test_tts_bridge.py's): the session opened as the pipeline starts
for the call's language, the talker's clauses on it in order (a reply's first a new turn), every
other clause a request; a stop cuts the clause in flight; a socket's failure falls back to
requests for the rest of the call with one line; the session closed at the call's end; and with
the setting off, or a language the provider does not stream, nothing changes (GP-18)."""

from __future__ import annotations

import asyncio
import struct
from collections.abc import AsyncIterator, Awaitable, Callable, Collection
from pathlib import Path
from typing import Any

import pytest
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.errors import ProviderError
from t2_agentic_voice.core.events import Event
from t2_agentic_voice.core.identity import Caller, Consent
from t2_agentic_voice.core.logging import FIELDS
from t2_agentic_voice.core.settings.storage import StorageSettings
from t2_agentic_voice.core.settings.tts import TtsSettings
from t2_agentic_voice.domain.action_lines import SpokenLine
from t2_agentic_voice.domain.ports.speech_stream import StreamingTextToSpeech
from t2_agentic_voice.domain.ports.text_to_speech import AudioChunk
from t2_agentic_voice.voice.pipecat_events import FailureReport
from t2_agentic_voice.voice.session.books import CallBooks
from t2_agentic_voice.voice.session.commands import Speak, StopSpeaking
from t2_agentic_voice.voice.session.io import SYSTEM_CLOCK
from t2_agentic_voice.voice.session.session_events import ClauseFailed, ClausePlayed, Synthesizing
from t2_agentic_voice.voice.session.speaker import Speaker
from t2_agentic_voice.voice.session_bridge import EventStream, SessionBridge, SessionCommands
from t2_agentic_voice.voice.transport import ClauseGate, OutputTap
from t2_agentic_voice.voice.tts_bridge import ClauseTTSBridge
from t2_agentic_voice.voice.tts_stream import CallStream, call_stream

from tests.t2_agentic_voice.adapters.tts_support import tone
from tests.t2_agentic_voice.fakes import Captured, FakeTextToSpeech, capturing_output
from tests.t2_agentic_voice.session_fakes import AGENT, FakeSessionIO
from tests.t2_agentic_voice.voice.kit import Recorder, ToneVAD, run_pipeline, until, voice_calls
from tests.t2_agentic_voice.voice.test_tts_bridge import SECOND, Rig, _nowhere

BROKEN = ProviderError("connection_lost", True, details={"provider": "fake", "error": "lost"})


class _Session:
    """One call's fake socket: each clause's text, language and new turn kept; its audio a tone
    of 0.06 s a character in 0.1 s chunks, each clause one louder than the last, so their order
    can be heard; `hold` makes a clause wait after its first chunk; `failing` maps a text to its
    failure and the chunks that come first."""

    def __init__(self, language: str) -> None:
        self.language = language
        self.said: list[tuple[str, str, bool]] = []
        self.failing: dict[str, tuple[ProviderError, int]] = {}
        self.hold: asyncio.Event | None = None
        self.cuts = self.ends = self.closed = 0

    async def say(self, text: str, *, language: str, new_turn: bool) -> AsyncIterator[AudioChunk]:
        self.said.append((text, language, new_turn))
        level = 1000 + 100 * len(self.said)
        audio = tone(len(text) * 0.06, 24_000, level=level)
        pieces = [audio[at : at + 4800] for at in range(0, len(audio), 4800)]
        failure, before = self.failing.get(text, (None, 0))
        try:
            for index, piece in enumerate(pieces):
                if failure is not None and index == before:
                    raise failure
                yield AudioChunk(pcm16=piece, sample_rate=24_000)
                if self.hold is not None:
                    await self.hold.wait()
        finally:
            self.ends += 1

    def cut(self) -> None:
        self.cuts += 1

    async def aclose(self) -> None:
        self.closed += 1


class _Streaming(FakeTextToSpeech):
    """The fakes' text-to-speech with a socket for `streamed` languages (a
    `StreamingTextToSpeech`), each call's session kept."""

    def __init__(self, *, streamed: Collection[str] = ("ar-SA", "ar", "en"), **options: Any):
        super().__init__(**options)
        self.streamed = streamed
        self.sessions: list[_Session] = []

    def streams(self, language: str) -> bool:
        return language in self.streamed

    def open_stream(self, *, language: str) -> _Session:
        self.sessions.append(_Session(language))
        return self.sessions[-1]


def _talker(reply: int, text: str, *, clause: int = 0, talker: bool = True) -> Speak:
    return Speak(reply_id=reply, clause=clause, turn_id=4, text=text, language="en", talker=talker)


def _run(port: FakeTextToSpeech, body: Callable[[Rig], Awaitable[None]], *, on: bool = True) -> Rig:
    events, session, emitted = EventStream(SYSTEM_CLOCK), Recorder(), list[Event]()
    report = FailureReport(call_id="call-1", emit=emitted.append, clock=SYSTEM_CLOCK)
    bridge = SessionBridge(events)
    stream = call_stream(port, on=on, language="en", call_id="call-1")
    tts = ClauseTTSBridge(tts=port, events=events, report=report, timeout_s=6.0, stream=stream)
    commands = SessionCommands(
        bridge,
        events,
        listen=lambda language: None,
        hear=lambda turn_id, window_ms: None,
        send=_nowhere,
        hang_up=lambda reason: None,
    )
    captured = Captured()
    from pipecat.transports.base_transport import TransportParams

    params = TransportParams(audio_out_enabled=True, audio_out_end_silence_secs=0)
    output = capturing_output(captured, params=params)
    rig = Rig(events, session, commands, tts, captured, emitted)

    async def feed(worker: object) -> None:
        events.start(session)
        await body(rig)
        await events.close()

    processors = [bridge, tts, ClauseGate(events), output, OutputTap(events, tts.played)]
    asyncio.run(run_pipeline(processors, feed))
    return rig


def _levels(captured: Captured) -> list[int]:
    """The loudness of each run of audio the output sent, in order (silence left out)."""
    sent = b"".join(frame.audio for _, frame in captured.audio)
    found: list[int] = []
    for (sample,) in struct.iter_unpack("<h", sent):
        if sample > 0 and (not found or found[-1] != sample):
            found.append(sample)
    return found


def test_the_talkers_clauses_go_on_the_socket_in_order_and_every_other_is_a_request() -> None:
    port = _Streaming()

    async def body(rig: Rig) -> None:
        await until(lambda: bool(port.sessions))  # opened as the pipeline started
        await rig.commands.run(_talker(1, "First clause,"))
        await rig.commands.run(_talker(1, "then the second.", clause=1))
        await rig.commands.run(_talker(1, "An action's line.", clause=2, talker=False))
        fixed = Speak(reply_id=1, clause=3, turn_id=4, text="Hi", language="en", audio=SECOND)
        await rig.commands.run(fixed)
        await rig.commands.run(_talker(2, "The next reply."))
        await until(lambda: len(rig.session.of(ClausePlayed)) == 5)

    rig = _run(port, body)
    (session,) = port.sessions
    assert session.language == "en"
    assert session.said == [
        ("First clause,", "en", True),
        ("then the second.", "en", False),
        ("The next reply.", "en", True),
    ]
    assert port.calls == [("An action's line.", "en")]
    assert rig.keyed(ClausePlayed) == [(1, 0), (1, 1), (1, 2), (1, 3), (2, 0)]
    assert rig.keyed(Synthesizing) == [(1, 0), (1, 1), (1, 2), (2, 0)]  # timed as requests are
    levels = [level for level in _levels(rig.captured) if level in (1100, 1200, 1300)]
    assert levels == [1100, 1200, 1300]  # each socket clause's audio whole, in its order
    assert session.closed == 1 and not rig.session.of(ClauseFailed)


def test_a_stop_mid_clause_cuts_it_on_the_socket_and_the_next_reply_plays() -> None:
    port = _Streaming()

    async def body(rig: Rig) -> None:
        await until(lambda: bool(port.sessions))
        session = port.sessions[0]
        session.hold = asyncio.Event()
        await rig.commands.run(_talker(1, "A long clause that the caller stops."))
        await until(lambda: bool(rig.captured.audio))
        await rig.commands.run(StopSpeaking(reply_id=1))
        await until(lambda: session.ends == 1)
        session.hold = None
        await rig.commands.run(_talker(2, "Yes?"))
        await until(lambda: (2, 0) in rig.keyed(ClausePlayed))

    rig = _run(port, body)
    (session,) = port.sessions
    assert session.cuts >= 1 and session.ends == 2
    assert [new_turn for _, _, new_turn in session.said] == [True, True]
    assert rig.keyed(ClausePlayed) == [(2, 0)] and port.calls == []


@pytest.mark.parametrize("before", [0, 1])
def test_a_socket_failure_falls_back_to_requests_for_the_rest_of_the_call_with_one_line(
    before: int, caplog: pytest.LogCaptureFixture
) -> None:
    """Before the clause's first audio, the clause is requested in its place; after some, it
    fails as a request that fails mid-take does. Either way the socket is closed, every later
    clause is a request, and one line says so, with no text."""
    port = _Streaming()

    async def body(rig: Rig) -> None:
        await until(lambda: bool(port.sessions))
        port.sessions[0].failing["Lost words."] = (BROKEN, before)
        await rig.commands.run(_talker(1, "Lost words."))
        await rig.commands.run(_talker(1, "And after.", clause=1))
        await rig.commands.run(_talker(2, "A later reply."))
        await until(lambda: len(rig.session.of(ClausePlayed)) == 3 - before)

    rig = _run(port, body)
    (session,) = port.sessions
    assert [text for text, _, _ in session.said] == ["Lost words."] and session.closed == 1
    asked = [("And after.", "en"), ("A later reply.", "en")]
    assert port.calls == ([("Lost words.", "en")] if before == 0 else []) + asked
    failed = [(e.reply_id, e.clause, e.failure) for e in rig.session.of(ClauseFailed)]
    assert failed == ([] if before == 0 else [(1, 0, "connection_lost")])
    lines = [getattr(r, FIELDS) for r in caplog.records if r.getMessage() == "tts_stream_fell_back"]
    assert lines == [
        {
            "call_id": "call-1",
            "provider": "fake",
            "kind": "connection_lost",
            "retryable": True,
            "error": "lost",
            "reply_id": 1,
            "clause": 0,
            "audio": before > 0,
        }
    ]
    assert "Lost words" not in caplog.text


def test_with_the_setting_off_or_no_socket_for_the_language_every_clause_is_a_request() -> None:
    """GP-18: off, the bridge has no stream and opens nothing; a provider with no socket for the
    call's language opens none either, and each clause goes as today."""
    assert TtsSettings().stream_replies is False
    assert call_stream(FakeTextToSpeech(), on=True, language="en", call_id="c") is None
    for port, on in ((_Streaming(), False), (_Streaming(streamed=("ar-SA",)), True)):

        async def body(rig: Rig) -> None:
            await rig.commands.run(_talker(1, "First clause,"))
            await rig.commands.run(_talker(1, "then the second.", clause=1))
            await until(lambda: len(rig.session.of(ClausePlayed)) == 2)

        rig = _run(port, body, on=on)
        assert port.sessions == [] and rig.keyed(ClausePlayed) == [(1, 0), (1, 1)]
        assert port.calls == [("First clause,", "en"), ("then the second.", "en")]
        assert (rig.tts._stream is None) is (not on)


def test_the_pipeline_gives_its_bridge_a_stream_only_with_the_setting(tmp_path: Path) -> None:
    port = _Streaming()
    found: dict[bool, CallStream | None] = {}
    for on in (False, True):
        storage = StorageSettings(var_dir=tmp_path / "var")
        settings = VoiceSettings(env="test", storage=storage, tts=TtsSettings(stream_replies=on))
        built = voice_calls(settings, tts=port)

        async def build(built: Any = built, on: bool = on) -> None:
            pipeline = built.calls._pipeline(
                "call-1",
                (ToneVAD(), None),
                caller=Caller(subject="made-up"),
                consent=Consent(version=None, record_audio=False),
                language=AGENT.languages[0],
                output=capturing_output(Captured()),
            )
            found[on] = pipeline.tts_bridge._stream

        asyncio.run(build())
    assert found[False] is None and isinstance(found[True], CallStream)
    assert isinstance(port, StreamingTextToSpeech)


def test_only_the_talkers_clauses_are_marked_for_the_socket(settings: VoiceSettings) -> None:
    io = FakeSessionIO(settings)

    async def end(reply: object) -> None:
        return None

    speaker = Speaker(io.setup, io.commands, CallBooks.of(io.setup), ended=end)

    async def scene() -> None:
        reply = await speaker.open_reply(io.clock.now(), turn_id=0)
        await reply.add_clause("Open Settings first.", language="en", at=io.clock.now())
        line = SpokenLine(text="Shall I send it?", spoken="Shall I send it?")
        await reply.add_line(line, language="en", at=io.clock.now())
        await speaker.say_line(line, language="en", at=io.clock.now(), turn_id=0)

    asyncio.run(scene())
    assert [speak.talker for speak in io.commands.of(Speak)] == [True, False, False]

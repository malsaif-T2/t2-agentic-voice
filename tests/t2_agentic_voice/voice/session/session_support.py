"""What the session's tests share (Track D): a `CallSession` on the fake session I/O
(tests/t2_agentic_voice/session_fakes.py), traced to memory when a test reads its spans, and the
steps a call takes, each at the fake clock's time."""

from __future__ import annotations

import dataclasses
from typing import Any

from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.events import CallReport, Event
from t2_agentic_voice.core.tracing import Tracing
from t2_agentic_voice.voice.protocol import Caption, SessionMessage
from t2_agentic_voice.voice.session.call import CallSession
from t2_agentic_voice.voice.session.commands import Speak
from t2_agentic_voice.voice.session.echo import said

from tests.t2_agentic_voice.session_fakes import FakeSessionIO

HEARD = "please check the line"  # what the caller says, in English
HEARD_AR = "ابغى اعرف حالة الطلب"  # what the caller says, in Saudi Arabic
GAP_S = 1.0  # a pause well past the drop rule's 300 ms


def call(settings: VoiceSettings, **given: Any) -> tuple[FakeSessionIO, CallSession]:
    """A session under test, attached to the fake session I/O built with `given`."""
    io = FakeSessionIO(settings, **given)
    session = CallSession(io.setup, io.commands)
    io.attach(session)
    return io, session


def traced(
    settings: VoiceSettings, **given: Any
) -> tuple[FakeSessionIO, CallSession, InMemorySpanExporter]:
    """A session whose spans go to memory, through a private provider."""
    io = FakeSessionIO(settings, **given)
    exporter = InMemorySpanExporter()
    setup = dataclasses.replace(io.setup, tracing=Tracing(exporter=exporter))
    session = CallSession(setup, io.commands)
    io.attach(session)
    return io, session, exporter


def spans(session: CallSession, exporter: InMemorySpanExporter) -> list[ReadableSpan]:
    """Every span the session exported, once its tracing has flushed."""
    session._setup.tracing.shutdown()
    return list(exporter.get_finished_spans())


async def greeted(io: FakeSessionIO) -> None:
    """The call connects and its greeting (reply 0) plays whole, then a pause past the drop
    rule's window."""
    await io.connected()
    await io.clause_queued(0, 0)
    await io.clause_played(0, 0, audio_s=0.5)
    await io.clock.advance(GAP_S)


async def turn(
    io: FakeSessionIO, turn_id: int, text: str | None, *, language: str = "en", audio_s: float = 1.0
) -> None:
    """The caller's turn: it opens and closes, its request goes, and its transcript comes."""
    await io.turn_opened(turn_id)
    await io.clock.advance(audio_s)
    await io.turn_closed(turn_id)
    await io.transcribing(turn_id, audio_s=audio_s)
    await io.transcribed(turn_id, text, language=language)


async def play(io: FakeSessionIO, reply_id: int, *, sent: bool = True) -> None:
    """Each clause the session asked for of `reply_id` plays whole, its request reported first
    when it sent one (`sent`)."""
    for speak in speaks(io, reply_id):
        if speak.audio is None and sent:
            await io.synthesizing(reply_id, speak.clause)
        await io.clause_queued(reply_id, speak.clause)
        await io.clause_played(reply_id, speak.clause, audio_s=0.4, chunks=2)


def speaks(io: FakeSessionIO, reply_id: int | None = None) -> list[Speak]:
    """The `Speak` commands given, of one reply or of all."""
    found = io.commands.of(Speak)
    return [s for s in found if reply_id is None or s.reply_id == reply_id]


def sent[M: SessionMessage](io: FakeSessionIO, kind: type[M]) -> list[M]:
    """The messages of `kind` the session sent the client."""
    return [m for m in io.commands.sent if isinstance(m, kind)]


def emitted[E: Event](io: FakeSessionIO, kind: type[E]) -> list[E]:
    """The public events of `kind` the session emitted."""
    return [e for e in io.emitted if isinstance(e, kind)]


def captions(io: FakeSessionIO, speaker: str = "agent") -> list[Caption]:
    return [c for c in sent(io, Caption) if c.speaker == speaker]


def report(io: FakeSessionIO) -> CallReport:
    """The report `CallEnded` carried."""
    from t2_agentic_voice.core.events import CallEnded

    (ended,) = emitted(io, CallEnded)
    return ended.report


def said_back(io: FakeSessionIO, text: str) -> list[str]:
    """The requests the session says `text` back in, its clauses packed up to `max_chars`, as
    captions show them (the said form), before an echo's bound on its requests."""
    setup = io.setup
    max_chars = setup.max_chars(setup.language.tag)
    return said(text, agent=setup.agent, language=setup.language, max_chars=max_chars)

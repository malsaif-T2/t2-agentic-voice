"""What observers see of each turn's language (voice/session/turn_book.py, report.py; core/
tracing.py, tracing_tts.py; plan 007's Block H): the language a turn's request named and how
(`by`) come from the turn's first `Transcribing`, whatever its part, so a talker call's held
request decides the turn and a reused held result, which hands no request of the turn's own,
is named too; speech resumed in the hold decides again. The call report's `TurnRecord.language`
is the tag of the language the turn was sent in, its code mapped to the agent's tag as
`reply_language` maps it, with `language_by`; the trace carries them on the turn's
speech-to-text span and its root span, and a share only for a classified turn. Under `session`
the report and the trace are as they were: the call's tag, `session`, and no new attribute."""

from __future__ import annotations

import asyncio
from typing import Any

from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.events import LanguageBy
from t2_agentic_voice.core.tracing import Tracing
from t2_agentic_voice.voice.session.call import CallSession
from t2_agentic_voice.voice.session.session_events import Transcribing

from tests.t2_agentic_voice.session_fakes import FakeSessionIO
from tests.t2_agentic_voice.voice.session.session_support import (
    GAP_S,
    greeted,
    play,
    report,
    spans,
    turn,
)
from tests.t2_agentic_voice.voice.session.talker_support import settle, talker_call


def _traced(settings: VoiceSettings) -> tuple[FakeSessionIO, CallSession, InMemorySpanExporter]:
    exporter = InMemorySpanExporter()
    io, session, _ = talker_call(settings, tracing=Tracing(exporter=exporter), language="ar-SA")
    return io, session, exporter


async def _sent(
    io: FakeSessionIO,
    turn_id: int,
    part: Any,
    language: str,
    by: LanguageBy,
    share: float | None = None,
) -> None:
    at = io.clock.now()
    verdict_at = None if share is None else at - 0.2
    event = Transcribing(
        turn_id=turn_id,
        at=at,
        audio_s=2.5,
        part=part,
        language=language,
        language_by=by,
        share=share,
        verdict_at=verdict_at,
    )
    await io._hand(event)


async def _own(
    io: FakeSessionIO,
    turn_id: int,
    text: str,
    language: str,
    by: LanguageBy,
    share: float | None = None,
) -> None:
    """A turn said while the agent is silent, its own request naming `language`."""
    await io.turn_opened(turn_id)
    await io.clock.advance(2.5)
    await io.turn_closed(turn_id)
    await _sent(io, turn_id, "turn", language, by, share)
    await io.transcribed(turn_id, text, language=language)
    await settle()
    await play(io, turn_id + 1)
    await io.clock.advance(GAP_S)


def _turn_spans(found: list[ReadableSpan]) -> dict[int, dict[str, Any]]:
    """Each turn's root span's attributes, with its speech-to-text span's under `stt`."""
    shown: dict[int, dict[str, Any]] = {}
    for root in [s for s in found if s.parent is None and s.name == "turn"]:
        attributes: dict[str, Any] = dict(root.attributes or {})
        children = [s for s in found if s.parent and s.parent.span_id == root.context.span_id]
        stt = [dict(s.attributes or {}) for s in children if s.name == "speech_to_text"]
        shown[int(attributes["turn.id"])] = {**attributes, "stt": stt[0] if stt else None}
    return shown


def test_the_report_and_the_trace_name_each_turns_language_and_how() -> None:
    settings = VoiceSettings(env="test")
    io, session, exporter = _traced(settings)

    async def drive() -> None:
        await greeted(io)
        await _own(io, 0, "please check my ticket", "en", "classified", 0.9)
        # a talker call's held request decides turn 1, whose own transcript reuses it
        await io.turn_opened(1)
        await io.clock.advance(1.0)
        await io.turn_held(1)
        await _sent(io, 1, "held", "en", "short")
        await io.transcribed(1, "yes", language="en", part="held")
        await io.clock.advance(0.6)
        await io.turn_closed(1)
        await io.transcribed(1, "yes", language="en")
        await settle()
        await play(io, 2)
        await io.clock.advance(GAP_S)
        await _own(io, 2, "شكرا", "ar", "unsure", 0.6)
        await io.ending()
        await io.close()

    asyncio.run(drive())
    turns = report(io).turns
    assert [(t.language, t.language_by) for t in turns] == [
        ("en", "classified"),
        ("en", "short"),
        ("ar-SA", "unsure"),
    ]
    shown = _turn_spans(spans(session, exporter))
    first, reused, unsure = shown[0], shown[1], shown[2]
    assert first["stt"]["stt.language_sent"] == "en"
    assert first["stt"]["stt.language_by"] == "classified"
    assert first["stt"]["stt.language_share"] == 0.9
    assert (first["turn.language"], first["turn.language_by"]) == ("en", "classified")
    assert reused["stt"] is None  # no request of its own, as before
    assert (reused["turn.language"], reused["turn.language_by"]) == ("en", "short")
    assert unsure["stt"]["stt.language_sent"] == "ar"
    assert unsure["stt"]["stt.language_by"] == "unsure"
    assert "stt.language_share" not in unsure["stt"]  # no score of a turn not classified


def test_speech_resumed_in_the_hold_decides_the_turn_again() -> None:
    io, _, _ = _traced(VoiceSettings(env="test"))

    async def drive() -> None:
        await greeted(io)
        await io.turn_opened(0)
        await io.clock.advance(1.0)
        await io.turn_held(0)
        await _sent(io, 0, "held", "ar", "late")
        await io.clock.advance(0.2)
        await io.hold_resumed(0)
        await io.clock.advance(1.5)
        await io.turn_held(0)
        await _sent(io, 0, "held", "en", "classified", 0.95)
        await io.transcribed(0, "my printer is broken", language="en", part="held")
        await io.clock.advance(0.6)
        await io.turn_closed(0)
        await io.transcribed(0, "my printer is broken", language="en")
        await settle()
        await io.ending()
        await io.close()

    asyncio.run(drive())
    (only,) = report(io).turns
    assert (only.language, only.language_by) == ("en", "classified")


def test_under_session_the_report_and_the_trace_are_as_they_were() -> None:
    settings = VoiceSettings(env="test")
    io, session, exporter = _traced(settings)

    async def drive() -> None:
        await greeted(io)
        await turn(io, 0, "please check my ticket", language="en")
        await settle()
        await io.ending()
        await io.close()

    asyncio.run(drive())
    (only,) = report(io).turns
    assert (only.language, only.language_by) == ("ar-SA", "session")
    shown = _turn_spans(spans(session, exporter))[0]
    assert shown["stt"]["stt.language_sent"] == "ar"
    assert not {"stt.language_by", "stt.language_share"} & set(shown["stt"])
    assert not {"turn.language", "turn.language_by"} & set(shown)

"""The session's seams for the talker (plan 006): the speaker opens a reply before its first
clause (speaker.py's `open_reply`, open_reply.py's `OpenReply`), which asks for each clause as it
comes, shows a card, and ends once closed and played; a clause added after a stop is not asked
for; an open reply needs its speaker; and the hold's signals are session events now."""

from __future__ import annotations

import asyncio
from typing import get_args

import pytest
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.domain.cards import Card
from t2_agentic_voice.voice.protocol import ShowCard
from t2_agentic_voice.voice.session.books import CallBooks
from t2_agentic_voice.voice.session.commands import Speak, StopSpeaking
from t2_agentic_voice.voice.session.open_reply import OpenReply, speech_of
from t2_agentic_voice.voice.session.playback import Reply, ReplyKind
from t2_agentic_voice.voice.session.scope import CancelScope
from t2_agentic_voice.voice.session.session_events import (
    SESSION_EVENTS,
    ClausePlayed,
    ClauseQueued,
    HoldResumed,
    TurnHeld,
)
from t2_agentic_voice.voice.session.speaker import Speaker

from tests.t2_agentic_voice.session_fakes import FakeSessionIO


def _speaker(settings: VoiceSettings) -> tuple[FakeSessionIO, Speaker, list[Reply]]:
    io = FakeSessionIO(settings)
    ended: list[Reply] = []

    async def end(reply: Reply) -> None:
        ended.append(reply)

    return io, Speaker(io.setup, io.commands, CallBooks.of(io.setup), ended=end), ended


def test_an_open_reply_asks_for_each_clause_as_it_comes_and_ends_once_closed_and_played(
    settings: VoiceSettings,
) -> None:
    io, speaker, ended = _speaker(settings)
    clock = io.clock

    async def scene() -> None:
        reply = await speaker.open_reply(clock.now(), turn_id=0)
        assert reply.scope is speaker.scope(reply.reply_id) and not reply.scope.cancelled
        await reply.add_clause("Open Settings first.", language="en", at=clock.now())
        await reply.card(Card(title="Reset a password", steps=("Open Settings.",)))
        played = ClausePlayed(reply_id=0, clause=0, at=clock.now(), audio_s=0.5, chunks=1)
        await speaker.queued(ClauseQueued(reply_id=0, clause=0, at=clock.now(), requested_at=None))
        await speaker.done(played, tell=True)
        assert ended == [] and speaker.playback.waiting  # open: thinking, not ended
        await reply.add_clause("Then press Reset.", language="en", at=clock.now())
        await reply.finish(clock.now())
        assert ended == []  # its last clause is still to play
        last = ClausePlayed(reply_id=0, clause=1, at=clock.now(), audio_s=0.5, chunks=1)
        await speaker.queued(ClauseQueued(reply_id=0, clause=1, at=clock.now(), requested_at=None))
        await speaker.done(last, tell=True)
        assert [r.reply_id for r in ended] == [0] and reply.scope.cancelled

    asyncio.run(scene())
    speaks = io.commands.of(Speak)
    assert [(s.reply_id, s.clause, s.turn_id) for s in speaks] == [(0, 0, 0), (0, 1, 0)]
    (card,) = [m for m in io.commands.sent if isinstance(m, ShowCard)]
    assert card.title == "Reset a password"
    assert "answer" in get_args(ReplyKind)


def test_a_reply_closed_with_nothing_to_play_ends_at_once_and_a_stop_asks_for_no_more(
    settings: VoiceSettings,
) -> None:
    io, speaker, ended = _speaker(settings)

    async def scene() -> None:
        empty = await speaker.open_reply(1.0, turn_id=0)
        await empty.finish(1.0)
        assert [r.reply_id for r in ended] == [0]
        stopped = await speaker.open_reply(2.0, turn_id=1)
        await stopped.add_clause("A clause.", language="en", at=2.0)
        await speaker.stop(2.1, client=True)
        await stopped.add_clause("Another clause.", language="en", at=2.2)
        await stopped.card(Card(title="Not shown"))

    asyncio.run(scene())
    assert [s.text for s in io.commands.of(Speak)] == ["A clause."]
    assert len(io.commands.of(StopSpeaking)) == 1 and not io.commands.sent


def test_an_open_reply_needs_its_speaker(settings: VoiceSettings) -> None:
    io = FakeSessionIO(settings)
    reply = OpenReply(reply_id=1, scope=CancelScope(name="reply-1", clock=io.clock))
    with pytest.raises(RuntimeError, match=r"Speaker.open_reply"):
        asyncio.run(reply.finish(1.0))


def test_a_clause_is_said_as_the_speaking_rules_say_it_and_captioned_as_written(
    settings: VoiceSettings,
) -> None:
    io = FakeSessionIO(settings, max_chars=30)
    ((said, caption),) = speech_of(io.setup, "You have 3 tickets.", "en")
    assert "three" in said and caption == "You have 3 tickets."
    parts = speech_of(io.setup, "Open Settings, then Accounts, then press Reset.", "en")
    assert len(parts) > 1 and all(len(text) <= 30 and text == cap for text, cap in parts)
    assert speech_of(io.setup, "...", "en") == []  # nothing to say: never sent


def test_the_holds_signals_are_session_events() -> None:
    held, resumed = TurnHeld(turn_id=3, at=1.5), HoldResumed(turn_id=3, at=1.8)
    assert (held.turn_id, resumed.at) == (3, 1.8)
    assert {TurnHeld, HoldResumed} <= set(SESSION_EVENTS)

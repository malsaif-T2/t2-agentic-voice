"""The session's seams for the talker (plan 006, Block 0; Track C builds them): the speaker opens
a reply before its first clause (speaker.py's `open_reply`, open_reply.py's `OpenReply`), and the
hold after Smart Turn's "complete" signals the session (session_events.py's `TurnHeld` and
`HoldResumed`, which the Pipecat side gives none of yet). Each is a stub that raises, and the
echo session is as it was: the new events are no `SessionEvent` yet, and no reply is the
talker's."""

from __future__ import annotations

import asyncio
from typing import get_args

import pytest
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.domain.cards import Card
from t2_agentic_voice.voice.session.books import CallBooks
from t2_agentic_voice.voice.session.open_reply import OpenReply
from t2_agentic_voice.voice.session.playback import Reply, ReplyKind
from t2_agentic_voice.voice.session.scope import CancelScope
from t2_agentic_voice.voice.session.session_events import (
    SESSION_EVENTS,
    HoldResumed,
    TurnHeld,
)
from t2_agentic_voice.voice.session.speaker import Speaker

from tests.t2_agentic_voice.session_fakes import FakeSessionIO


async def _ended(reply: Reply) -> None:
    """Where a reply's end would go."""


def test_a_streamed_reply_is_opened_by_the_speaker_as_a_stub(settings: VoiceSettings) -> None:
    io = FakeSessionIO(settings)
    speaker = Speaker(io.setup, io.commands, CallBooks.of(io.setup), ended=_ended)
    with pytest.raises(NotImplementedError):
        asyncio.run(speaker.open_reply(1.0, turn_id=0))
    assert io.commands.commands == []  # nothing asked for
    scope = CancelScope(name="reply-1", clock=io.clock)
    reply = OpenReply(reply_id=1, scope=scope)
    assert (reply.reply_id, reply.scope) == (1, scope)

    async def steps() -> None:
        for step in (
            reply.add_clause("Open Settings first.", language="en", at=1.0),
            reply.card(Card(title="Reset a password")),
            reply.finish(2.0),
        ):
            with pytest.raises(NotImplementedError):
                await step

    asyncio.run(steps())
    assert "answer" in get_args(ReplyKind)


def test_the_holds_signals_are_no_session_event_yet() -> None:
    held, resumed = TurnHeld(turn_id=3, at=1.5), HoldResumed(turn_id=3, at=1.8)
    assert (held.turn_id, resumed.at) == (3, 1.8)
    assert {TurnHeld, HoldResumed}.isdisjoint(SESSION_EVENTS)

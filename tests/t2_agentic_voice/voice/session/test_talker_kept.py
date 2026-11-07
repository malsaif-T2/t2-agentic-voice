"""The reply kept behind the caller's newer turn (voice/session/talking.py's kept reply; plan
006, Q19), on `TextCall`'s virtual clock, its talker the tests' scripted one
(testing/text_call_support.py). Words the caller begins while a search runs, with nothing of its
reply played, keep that reply: nothing of it plays while the turn is open (its progress line,
its card and its clauses kept, in order), and the client is shown `thinking` throughout, since a
reply asked for has no audio yet. Heard with words, the turn stops the reply, the earlier turn
`rolled_back`, and the talker answers both turns; heard as nothing (an empty transcript, or the
filter's text from silence), what was kept plays after the turn, whole and in order, and the
call returns to `listening`; a stop or pause request said whole stops it, nothing kept played.
The fake session I/O's steps are test_talker_kept_steps.py's."""

from __future__ import annotations

import asyncio
from collections.abc import Callable

import pytest
from t2_agentic_voice.agent.talker import ProgressDue, ShownCard, ToolBegan, ToolEnded
from t2_agentic_voice.core.conversation import TalkerTurn
from t2_agentic_voice.core.events import Interrupted
from t2_agentic_voice.domain.cards import Card
from t2_agentic_voice.domain.words import PRESET_WORDS
from t2_agentic_voice.evals import TextTurn
from t2_agentic_voice.voice.protocol import ShowCard, State
from t2_agentic_voice.voice.session.call import CallSession
from t2_agentic_voice.voice.session.commands import Command, Send

from tests.t2_agentic_voice.testing.text_call_support import (
    AGENT,
    ScriptedCall,
    Step,
    Work,
    answer,
)

SEARCHED = "How do I reset my password?"
# The correction, about 70 characters: 4.6 s at the text call's pace, well past the search.
CORRECTION = "no no, I meant how do I export a ticket, not reset my password, sorry"
FIRST = "Open Settings first, then choose Security from the list on the left."
SECOND = "Then press Reset and follow the link we email you."
CARD = Card(title="Reset a password", steps=("Open Settings.", "Press Reset."))
PROGRESS = AGENT.languages[0].progress["looking"]
# The states the session showed the client, each with when, on the call's clock.
States = list[tuple[float, str]]
Scene = tuple[ScriptedCall, TextTurn, TextTurn]


def _search(seconds: float) -> Callable[[TalkerTurn], list[Step]]:
    """Turn 0's reply searches for `seconds`, then gives its progress line, its card and two
    clauses; any later turn's says one clause."""

    def script(turn: TalkerTurn) -> list[Step]:
        if turn.turn_id == 0:
            return [
                ToolBegan(call_id="t-1", tool="search_help"),
                Work(seconds),
                ProgressDue(tool="search_help", key="looking", language="en"),
                ToolEnded(call_id="t-1", tool="search_help", ok=True, ms=seconds * 1000),
                ShownCard(card=CARD),
                *answer(FIRST, SECOND),
            ]
        return answer("Exporting is under Tickets.")

    return script


def _watch(call: ScriptedCall, monkeypatch: pytest.MonkeyPatch, states: States) -> None:
    """Keep each state the session shows the client from now on, with when it was shown."""
    side = call._side
    assert side is not None
    run = side.run

    async def watched(command: Command) -> None:
        if isinstance(command, Send) and isinstance(command.message, State):
            states.append((side.clock.now(), command.message.state))
        await run(command)

    monkeypatch.setattr(side, "run", watched)


def _shown_while_open(session: CallSession, turn_id: int, states: States) -> list[str]:
    """The states the client showed while the turn was open: the one shown as it opened (the
    last sent by then), then each sent after, before it closed."""
    turn = session._turns.turn(turn_id)
    opened, ended = turn.speech_at, turn.speech_ended_at
    assert opened is not None and ended is not None
    shown = [state for at, state in states if at <= opened][-1:]
    return shown + [state for at, state in states if opened < at < ended]


def _parts(call: ScriptedCall) -> tuple[CallSession, list[object]]:
    """The call's session and the messages it sent the client."""
    session, side = call._session, call._side
    assert session is not None and side is not None
    return session, list(side.sent)


def test_a_correction_that_outlasts_the_search_hears_none_of_the_reply_and_both_are_answered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The review's case: the correction is said while the search runs and goes on after it
    ends; the progress line, the card and the clauses its reply then gives are kept, never said
    over the caller; heard with words, the turn stops that reply, none of which played
    (`rolled_back`), and the talker answers both turns."""
    states: States = []

    async def scene() -> Scene:
        async with ScriptedCall(_search(1.0)) as call:
            _watch(call, monkeypatch, states)
            first = await call.user(SEARCHED)
            second = await call.user(CORRECTION, at="tool_running")
            await call.advance(10.0)
            return call, first, second

    call, first, second = asyncio.run(scene())
    session, sent = _parts(call)
    kept = session.playback.reply(1)
    assert kept is not None and kept.clauses == [] and kept.cut  # nothing of it asked or played
    assert first.fate == "rolled_back" and first.clauses == ()
    assert not [message for message in sent if isinstance(message, ShowCard)]
    assert _shown_while_open(session, 1, states) == ["thinking"]
    assert call.talker is not None
    handed = call.talker.turns[1]
    assert (handed.words, handed.cut_reply) == (CORRECTION, 1)
    assert [(t.turn_id, t.fate) for t in handed.conversation.turns] == [(0, "rolled_back")]
    second.expect.said(contains="Exporting")
    assert second.fate == "answered"
    interrupted = [(e.turn_id, e.kind) for e in call._emitted if isinstance(e, Interrupted)]
    assert interrupted == [(0, "new_words")]


@pytest.mark.parametrize(
    "nothing", [" " * 40, "Subtitles by the Amara.org community"], ids=["empty", "from_silence"]
)
def test_a_turn_heard_as_nothing_lets_the_kept_reply_play_after_it_whole_and_in_order(
    monkeypatch: pytest.MonkeyPatch, nothing: str
) -> None:
    """A turn that outlasts the search and is heard as nothing: an empty transcript, or a
    caption Whisper invents for silence, which the filter drops. The client shows `thinking`
    while it is open; then the kept reply plays, from its progress line on, whole and in order,
    its card shown, and the call returns to `listening`."""
    states: States = []

    async def scene() -> Scene:
        async with ScriptedCall(_search(1.0)) as call:
            _watch(call, monkeypatch, states)
            first = await call.user(SEARCHED)
            second = await call.user(nothing, at="tool_running")
            await call.advance(15.0)
            return call, first, second

    call, first, second = asyncio.run(scene())
    session, sent = _parts(call)
    closed = session._turns.turn(1).speech_ended_at
    kept = session.playback.reply(1)
    assert kept is not None and closed is not None
    assert [clause.caption for clause in kept.clauses] == [PROGRESS, FIRST, SECOND]
    assert all(c.queued_at is not None and c.queued_at >= closed for c in kept.clauses)
    assert first.fate == "answered" and [c.fate for c in first.clauses] == ["played"] * 3
    assert second.fate == "answered" and second.clauses == ()
    assert len([message for message in sent if isinstance(message, ShowCard)]) == 1
    assert _shown_while_open(session, 1, states) == ["thinking"]
    assert states[-1][1] == "listening"


@pytest.mark.parametrize("word", [PRESET_WORDS["en"].stop[0], PRESET_WORDS["en"].wait[0]])
def test_a_stop_said_while_the_search_runs_stops_the_reply_and_nothing_kept_plays(
    word: str,
) -> None:
    """A stop or pause word said whole, which outlasts a short search: the reply, none of which
    played, is stopped, and the turn is a command; nothing the reply kept plays, and the talker
    hears no stop."""

    async def scene() -> Scene:
        async with ScriptedCall(_search(0.2)) as call:
            first = await call.user(SEARCHED)
            second = await call.user(word, at="tool_running")
            await call.advance(10.0)
            return call, first, second

    call, first, second = asyncio.run(scene())
    session, _ = _parts(call)
    kept = session.playback.reply(1)
    assert kept is not None and kept.clauses == [] and kept.stopped
    assert first.fate == "rolled_back" and second.fate == "command"
    assert session.playback.next_id == 2  # no reply after it
    assert call.talker is not None and len(call.talker.turns) == 1
    interrupted = [(e.turn_id, e.kind) for e in call._emitted if isinstance(e, Interrupted)]
    assert interrupted == [(0, "stop")]

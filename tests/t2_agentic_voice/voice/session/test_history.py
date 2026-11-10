"""The heard history (voice/session/history.py), on its own: its records are frozen; each turn
keeps its heard words and its fate, an overlap's verdict coming before the turn's own transcript
included; each reply's clauses are played, cut with the share played, or unplayed, and the reply's
share played and heard text follow from them; the last reply the caller heard is the one a repeat
says again. The session's marks in a call are test_overlap_stop.py's."""

from __future__ import annotations

import dataclasses

import pytest
from t2_agentic_voice.core.yes_inputs import HEARD_WORDS_SEAL, HeardWords
from t2_agentic_voice.voice.session.history import (
    HeardClause,
    HeardHistory,
    HeardReply,
    HeardTurn,
)


def _heard(turn_id: int, text: str, at: float) -> HeardWords:
    values = {"turn_id": turn_id, "text": text, "language": "en", "at": at, "speech_at": at}
    return HeardWords.model_validate(values, context=HEARD_WORDS_SEAL)


WORDS = _heard(0, "made-up words", 1.0)


def test_the_records_are_frozen() -> None:
    clause = HeardClause(text="a made-up clause", fate="cut", played_fraction=0.4)
    reply = HeardReply(reply_id=1, turn_id=0, clauses=(clause,))
    turn = HeardTurn(turn_id=0, words="made-up words", fate="cut", reply_id=1)
    for record in (clause, reply, turn):
        with pytest.raises(dataclasses.FrozenInstanceError):
            setattr(record, "turn_id", 9)  # noqa: B010 - a field set on purpose
    assert HeardTurn(turn_id=2, words="", fate="dropped").reply_id is None


def test_each_turn_keeps_its_words_and_its_fate() -> None:
    history = HeardHistory()
    history.heard(WORDS)
    history.turn_ended(2, "command", reply_id=None)  # an overlap's verdict, before its words
    history.heard(_heard(2, "made-up halting words", 2.0))
    history.turn_ended(0, "answered", reply_id=1)
    history.turn_ended(1, "unfinished", reply_id=None)  # never heard
    assert history.turns() == (
        HeardTurn(turn_id=0, words="made-up words", fate="answered", reply_id=1),
        HeardTurn(turn_id=1, words="", fate="unfinished"),
        HeardTurn(turn_id=2, words="made-up halting words", fate="command"),
    )


def test_each_reply_keeps_its_clauses_as_played_cut_or_unplayed() -> None:
    history = HeardHistory()
    assert history.last_reply() is None
    history.asked(0, None, ("a made-up greeting",))
    history.played(0, 0)
    history.asked(1, 0, ("one", "two three", "four"))
    history.played(1, 0)
    history.stopped(1, playing=1, fraction=1.4)  # the estimate passed the clause's length
    history.played(1, 9)  # no such clause
    history.played(7, 0)  # no such reply
    history.asked(2, None, ("a made-up notice",))
    history.stopped(2, playing=None, fraction=0.0)  # cut before any of it played
    greeting, echo, notice = history.replies()
    assert [c.fate for c in echo.clauses] == ["played", "cut", "unplayed"]
    assert [c.played_fraction for c in echo.clauses] == [1.0, 1.0, 0.0]
    assert echo.text == "one two three" and greeting.played_fraction == 1.0
    assert not notice.heard and notice.text == "" and notice.played_fraction == 0.0
    assert history.last_reply() == echo and history.reply(1) == echo
    history.stopped(1, playing=1, fraction=-0.5)
    assert history.reply(1).played_fraction == len("one") / len("onetwo threefour")
    with pytest.raises(KeyError):
        history.reply(9)


def test_a_reply_that_says_nothing_played_whole() -> None:
    history = HeardHistory()
    history.asked(0, None, ())
    assert history.reply(0).played_fraction == 1.0 and history.turns() == ()


def test_the_lines_say_the_call_as_the_caller_heard_it_in_order() -> None:
    """What a confirmed action's job is handed (plan 007's Q7): each turn's words before the
    reply that answers it, each reply as the caller heard it; nothing of a turn heard as nothing
    or of a reply none of which played."""
    history = HeardHistory()
    history.asked(0, None, ("a made-up greeting",))
    history.played(0, 0)
    history.heard(WORDS)
    history.asked(1, 0, ("made-up answer", "never played"))
    history.played(1, 0)
    history.turn_ended(1, "dropped", reply_id=None)  # heard as nothing
    history.heard(_heard(2, "made-up second words", 3.0))
    history.asked(2, 2, ("unplayed",))
    history.heard(_heard(3, "made-up last words", 4.0))
    assert [(line.speaker, line.text) for line in history.lines()] == [
        ("agent", "a made-up greeting"),
        ("caller", "made-up words"),
        ("agent", "made-up answer"),
        ("caller", "made-up second words"),
        ("caller", "made-up last words"),
    ]
    assert "made-up words" not in repr(history.lines())

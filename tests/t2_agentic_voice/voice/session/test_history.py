"""The heard history (voice/session/history.py): its records are frozen, and the history a stub
until plan 005's Track B builds it, whose tests mark each turn's fate and each clause's."""

from __future__ import annotations

import dataclasses
from collections.abc import Callable

import pytest
from t2_agentic_voice.voice.session.heard import HeardWords
from t2_agentic_voice.voice.session.history import (
    HeardClause,
    HeardHistory,
    HeardReply,
    HeardTurn,
)

WORDS = HeardWords(turn_id=0, text="made-up words", language="en", at=1.0)


def test_the_records_are_frozen() -> None:
    clause = HeardClause(text="a made-up clause", fate="cut", played_fraction=0.4)
    reply = HeardReply(reply_id=1, turn_id=0, clauses=(clause,))
    turn = HeardTurn(turn_id=0, words="made-up words", fate="cut", reply_id=1)
    for record in (clause, reply, turn):
        with pytest.raises(dataclasses.FrozenInstanceError):
            setattr(record, "turn_id", 9)  # noqa: B010 - a field set on purpose
    assert HeardTurn(turn_id=2, words="", fate="dropped").reply_id is None


@pytest.mark.parametrize(
    "step",
    [
        lambda history: history.heard(WORDS),
        lambda history: history.turn_ended(0, "answered", reply_id=1),
        lambda history: history.asked(1, 0, ("a made-up clause",)),
        lambda history: history.played(1, 0),
        lambda history: history.stopped(1, playing=0, fraction=0.5),
        lambda history: history.turns(),
        lambda history: history.replies(),
        lambda history: history.last_reply(),
    ],
)
def test_the_history_is_a_stub_until_it_is_built(step: Callable[[HeardHistory], object]) -> None:
    with pytest.raises(NotImplementedError, match="Track B"):
        step(HeardHistory())

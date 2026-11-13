"""The call as the talker reads it (core/conversation.py; plan 006): plain frozen models
the session builds from its heard history, a clause's share of its audio agreeing with its fate,
the turn handed over holding its words, its heard language, the reply it was said over and the
one it cut."""

from __future__ import annotations

from typing import Any, get_args, get_type_hints

import pytest
from pydantic import ValidationError
from t2_agentic_voice.core.conversation import (
    ClauseFate,
    Conversation,
    PastTurn,
    SaidClause,
    SaidReply,
    TalkerTurn,
    TurnFate,
)
from t2_agentic_voice.voice.session.history import HeardClause, HeardTurn

HEARD = SaidClause(text="Open the settings.", fate="played", played_fraction=1.0)
CUT = SaidClause(text="Then press reset.", fate="cut", played_fraction=0.4)
UNPLAYED = SaidClause(text="It takes a minute.", fate="unplayed", played_fraction=0.0)


def test_a_turn_handed_to_the_talker_holds_the_call_as_heard() -> None:
    reply = SaidReply(reply_id=1, turn_id=0, clauses=(HEARD, CUT, UNPLAYED))
    so_far = Conversation(
        turns=(PastTurn(turn_id=0, words="how do I reset it", fate="cut", reply_id=1),),
        replies=(SaidReply(reply_id=0), reply),
    )
    turn = TalkerTurn(turn_id=1, words="wait, only the second step", language="en", over_reply=1)
    turn = turn.model_copy(update={"cut_reply": 1, "conversation": so_far})
    assert (turn.over_reply, turn.cut_reply, turn.conversation.replies[1].clauses[1]) == (1, 1, CUT)
    assert TalkerTurn(turn_id=2, words="hello").conversation == Conversation()
    with pytest.raises(ValidationError):
        turn.words = "other"  # type: ignore[misc]


def test_the_fates_are_the_heard_historys() -> None:
    """The session's heard history (voice/session/history.py) keeps the same closed lists."""
    clause = get_args(SaidClause.model_fields["fate"].annotation)
    turn = get_args(PastTurn.model_fields["fate"].annotation)
    assert get_args(get_type_hints(HeardClause)["fate"]) == get_args(ClauseFate) == clause
    assert get_args(get_type_hints(HeardTurn)["fate"]) == get_args(TurnFate) == turn


@pytest.mark.parametrize(
    ("model", "values"),
    [
        (SaidClause, {"text": "x", "fate": "played", "played_fraction": 0.5}),
        (SaidClause, {"text": "x", "fate": "unplayed", "played_fraction": 0.1}),
        (SaidClause, {"text": "x", "fate": "cut", "played_fraction": 1.5}),
        (SaidClause, {"text": "x", "fate": "skipped", "played_fraction": 0.0}),
        (SaidReply, {"reply_id": -1}),
        (PastTurn, {"turn_id": 0, "words": "x", "fate": "ignored"}),
        (TalkerTurn, {"turn_id": 0, "words": ""}),  # nothing heard reaches no talker
        (TalkerTurn, {"turn_id": 0, "words": "x", "language": "a"}),
        (TalkerTurn, {"turn_id": 0, "words": "x", "said": "y"}),
    ],
)
def test_a_wrong_value_is_refused(model: type[Any], values: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        model.model_validate(values)

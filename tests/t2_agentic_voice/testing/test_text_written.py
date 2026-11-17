"""`TextTurn.written` (testing/text_turn.py): the talker's clauses as the output guard passed them,
digits and all, where `clauses` holds a clause cut into several requests as said, part by part,
its numbers in words; a fixed phrase is never among them."""

from __future__ import annotations

import asyncio

from t2_agentic_voice.agent.talker import ProgressDue
from t2_agentic_voice.core.conversation import TalkerTurn
from t2_agentic_voice.evals import TextTurn

from tests.t2_agentic_voice.testing.text_call_support import ScriptedCall, Step, Work, answer

# Over the voice's 200 characters once its numbers are said: cut into two requests.
LONG = (
    "On Thursday, November 19 there are two flights to London, departing at 09:10 and 14:40, "
    "the cheapest at 09:10 costing 2190 riyals per person, and on Sunday, November 22 there "
    "are two return flights."
)
ASKED = "Which one would you like?"


def _listed(turn: TalkerTurn) -> list[Step]:
    looking = ProgressDue(tool="search_flights", key="looking", language="en")
    return [looking, Work(1.0), *answer(LONG, ASKED)]


async def _turn() -> TextTurn:
    async with ScriptedCall(_listed) as call:
        turn = await call.user("Flights to London?")
        await call.advance(30.0)
        return turn


def test_the_reply_as_written_keeps_its_digits_where_the_heard_clauses_say_them() -> None:
    turn = asyncio.run(_turn())
    assert turn.written == (LONG, ASKED)
    own = [c.text for c in turn.clauses if not c.phrase]
    assert len(own) == 3 and own[-1] == ASKED  # the long clause in two requests
    assert "2190" not in " ".join(own) and "two thousand one hundred and ninety" in own[1]
    assert [c.text for c in turn.clauses if c.phrase] == ["One moment."]

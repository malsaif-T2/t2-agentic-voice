"""A call held in text through the library's own session and talker (`TextCall` on a
`ScriptedLLM`), the search its one tool: the caller asks for London, the talker searches with
date forms, the card is shown on the page beside the reply, and the reply's fares and times,
written in digits from the result, pass the output guard, while a fare the result does not hold
is blocked. No key and no network."""

from __future__ import annotations

import asyncio

from flight_voice.tools.search import SEARCH_FLIGHTS, search_flights
from flight_voice.trip import TripBook
from pydantic import JsonValue
from t2_agentic_voice import Language, VoiceAgent
from t2_agentic_voice.evals import ScriptedLLM, TextCall, TextTurn

from tests.flight_voice.tools.tool_support import CALL_ID, CALLER, airline

DEC_17: JsonValue = {"kind": "on", "day": 17, "month": 12}
DEC_20: JsonValue = {"kind": "on", "day": 20, "month": 12}


def _agent(trips: TripBook) -> VoiceAgent:
    return VoiceAgent(
        name="flight-search-test",
        languages=[
            Language.english(
                greeting="Hi, where would you like to fly?",
                progress={"searching": "Checking the flights for you."},
            )
        ],
        instructions="You book flights.",
        tools=[search_flights(airline(), trips)],
    )


async def _searched(reply: str, trips: TripBook) -> tuple[TextTurn, tuple[str, ...]]:
    llm = ScriptedLLM(
        [
            ScriptedLLM.call_tool(
                SEARCH_FLIGHTS, destination="London", depart=DEC_17, return_date=DEC_20
            ),
            ScriptedLLM.reply(reply),
        ]
    )
    async with TextCall(_agent(trips), llm=llm, caller=CALLER, language="en") as call:
        turn = await call.user("London on the 17th of December, back on the 20th.")
        await call.advance(20.0)
        return turn, call.violations


def test_the_search_shows_its_card_and_the_reply_says_its_fares_in_digits() -> None:
    trips = TripBook()
    reply = "On Thursday the 17th there is the 09:10 at 3560 riyals and the 14:40 at 3780."
    turn, violations = asyncio.run(_searched(reply, trips))
    turn.expect.tool_call(SEARCH_FLIGHTS, destination="London")
    (card,) = turn.cards
    assert card.title == "Riyadh to London, Thu 17 Dec" and len(card.steps) == 2
    turn.expect.said(contains="3560 riyals")
    assert turn.blocked == () and violations == ()
    assert [c.outcome for c in turn.tool_calls] == ["ok"]
    # The call's own draft was written, under the call's id, not the tests' made-up one.
    assert len(trips) == 1 and trips.get(CALL_ID).destination is None


def test_a_fare_the_search_did_not_give_is_blocked() -> None:
    turn, _ = asyncio.run(_searched("The 09:10 is 2999 riyals.", TripBook()))
    assert turn.blocked != ()

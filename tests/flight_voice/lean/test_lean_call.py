"""The lean agent in a whole call held in text (the library's `TextCall` on its virtual clock, the
real session, talker, guard and tools, a fake model, no key and no network): a one-way trip to
Jeddah found, its first flight chosen, said with its total and booked on the caller's yes, the
booking check reading the call's own events (`TextCall.emitted`); a `book_trip` called before
the summary books nothing; and run F's lean play (evals/lean_call.py) of the same call, its
closing question's moment said over the reply's question, scored by its outcomes with every kept
check holding, its measures read, and a booking claimed before the store held one counted."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Sequence
from datetime import date
from typing import Any

from flight_voice.airline.bookings import Leg, priced
from flight_voice.airline.system import Airline
from flight_voice.evals import lean_call
from flight_voice.evals.lean_checks import lean_failures, lean_violations
from flight_voice.evals.scenarios import Scenario
from flight_voice.evals.score import record_of
from flight_voice.lean.agent import declare
from flight_voice.lean.booking_check import BookingCheck
from flight_voice.settings import for_the_app
from flight_voice.traveler import demo_caller
from flight_voice.trip import TripBook
from t2_agentic_voice import VoiceSettings
from t2_agentic_voice.domain.ports.chat_model import ChatRequest
from t2_agentic_voice.evals import FunctionLLM, ScriptedLLM, ScriptStep, TextCall

from tests.flight_voice.scenario_dates import TODAY

DAY = date(2026, 11, 19)
FIRST = "T2-101-2026-11-19"
ASKED = "A one-way to Jeddah on Thursday the 19th, please."
PICKED = "The first one."
AGREED = "Yes, go ahead."
TOTAL = priced((Leg(flight=101, day=DAY),), "economy", 1, TODAY)
LISTED = "There are 4 flights that day, from 06:00 to 21:00. Which one would you like?"
SUMMARY = (
    f"Riyadh to Jeddah, one way, Thursday November 19 at 06:00, economy, one traveler, "
    f"{TOTAL} riyals in all. Shall I book it?"
)


def _last_user(request: ChatRequest) -> tuple[str, list[str]]:
    """The caller's last words in `request`, and the tool results after them."""
    messages = list(request.messages)
    users = [n for n, m in enumerate(messages) if m.role == "user"]
    last = users[-1] if users else 0
    return messages[last].content, [m.content for m in messages[last:] if m.role == "tool"]


def talker(*, early: bool = False, claim: bool = False) -> FunctionLLM:
    """A fake model that finds, picks, says the trip and books on the yes; `early` calls
    book_trip before the summary, and `claim` says it is booked before it is."""

    def answer(request: ChatRequest) -> Sequence[ScriptStep]:
        words, results = _last_user(request)
        if ASKED in words:
            if not results:
                return ScriptedLLM.call_tool(
                    "find_flights", destination="Jeddah", depart="2026-11-19"
                )
            return ScriptedLLM.reply("All set, you're booked. " + LISTED if claim else LISTED)
        if PICKED in words:
            if not results:
                return ScriptedLLM.call_tool("choose_flights", outbound_id=FIRST)
            if early and len(results) == 1:
                return ScriptedLLM.call_tool("book_trip")
            return ScriptedLLM.reply(SUMMARY)
        if AGREED in words:
            if not results:
                return ScriptedLLM.call_tool("book_trip")
            return ScriptedLLM.reply("Done. Enjoy Jeddah.")
        return ScriptedLLM.reply("Okay.")

    return FunctionLLM(answer)


def _settings() -> VoiceSettings:
    return for_the_app(VoiceSettings.model_validate({"env": "test"}), agent="lean")


def _results(llm: FunctionLLM, tool: str) -> list[dict[str, Any]]:
    """Every result of `tool` the model was given, once each, in order, as data."""
    found: dict[str | None, dict[str, Any]] = {}
    for request in llm.requests:
        for message in request.messages:
            if message.role == "tool" and f'tool="{tool}"' in message.content:
                body = message.content.split(">", 1)[1].rsplit("<", 1)[0]
                found.setdefault(message.tool_call_id, json.loads(body))
    return list(found.values())


async def _called(llm: FunctionLLM) -> tuple[Airline, tuple[str, ...]]:
    airline, check = Airline(today=lambda: TODAY), BookingCheck()
    agent = declare(airline, TripBook(), check)
    async with TextCall(
        agent, llm=llm, settings=_settings(), caller=demo_caller(), today=TODAY, language="en"
    ) as call:
        check.read_from(lambda: call.emitted)
        for words in (ASKED, PICKED, AGREED):
            await call.user(words)
            await call.advance(30.0)
        return airline, call.violations


def test_a_whole_call_books_the_trip_once_the_caller_agreed() -> None:
    llm = talker()
    airline, violations = asyncio.run(_called(llm))
    assert violations == ()
    (booking,) = airline.bookings.made
    assert [(leg.flight, leg.day) for leg in booking.legs] == [(101, DAY)]
    assert booking.total_sar == TOTAL and booking.traveler_id == "T-0001"
    (booked,) = _results(llm, "book_trip")
    assert booked["status"] == "booked" and booked["reference_if_asked"] == booking.reference


def test_a_booking_before_the_summary_books_nothing_then_the_yes_books() -> None:
    llm = talker(early=True)
    airline, _ = asyncio.run(_called(llm))
    first, second = _results(llm, "book_trip")
    assert first["status"] == "not_confirmed" and "say" in first
    assert second["status"] == "booked" and len(airline.bookings.made) == 1


SCENARIO: dict[str, Any] = {
    "id": "x01_lean_seam",
    "split": "dev",
    "language": "en",
    "kind": "one_way",
    "notes": "A one-way trip, the first flight, booked by the lean agent.",
    "turns": [
        {"says": ASKED},
        {
            "says": PICKED,
            "outcome": "read_back",
            "read_back": {
                "outbound": "T2 101@2026-11-19",
                "one_way": True,
                "travelers": 1,
                "cabin": "economy",
            },
        },
        {"says": AGREED, "when": "closing_question", "outcome": "done"},
    ],
}


def _played(llm: FunctionLLM) -> lean_call.LeanRead:
    scenario = Scenario.model_validate(SCENARIO)
    return asyncio.run(lean_call.play(scenario, llm, _settings(), clock="virtual"))


def test_run_fs_lean_play_scores_the_call_by_its_outcomes() -> None:
    scenario = Scenario.model_validate(SCENARIO)
    assert lean_call.lean_turns(scenario).turns[2].when == "closing_question"  # over it
    read = _played(talker())
    assert read.failure is None and read.violations == () and read.drops == 0
    assert len(read.made) == 1 and (read.booked_turns, read.booked_index) == (3, 2)
    assert read.booked_s is not None and read.booked_s >= 0
    assert lean_failures(scenario, read) == ()
    record = record_of(scenario, 1, read, 1.0, agent="lean")
    assert record.passed and record.measures is not None
    assert record.measures.turns_to_booking == 3 and record.measures.words > 10


def test_a_booking_claimed_before_the_store_held_one_is_a_violation() -> None:
    read = _played(talker(claim=True))
    assert lean_violations(read) == ("turn 1: a booking claimed before the store held one",)
    scenario = Scenario.model_validate(SCENARIO)
    assert ("violations", None) in [(f.check, f.turn) for f in lean_failures(scenario, read)]


def test_a_reply_that_is_no_speech_is_counted() -> None:
    assert lean_call.not_speech("{...} ***")
    assert lean_call.not_speech("[waiting]")
    assert not lean_call.not_speech("There are 4 flights, from 06:00 to 21:00.")
    assert not lean_call.not_speech("فيه 4 رحلات، من 06:00 إلى 21:00.")

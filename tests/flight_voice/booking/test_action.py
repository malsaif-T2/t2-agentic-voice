"""The booking (flight_voice/booking/action.py) in a call held in text on the library's own
session, yes rule, guard and action runner (`TextCall`), the model a fake that calls `book_trip`
with no arguments, over the mock airline in each of its write modes:

- refused before any read-back, with the reason the talker reads: a caller who is no traveler
  the airline knows, a trip not planned or with a leg not chosen, a flight short of seats, a day
  passed (invariant 3, and nothing is said that was not checked);
- a yes books the trip read back for the verified traveler alone, `done` says the city and the
  day, never the reference; a refusal is said `failed` and books nothing, and the caller may try
  again; a write with no answer is looked up and said `unknown` when nothing finds it, or `done`
  when the late write is found (invariant 6);
- one booking a call: after a write whose outcome is unknown, a second is refused in code, so
  the late mode never books twice.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from typing import Any

import pytest
from flight_voice.airline.bookings import Leg
from flight_voice.airline.schedule import departures
from flight_voice.airline.system import Airline
from flight_voice.booking.action import NO_TRAVELER
from flight_voice.booking.draft import BOOK_TRIP
from flight_voice.trip import TripBook, TripDraft
from pydantic import JsonValue
from t2_agentic_voice import Caller
from t2_agentic_voice.core.settings.tts import LanguageTag
from t2_agentic_voice.domain.ports.action_jobs import OutcomeKind
from t2_agentic_voice.domain.ports.chat_model import ChatRequest
from t2_agentic_voice.evals import FunctionLLM, ScriptedLLM, ScriptStep, TextCall, TextTurn

from tests.flight_voice.booking.booking_support import (
    CALLER,
    DEC_17,
    NOBODY,
    REQUEST,
    STRANGER,
    YES,
    agent,
    airline,
    booking,
    london,
    planned,
)
from tests.flight_voice.scenario_dates import TODAY, business_sold_out

SETTLE_S = 2.0
# Long enough for a read-back to be said whole after the last line.
READ_S = 20.0


def _model(tag: LanguageTag, told: list[str]) -> FunctionLLM:
    """The fake talker: the caller's request is answered with `book_trip` called with `{}`; a
    result it reads is kept in `told`, then answered with a short neutral line."""

    def answer(request: ChatRequest) -> Sequence[ScriptStep]:
        said = [m for m in request.messages if m.role in ("user", "tool")]
        if said and said[-1].role == "tool":
            told.append(said[-1].content)
            return ScriptedLLM.reply("Okay." if tag == "en" else "طيب.")
        if said and REQUEST[tag] in said[-1].content:
            return ScriptedLLM.call_tool(BOOK_TRIP)
        return ScriptedLLM.reply("Okay." if tag == "en" else "طيب.")

    return FunctionLLM(answer)


class Played:
    """One call's turns, what the talker was told, and its checks."""

    def __init__(self) -> None:
        self.turns: list[TextTurn] = []
        self.told: list[str] = []
        self.violations: tuple[str, ...] = ()
        self.outcomes: list[str] = []


async def _play(
    flights: Airline,
    trips: TripBook,
    *lines: str,
    tag: LanguageTag = "en",
    caller: Caller = CALLER,
    advance_s: float = SETTLE_S,
) -> Played:
    played = Played()
    made = agent(flights, trips)
    call = TextCall(made, llm=_model(tag, played.told), language=tag, caller=caller)
    async with call:
        for line in lines:
            played.turns.append(await call.user(line))
            await call.advance(advance_s if line == YES[tag] else SETTLE_S)
        await call.advance(READ_S)  # the last reply said whole
        played.violations = call.violations
        jobs = call._jobs  # the job runs, each with the line its outcome said
        runs = jobs.runs if jobs is not None else []
        played.outcomes = [r.outcome.line.text for r in runs if r.outcome is not None]
    return played


def play(flights: Airline, trips: TripBook, *lines: str, **options: Any) -> Played:
    """`lines` said in turn in a call over `flights` and `trips`."""
    return asyncio.run(_play(flights, trips, *lines, **options))


@pytest.mark.parametrize(
    ("caller", "trip", "told"),
    [
        (NOBODY, london(), NO_TRAVELER),
        (STRANGER, london(), NO_TRAVELER),
        (CALLER, None, "No trip is planned yet."),
        (CALLER, london().model_copy(update={"chosen_return": None}), "The return flight is not"),
    ],
)
def test_a_trip_that_cannot_be_booked_is_refused_before_any_read_back(
    caller: Caller, trip: Any, told: str
) -> None:
    trips = planned(trip) if trip is not None else TripBook()
    flights = airline()
    done = play(flights, trips, REQUEST["en"], YES["en"], caller=caller)
    done.turns[0].expect.no_action()
    done.turns[1].expect.no_action()
    assert any(told in each for each in done.told), done.told
    assert flights.bookings.writes == [] and done.violations == ()


def test_a_flight_short_of_seats_or_a_day_passed_is_refused_with_its_reason() -> None:
    found = business_sold_out("RUH", "LHR")
    assert found is not None
    number, day = found
    full = TripDraft(
        destination="LHR",
        depart=day,
        one_way=True,
        cabin="business",
        chosen_outbound=Leg(flight=number, day=day),
    )
    seats = play(airline(), planned(full), REQUEST["en"])
    assert any("no longer has seats" in each for each in seats.told), seats.told
    later = Airline(today=lambda: DEC_17.replace(day=18), bookings=airline().bookings)
    passed = play(later, planned(), REQUEST["en"])
    assert any("day has passed" in each for each in passed.told), passed.told
    assert later.bookings.writes == []


@pytest.mark.parametrize(
    ("tag", "done"),
    [
        ("en", "Done. Your trip to London, on Thursday the seventeenth of December, is all set."),
        ("ar-SA", "تم، رحلتك للندن يوم الخميس سبعطعش ديسمبر جاهزة."),
    ],
)
def test_a_yes_books_the_trip_read_back_for_the_traveler_and_done_says_no_reference(
    tag: LanguageTag, done: str
) -> None:
    flights = airline()
    total = london().total(TODAY)
    played = play(flights, planned(), REQUEST[tag], YES[tag], tag=tag)
    asked, yes = played.turns
    asked.expect.read_back()
    yes.expect.action_completed(BOOK_TRIP)
    [made, *_] = flights.bookings.listed("T-0001")
    assert made.request_id is not None and (made.total_sar, made.travelers) == (total, 1)
    out = departures("RUH", "LHR", DEC_17)[0]
    assert made.legs[0].flight == out.flight.number and len(made.legs) == 2
    assert played.outcomes == [done] and made.reference not in done
    assert list(flights.bookings.listed("T-0002")) == []
    assert played.violations == ()


def test_a_refused_write_is_said_failed_books_nothing_and_may_be_tried_again() -> None:
    flights = airline(mode="refuse")
    played = play(flights, planned(), REQUEST["en"], YES["en"], REQUEST["en"])
    played.turns[1].expect.action_ended(BOOK_TRIP, "failed")
    assert played.outcomes == [
        "Unfortunately the booking system turned it down, so no booking was made."
    ]
    played.turns[2].expect.read_back()
    assert len(flights.bookings.writes) == 1 and flights.bookings.listed("T-0001")[0].flown
    assert played.violations == ()


@pytest.mark.parametrize(
    ("modes", "kind", "booked"),
    [
        ({"mode": "timeout"}, "unknown", 0),
        ({"mode": "timeout", "lookup": False}, "unknown", 0),
        ({"mode": "late", "lookup": False}, "unknown", 1),
        ({"mode": "late"}, "done", 1),
    ],
)
def test_a_write_with_no_answer_is_looked_up_and_never_sent_twice(
    modes: dict[str, JsonValue], kind: OutcomeKind, booked: int
) -> None:
    """The store waits past the action's timeout: what the lookup finds is said, and a second
    booking in the same call is refused in code (one a call), so a late write is never made
    twice under a new request ID."""
    flights = airline(**modes)
    timeout = booking(agent(flights, planned())).timeout_s
    played = play(
        flights,
        planned(),
        REQUEST["en"],
        YES["en"],
        REQUEST["en"],
        YES["en"],
        advance_s=timeout + SETTLE_S,
    )
    first, again = played.turns[1], played.turns[3]
    first.expect.action_ended(BOOK_TRIP, kind)
    played.turns[2].expect.no_action()
    again.expect.no_action()
    made = [b for b in flights.bookings.listed("T-0001") if not b.flown]
    assert len(made) == booked and len(flights.bookings.writes) == 1
    assert played.violations == ()

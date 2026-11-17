"""One scripted flight call played through the seam (flight_voice/evals/call.py) on the library's
own session, talker, yes rule and action runner (`TextCall` on its virtual clock), the app's
own agent over a new mock airline, the model a fake (`FunctionLLM`): no key and no network. The
caller asks for a one-way trip to Dubai tomorrow, picks the earliest, and says yes over the
closing question; the play's reads hold the tools, the read-back with the airline's total, the
booking done, and every check holds. A stop cuts a reply, a play with no booking expected
books nothing, a clause the guard blocked is read with its text, a bare yes over the summary as
the last turn books before the play ends when held (f31's shape) and ends it unbooked when not,
and a model that never answers leaves the play stuck, its turns read."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from typing import Any

from flight_voice.airline.bookings import BookingStore
from flight_voice.airline.system import Airline
from flight_voice.booking.draft import BOOK_TRIP
from flight_voice.evals.call import PlayRead, airline_for, play, read_back_values
from flight_voice.evals.checks import failures
from flight_voice.evals.scenarios import Scenario
from flight_voice.tools.choose import CHOOSE_FLIGHT
from flight_voice.tools.search import SEARCH_FLIGHTS
from t2_agentic_voice import VoiceSettings
from t2_agentic_voice.domain.ports.chat_model import ChatRequest
from t2_agentic_voice.evals import FunctionLLM, Pause, ScriptedLLM, ScriptStep

ASKED = "A one-way to Dubai tomorrow morning, please."
PICKED = "The earliest one."
LISTED = "There are three flights tomorrow, one way and per person. Which one would you like?"
ONE_WAY = {
    "id": "x01_one_way_seam",
    "split": "dev",
    "language": "en",
    "kind": "one_way",
    "notes": "A one-way trip, the earliest, booked.",
    "turns": [
        {
            "says": ASKED,
            "calls": [SEARCH_FLIGHTS],
            "args": {"destination": "DXB", "depart": "2026-11-17", "one_way": True},
            "forms": {"depart": {"kind": "relative", "when": "tomorrow"}},
            "said_any": [["per person"]],
        },
        {
            "says": PICKED,
            "calls": [CHOOSE_FLIGHT, BOOK_TRIP],
            "args": {"leg": "outbound", "pick": "earliest"},
            "outcome": "read_back",
            "read_back": {
                "outbound": "T2 201@2026-11-17",
                "one_way": True,
                "travelers": 1,
                "cabin": "economy",
            },
        },
        {"says": "Yes, book it.", "when": "closing_question", "outcome": "done"},
    ],
}


def _last_user(request: ChatRequest) -> tuple[str, int]:
    """The caller's last words in `request`, and the tool results after them."""
    messages = list(request.messages)
    users = [n for n, m in enumerate(messages) if m.role == "user"]
    if not users:
        return "", 0
    last = users[-1]
    return messages[last].content, sum(m.role == "tool" for m in messages[last:])


def _talker(request: ChatRequest) -> Sequence[ScriptStep]:
    words, tools = _last_user(request)
    if ASKED in words:
        if tools == 0:
            return ScriptedLLM.call_tool(
                SEARCH_FLIGHTS,
                destination="Dubai",
                depart={"kind": "relative", "when": "tomorrow"},
                one_way=True,
            )
        return ScriptedLLM.reply(LISTED)
    if PICKED in words and tools < 2:
        if tools == 0:
            return ScriptedLLM.call_tool(CHOOSE_FLIGHT, leg="outbound", choice={"pick": "earliest"})
        return ScriptedLLM.call_tool(BOOK_TRIP)
    return ScriptedLLM.reply("Okay.")


def _settings() -> VoiceSettings:
    return VoiceSettings.model_validate({"env": "test"})


def _played(scenario: Scenario, llm: FunctionLLM, **options: Any) -> PlayRead:
    return asyncio.run(play(scenario, llm, _settings(), clock="virtual", **options))


def _scenario(**changes: Any) -> Scenario:
    return Scenario.model_validate(ONE_WAY | changes)


def test_the_earliest_flight_is_read_back_and_booked_and_every_check_holds() -> None:
    scenario = _scenario()
    read = _played(scenario, FunctionLLM(_talker))
    assert read.failure is None and read.violations == ()
    first, second, third = read.turns
    assert first is not None and second is not None and third is not None
    assert [c.tool for c in first.tools] == [SEARCH_FLIGHTS] and first.cards == 1
    assert first.tools[0].arguments["destination"] == "Dubai" and first.blocked_texts == ()
    assert " ".join(first.written) == LISTED  # the talker's clauses as written
    assert [c.tool for c in second.tools] == [CHOOSE_FLIGHT, BOOK_TRIP]
    assert second.read_back and not second.confirmed
    assert third.confirmed and third.ended == "done"
    (booking,) = read.made
    assert [(leg.flight, leg.day.isoformat()) for leg in booking.legs] == [(201, "2026-11-17")]
    assert read.writes == 1
    assert failures(scenario, read) == ()


def test_the_read_back_values_hold_the_total_priced_from_the_airline() -> None:
    scenario = _scenario()
    turn = scenario.turns[1]
    assert turn.read_back is not None
    values = read_back_values(turn.read_back, scenario.today)
    assert values["outbound_flight"] == 201 and values["return_flight"] is None
    assert isinstance(values["total_sar"], int) and values["total_sar"] > 0


def test_each_play_gets_a_new_airline_with_the_scenarios_modes_and_today() -> None:
    scenario = _scenario(
        modes={"search": "fail", "profile": "fail", "booking": "refuse", "lookup": False},
        today="2026-12-01",
    )
    one, two = airline_for(scenario), airline_for(scenario)
    assert one is not two and one.bookings is not two.bookings
    assert isinstance(one, Airline) and isinstance(one.bookings, BookingStore)
    assert (one.search_mode, one.profile_mode) == ("fail", "fail")
    assert (one.bookings.mode, one.bookings.can_find) == ("refuse", False)
    assert one.today().isoformat() == "2026-12-01"


def _prompted(scenario: Scenario) -> str:
    """The system message of the first request a play of `scenario` sends the model."""
    systems: list[str] = []

    def talker(request: ChatRequest) -> Sequence[ScriptStep]:
        systems.extend(m.content for m in request.messages if m.role == "system")
        return ScriptedLLM.reply("Okay.")

    _played(scenario, FunctionLLM(talker))
    return systems[0]


def test_the_talkers_prompt_says_the_scenarios_today_as_the_airline_does() -> None:
    one_turn = [{"says": ASKED}]
    assert "Today is 2026-11-16." in _prompted(_scenario(turns=one_turn))
    later = _scenario(turns=one_turn, today="2026-12-01")
    assert "Today is 2026-12-01." in _prompted(later)


def test_a_stop_cuts_the_reply_and_the_turn_after_it_is_read() -> None:
    long = " ".join(["The flights to Dubai leave in the morning and at night."] * 6)

    def talker(request: ChatRequest) -> Sequence[ScriptStep]:
        words, _ = _last_user(request)
        return ScriptedLLM.reply(long if ASKED in words else "Sure.")

    scenario = _scenario(
        turns=[
            {"says": ASKED},
            {"stop": True, "at": "agent_speaking", "after_s": 1.0},
            {"says": "Sorry, one more time?", "asks_repeat": True, "repeat_of_cut": True},
        ]
    )
    read = _played(scenario, FunctionLLM(talker))
    first, stop, after = read.turns
    assert stop is None and first is not None and after is not None
    assert any(c.fate != "played" for c in first.clauses)
    assert read.made == () and read.writes == 0
    # "Sure." holds none of the cut reply's words: the cut repeat fails, nothing else.
    assert [(f.check, f.turn) for f in failures(scenario, read)] == [("cut_repeat", 3)]


def test_a_clause_the_guard_blocked_is_read_with_its_text() -> None:
    claimed = "Your booking reference is 482913."

    def talker(request: ChatRequest) -> Sequence[ScriptStep]:
        return ScriptedLLM.reply(f"Sure. {claimed}")

    read = _played(_scenario(turns=[{"says": "What's my booking reference?"}]), FunctionLLM(talker))
    (turn,) = read.turns
    assert turn is not None and turn.blocked == 1 and turn.blocked_texts == (claimed,)
    assert all("482913" not in c.text for c in turn.heard)


def _yes_over_the_summary(*, held: bool) -> tuple[Scenario, PlayRead]:
    """f31's shape: a bare yes said over the summary, 2 s in, as the last turn, with
    `interruptions.yes_over_read_back` on when `held`."""
    last = {"says": "Yes.", "when": "read_back", "after_s": 2.0, "outcome": "done"}
    scenario = _scenario(turns=[*ONE_WAY["turns"][:2], last])
    settings = VoiceSettings.model_validate(
        {"env": "test", "interruptions": {"yes_over_read_back": held}}
    )
    llm = FunctionLLM(_talker)
    return scenario, asyncio.run(play(scenario, llm, settings, clock="virtual"))


def test_a_yes_held_over_the_summary_as_the_last_turn_books_before_the_play_ends() -> None:
    scenario, read = _yes_over_the_summary(held=True)
    third = read.turns[2]
    assert read.failure is None and third is not None
    assert third.confirmed and third.ended == "done"
    assert read.writes == 1 and len(read.made) == 1
    assert failures(scenario, read) == ()


def test_a_yes_over_the_summary_with_none_held_ends_the_play_unbooked_not_stuck() -> None:
    scenario, read = _yes_over_the_summary(held=False)
    third = read.turns[2]
    assert read.failure is None and third is not None and not third.confirmed
    assert read.writes == 0 and read.made == ()
    assert [f.check for f in failures(scenario, read) if f.turn == 3] != []


def test_a_model_that_never_answers_leaves_the_play_stuck_with_its_turns_read() -> None:
    def silent(request: ChatRequest) -> Sequence[ScriptStep]:
        return [Pause(seconds=3600.0)]

    read = _played(_scenario(), FunctionLLM(silent), whole_s=5.0)
    assert read.failure == "stuck"
    assert next(f.check for f in failures(_scenario(), read)) == "failure"

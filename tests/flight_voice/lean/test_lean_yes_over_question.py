"""A yes said over the lean agent's closing question books once its reply ends (D-116:
`interruptions.answer_yes_over_question`, which the lean agent's settings path turns on, with
the booking's send words), in a whole call held in text (the library's `TextCall` on its
virtual clock, the real session, talker, guard, tools and booking check, a fake model): a bare
yes in English and in Saudi Arabic, and «إي احجزها» / «نعم، احجزها», said once the summary with
its total has played (run F's lean moment, lean_call.py's `to_question`), no model request made
until the reply has ended. Never (adversarial): a yes said over the summary before its total, a
filler alone over the question, or a yes the caller takes back with a no over the question, is
answered or books; with the setting off the yes is lost, as before (characterization). Run F's
lean play says a scenario's closing-question turn over the question, so a bare yes books there,
in both languages, and after the reply when its total and question share its last clause."""

from __future__ import annotations

import asyncio
import dataclasses
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any

import pytest
from flight_voice.airline.bookings import Leg, priced
from flight_voice.airline.system import Airline
from flight_voice.evals import lean_call
from flight_voice.evals.lean_checks import lean_failures
from flight_voice.evals.scenarios import Scenario
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
TOTAL = priced((Leg(flight=101, day=DAY),), "economy", 1, TODAY)


@dataclass(frozen=True)
class Lines:
    """One language's call: what the caller asks and picks, the agent's list, its summary with
    the total and its closing question, and the caller's bare yes."""

    language: str
    asked: str
    picked: str
    listed: str
    summary: str
    question: str
    yes: str


ENGLISH = Lines(
    language="en",
    asked="A one-way to Jeddah on Thursday the 19th, please.",
    picked="The first one.",
    listed="There are 4 flights that day, from 06:00 to 21:00. Which one would you like?",
    summary=(
        f"Riyadh to Jeddah, one way, Thursday November 19 at 06:00, economy, one traveler, "
        f"{TOTAL} riyals in all."
    ),
    question="Shall I book it?",
    yes="Yes.",
)
SAUDI = Lines(
    language="ar-SA",
    asked="أبي رحلة لجدة يوم الخميس تسعطعش، رايح بس",
    picked="الأولى",
    listed="فيه 4 رحلات ذاك اليوم، من 06:00 إلى 21:00. أي وحدة تبي؟",
    summary=(
        f"من الرياض إلى جدة، رايح بس، الخميس 19 نوفمبر الساعة 06:00، سياحي، مسافر واحد، "
        f"{TOTAL} ريال."
    ),
    question="أحجزها لك؟",
    yes="إيه",  # eeh, yes (Saudi): alef with hamza below, yeh, heh
)


def talker(lines: Lines) -> FunctionLLM:
    """A fake model that finds, picks, says the trip with its total and its closing question,
    and books on any later words."""

    def answer(request: ChatRequest) -> Sequence[ScriptStep]:
        messages = list(request.messages)
        users = [n for n, m in enumerate(messages) if m.role == "user"]
        last = users[-1] if users else 0
        words = messages[last].content
        results = [m.content for m in messages[last:] if m.role == "tool"]
        if lines.asked in words:
            if not results:
                return ScriptedLLM.call_tool(
                    "find_flights", destination="Jeddah", depart="2026-11-19"
                )
            return ScriptedLLM.reply(lines.listed)
        if lines.picked in words:
            if not results:
                return ScriptedLLM.call_tool("choose_flights", outbound_id=FIRST)
            return ScriptedLLM.reply(f"{lines.summary} {lines.question}")
        if not results:
            return ScriptedLLM.call_tool("book_trip")
        return ScriptedLLM.reply("Done.")

    return FunctionLLM(answer)


def _settings(**interruptions: Any) -> VoiceSettings:
    voice = VoiceSettings.model_validate({"env": "test", "interruptions": interruptions})
    return for_the_app(voice, agent="lean")


@dataclass(frozen=True)
class Played:
    """What the call did: the bookings made, the model's requests made while the question
    played (after the words were said, before the reply ended) and after, and the words' fate."""

    booked: int
    while_playing: int
    after: int
    fate: str


async def _call(lines: Lines, words: str, *, over: str, settings: VoiceSettings) -> Played:
    """One call in `lines`' language whose caller says `words` over the summary reply's
    question (`over="question"`) or its first clause (`over="summary"`)."""
    llm = talker(lines)
    airline, check = Airline(today=lambda: TODAY), BookingCheck()
    agent = declare(airline, TripBook(), check)
    async with TextCall(
        agent,
        llm=llm,
        settings=settings,
        caller=demo_caller(),
        today=TODAY,
        language="en" if lines.language == "en" else "ar-SA",
    ) as call:
        check.read_from(lambda: call.emitted)
        await call.user(lines.asked)
        await call.advance(30.0)
        summary = await call.user(lines.picked)
        if over == "question":
            assert await lean_call.to_question(call, summary), "the question never played"
        before = len(llm.requests)
        said = await call.user(words, during="agent_speaking")
        while_playing = len(llm.requests) - before
        await lean_call.to_end(call, summary)
        await call.advance(30.0)
        after = len(llm.requests) - before - while_playing
        return Played(len(airline.bookings.made), while_playing, after, said.fate)


@pytest.mark.parametrize("lines", [ENGLISH, SAUDI], ids=["en", "ar-SA"])
def test_a_bare_yes_over_the_closing_question_books_once_the_reply_ends(lines: Lines) -> None:
    played = asyncio.run(_call(lines, lines.yes, over="question", settings=_settings()))
    assert played.while_playing == 0  # held: nothing asked while the question plays
    assert played.after == 2  # then answered: book_trip, and the reply to its result
    assert played.booked == 1


@pytest.mark.parametrize("words", ["إي احجزها", "نعم، احجزها"], ids=["saudi", "msa-yes"])
def test_a_yes_with_the_bookings_send_word_over_the_closing_question_books(words: str) -> None:
    played = asyncio.run(_call(SAUDI, words, over="question", settings=_settings()))
    assert (played.booked, played.fate) == (1, "answered")  # the rule may ask a model first


async def _yes_then(lines: Lines, no: str) -> tuple[int, str, str]:
    """A call whose caller says the bare yes over the summary reply's question, then `no` over
    it too: the bookings made, and each turn's fate."""
    llm = talker(lines)
    airline, check = Airline(today=lambda: TODAY), BookingCheck()
    agent = declare(airline, TripBook(), check)
    async with TextCall(
        agent,
        llm=llm,
        settings=_settings(),
        caller=demo_caller(),
        today=TODAY,
        language="en" if lines.language == "en" else "ar-SA",
    ) as call:
        check.read_from(lambda: call.emitted)
        await call.user(lines.asked)
        await call.advance(30.0)
        summary = await call.user(lines.picked)
        assert await lean_call.to_question(call, summary), "the question never played"
        yes = await call.user(lines.yes, during="agent_speaking")
        taken_back = await call.user(no, during="agent_speaking")
        await lean_call.to_end(call, summary)
        await call.advance(30.0)
        return len(airline.bookings.made), yes.fate, taken_back.fate


@pytest.mark.parametrize(("lines", "no"), [(ENGLISH, "No."), (SAUDI, "لا")], ids=["en", "ar-SA"])
def test_a_yes_taken_back_by_a_no_over_the_closing_question_never_books(
    lines: Lines, no: str
) -> None:
    assert asyncio.run(_yes_then(lines, no)) == (0, "went_on", "went_on")


@pytest.mark.parametrize("lines", [ENGLISH, SAUDI], ids=["en", "ar-SA"])
def test_a_yes_over_the_summary_before_its_total_never_books(lines: Lines) -> None:
    played = asyncio.run(_call(lines, lines.yes, over="summary", settings=_settings()))
    assert (played.booked, played.while_playing, played.after) == (0, 0, 0)
    assert played.fate == "went_on"


@pytest.mark.parametrize(
    ("lines", "filler"), [(ENGLISH, "Okay."), (SAUDI, "تمام")], ids=["en", "ar-SA"]
)
def test_a_filler_alone_over_the_closing_question_is_not_answered(
    lines: Lines, filler: str
) -> None:
    played = asyncio.run(_call(lines, filler, over="question", settings=_settings()))
    assert (played.booked, played.while_playing, played.after) == (0, 0, 0)
    assert played.fate == "went_on"


def test_with_the_setting_off_the_yes_over_the_question_is_lost_as_before() -> None:
    off = _settings(answer_yes_over_question=False)
    assert not off.interruptions.answer_yes_over_question
    played = asyncio.run(_call(ENGLISH, ENGLISH.yes, over="question", settings=off))
    assert (played.booked, played.while_playing, played.after) == (0, 0, 0)
    assert played.fate == "went_on"


def _scenario(lines: Lines) -> Scenario:
    return Scenario.model_validate(
        {
            "id": "x03_lean_yes_over_question",
            "split": "dev",
            "language": lines.language,
            "kind": "confirmation",
            "notes": "A bare yes over the lean agent's closing question books the trip.",
            "turns": [
                {"says": lines.asked},
                {
                    "says": lines.picked,
                    "outcome": "read_back",
                    "read_back": {
                        "outbound": "T2 101@2026-11-19",
                        "one_way": True,
                        "travelers": 1,
                        "cabin": "economy",
                    },
                },
                {"says": lines.yes, "when": "closing_question", "outcome": "done"},
            ],
        }
    )


@pytest.mark.parametrize("lines", [ENGLISH, SAUDI], ids=["en", "ar-SA"])
def test_run_fs_lean_play_says_a_closing_question_turn_over_the_question(lines: Lines) -> None:
    scenario = _scenario(lines)
    assert lean_call.lean_turns(scenario).turns[2].when == "closing_question"
    play = lean_call.play(scenario, talker(lines), _settings(), clock="virtual")
    read = asyncio.run(play)
    assert read.failure is None and read.violations == ()
    assert len(read.made) == 1 and (read.booked_turns, read.booked_index) == (3, 2)
    final = read.turns[2]
    assert final is not None and final.fate == "answered"
    if lines is ENGLISH:
        assert lean_failures(scenario, read) == ()


@pytest.mark.parametrize("words", ["Yes.", "Yes, book it."], ids=["bare", "with-send"])
def test_run_fs_lean_play_says_a_turn_after_a_question_that_holds_the_total(words: str) -> None:
    one = dataclasses.replace(  # the total and the question in one clause, the reply's last
        ENGLISH,
        summary=f"Jeddah, Thursday 06:00, economy, {TOTAL} riyals,",
        question="shall I book it?",
        yes=words,
    )
    read = asyncio.run(lean_call.play(_scenario(one), talker(one), _settings(), clock="virtual"))
    assert read.failure is None and len(read.made) == 1  # said once the reply had ended
    assert [len(t.clauses) for t in read.turns[1:2] if t is not None] == [1]

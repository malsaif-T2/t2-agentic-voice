"""The lean agent never says a trip is booked before `book_trip` booked it (lean/book.py's
"No claim before the booking"; the owner's call of 2026-11-18, where «تم حجز رحلتك …» followed a
`not_confirmed`): a whole Saudi call held in text (the library's `TextCall`, the real session,
talker, guard and tools, a fake model), whose model calls `book_trip` before the summary and then
claims the booking, in the booking's own words or a model's rewording of them («تم حجزها لك»,
«حجزتها»). The claim is never heard, nor the error notice in its place; the model is asked once
more, says the trip with its total, and the caller's yes books it, after which the claim is
said. And the guard on the lean agent's tools alone: each rewording is held with no booking made
and said after one; one negated, or the flight sold out, is said; and the library's default
phrases are not read, so an honest "nothing has been booked yet" is said. Every sentence is
written for the test."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from datetime import date

import pytest
from flight_voice.airline.bookings import Leg, priced
from flight_voice.airline.system import Airline
from flight_voice.evals.spoken import failure_notices, form
from flight_voice.lean.agent import declare
from flight_voice.lean.book import REWORDED
from flight_voice.lean.booking_check import BookingCheck
from flight_voice.settings import for_the_app
from flight_voice.traveler import demo_caller
from t2_agentic_voice import Tool, VoiceSettings
from t2_agentic_voice.agent.clause_gate import CLAIM_HELD
from t2_agentic_voice.agent.speech_guard import SpeechGuard, claimants
from t2_agentic_voice.agent.tool_calls import Memory
from t2_agentic_voice.domain.ports.chat_model import ChatRequest
from t2_agentic_voice.evals import FunctionLLM, ScriptedLLM, ScriptStep, TextCall

from tests.flight_voice.lean.lean_support import lean_deps
from tests.flight_voice.scenario_dates import TODAY

DAY = date(2026, 11, 19)
FIRST = "T2101-2026-11-19"
TOTAL = priced((Leg(flight=101, day=DAY),), "economy", 1, TODAY)
ASKED = "أبي رحلة لجدة يوم الخميس تسعطعش، رايح بس"
PICKED = "الأولى"
AGREED = "إي نعم"
LISTED = "فيه أربع رحلات ذاك اليوم، أولها 06:00 وآخرها 21:00. أي وحدة تبي؟"
# The claim the model makes after book_trip answered not_confirmed: the booking's own words, and
# two rewordings of them, the verb with "it" on it.
CLAIMED = (
    f"تم حجز رحلتك من الرياض لجدة الخميس الساعة 06:00 بـ {TOTAL} ريال.",
    "أبشر، تم حجزها لك الخميس الساعة 06:00.",
    "أبشر، حجزتها، الخميس الساعة 06:00.",
)
SUMMARY = f"رحلتك من الرياض لجدة الخميس الساعة 06:00، سياحي لشخص واحد، بـ {TOTAL} ريال. أحجزها لك؟"
BOOKED = f"تم حجز رحلتك بـ {TOTAL} ريال، رحلة سعيدة."


def _asked(request: ChatRequest) -> tuple[str, int, bool]:
    """The caller's last words in `request`, the tool results after them, and whether a claim
    was held back since."""
    messages = list(request.messages)
    last = max(n for n, m in enumerate(messages) if m.role == "user")
    after = messages[last:]
    held = any(m.role == "system" and m.content == CLAIM_HELD for m in after)
    return messages[last].content, sum(m.role == "tool" for m in after), held


def _talker(claimed: str) -> FunctionLLM:
    """A fake model that books before the summary, then says `claimed`, and says the trip with
    its total once that claim is held back; on the yes it books and claims it again."""

    def answer(request: ChatRequest) -> Sequence[ScriptStep]:
        words, results, held = _asked(request)
        if ASKED in words:
            if not results:
                return ScriptedLLM.call_tool(
                    "find_flights", destination="Jeddah", depart=DAY.isoformat()
                )
            return ScriptedLLM.reply(LISTED)
        if PICKED in words:
            if results == 0:
                return ScriptedLLM.call_tool("choose_flights", outbound_id=FIRST)
            if results == 1:
                return ScriptedLLM.call_tool("book_trip")
            return ScriptedLLM.reply(SUMMARY if held else claimed)
        if AGREED in words:
            return ScriptedLLM.call_tool("book_trip") if not results else ScriptedLLM.reply(BOOKED)
        return ScriptedLLM.reply("تمام.")

    return FunctionLLM(answer)


async def _called(llm: FunctionLLM) -> tuple[Airline, list[list[str]]]:
    airline, check = Airline(today=lambda: TODAY), BookingCheck()
    settings = for_the_app(VoiceSettings.model_validate({"env": "test"}), agent="lean")
    agent = declare(lean_deps(airline, check=check))
    heard: list[list[str]] = []
    async with TextCall(
        agent, llm=llm, settings=settings, caller=demo_caller(), today=TODAY, language="ar-SA"
    ) as call:
        check.read_from(lambda: call.emitted)
        for words in (ASKED, PICKED, AGREED):
            turn = await call.user(words)
            await call.advance(30.0)
            heard.append([clause.text for clause in turn.heard()])
        return airline, heard


@pytest.mark.parametrize("claimed", CLAIMED)
def test_a_booking_claimed_before_book_trip_booked_is_never_said_then_is_once_booked(
    claimed: str,
) -> None:
    llm = _talker(claimed)
    airline, (_, picked, agreed) = asyncio.run(_called(llm))
    said = " ".join(picked)
    assert not [claim for claim in ("تم حجز", "حجزتها") if claim in said], said
    assert SUMMARY.split("،")[0] in said
    notices = failure_notices()
    assert not [text for text in picked if form(text) in notices]  # no notice in its place
    assert any(CLAIM_HELD in (m.content for m in r.messages) for r in llm.requests)
    (booking,) = airline.bookings.made
    assert booking.total_sar == TOTAL
    assert "تم حجز رحلتك" in " ".join(agreed)


def _guard(*done: str) -> SpeechGuard:
    """The guard of a lean reply, its claimants the lean agent's (its tools alone), the
    booking's results marked done `done`."""
    settings = for_the_app(VoiceSettings.model_validate({"env": "test"}), agent="lean")
    agent = declare(lean_deps(Airline(today=lambda: TODAY)))
    memory = Memory(done={"book_trip": list(done)} if done else {})
    return SpeechGuard(
        settings=settings.guard,
        year=TODAY.year,
        claimants=claimants((), [t for t in agent.tools if isinstance(t, Tool)]),
        record=None,
        memory=memory,
        heard=(),
    )


@pytest.mark.parametrize("phrase", [p for listed in REWORDED.values() for p in listed])
def test_each_rewording_is_held_with_no_booking_and_said_after_one(phrase: str) -> None:
    clause = f"{phrase}."
    assert _guard().check(clause).reason == "unsupported_claim"
    assert _guard('{"status": "booked"}').check(clause).passed


@pytest.mark.parametrize(
    "clause",
    [
        "ما حجزتها للحين،",  # I haven't booked it yet (a clause of a reply)
        "ما تم حجزها",  # it was not booked
        "الرحلة محجوزة بالكامل ذاك اليوم",  # the flight is sold out that day
        "No, nothing has been booked yet.",  # the library's defaults hold "has been booked"
        "I haven't got you booked yet.",
    ],
)
def test_an_honest_negative_is_said_with_no_booking(clause: str) -> None:
    assert _guard().check(clause).passed

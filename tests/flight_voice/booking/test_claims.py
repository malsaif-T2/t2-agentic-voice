"""Rule A on the booking's claims (flight_voice/booking/lines.py's `CLAIMS`; docs/SECURITY.md,
invariant 2): with no booking in the call's record, the talker's honest negatives pass, in
English and in Arabic, and every claim phrase is blocked; and, adversarially, after the travel
profile (full of six-digit references) and no `book_trip`, a past reference said beside a claim
is blocked, while the same reference said as a trip flown passes (rule B: the profile holds
it)."""

from __future__ import annotations

import asyncio
from typing import Final

import pytest
from flight_voice.booking import lines
from flight_voice.booking.draft import BOOK_TRIP
from flight_voice.tools.profile import TRAVELER_PROFILE, traveler_profile
from t2_agentic_voice import VoiceSettings
from t2_agentic_voice.core.settings.tts import LanguageTag
from t2_agentic_voice.domain.claims import any_action_claims, check_claims, every_language
from t2_agentic_voice.evals import ScriptedLLM, TextCall, TextTurn

from tests.flight_voice.booking.booking_support import CALLER, agent, airline, planned

NEGATIVES: Final = (
    "Nothing is booked.",
    "No booking was made.",
    "Okay, nothing is booked yet.",
    "ما تم الحجز",  # ma tamm al-Hajz: the booking was not made
    "لم يتم الحجز",  # lam yatimm al-Hajz: the same, in MSA
    "ما حجزت لك شي",  # ma Hajazt lak shay: I booked nothing for you
)
# A past trip's reference, which the demo traveler's profile holds.
PAST_REFERENCE: Final = "482913"


def _passes(clause: str) -> bool:
    guard = VoiceSettings(env="test").guard
    verdict = check_claims(
        clause,
        claims={BOOK_TRIP: every_language(lines.CLAIMS.phrases)},
        any_action=any_action_claims(guard.claims),
        evidence=(),
        settings=guard,
        year=2026,
    )
    return verdict.passed


@pytest.mark.parametrize("clause", NEGATIVES)
def test_an_honest_negative_passes_with_nothing_booked(clause: str) -> None:
    assert _passes(clause)


@pytest.mark.parametrize("phrase", every_language(lines.CLAIMS.phrases))
def test_every_claim_phrase_is_blocked_with_nothing_booked(phrase: str) -> None:
    assert not _passes(f"{phrase} it.")
    assert not _passes(phrase)


async def _after_the_profile(reply: str, tag: LanguageTag) -> TextTurn:
    flights = airline()
    made = agent(flights, planned(), tools=(traveler_profile(flights),))
    llm = ScriptedLLM([ScriptedLLM.call_tool(TRAVELER_PROFILE), ScriptedLLM.reply(reply)])
    async with TextCall(made, llm=llm, caller=CALLER, language=tag) as call:
        turn = await call.user("When did I last go to Dubai?")
        await call.advance(10.0)
        return turn


@pytest.mark.parametrize(
    ("reply", "tag", "claim"),
    [
        (f"{PAST_REFERENCE}. I've booked it.", "en", "booked"),
        (f"{PAST_REFERENCE}، حجزت لك", "ar-SA", "حجزت"),
    ],
)
def test_a_past_reference_beside_a_claim_is_blocked_after_the_profile(
    reply: str, tag: LanguageTag, claim: str
) -> None:
    """The claim is never heard: the profile is no evidence of a booking (it has no
    `reports_on`). In English the reference is its own clause, which rule B passes as the
    profile's; in Arabic the one clause is blocked whole."""
    turn = asyncio.run(_after_the_profile(reply, tag))
    turn.expect.tool_call(TRAVELER_PROFILE)
    assert turn.blocked != ()
    heard = " ".join(clause.text for clause in turn.heard())
    assert claim not in heard
    if tag != "en":
        assert PAST_REFERENCE not in heard


def test_a_past_reference_said_as_a_trip_flown_passes_after_the_profile() -> None:
    reply = f"Your last Dubai trip was {PAST_REFERENCE}."
    turn = asyncio.run(_after_the_profile(reply, "en"))
    assert turn.blocked == ()
    turn.expect.said(contains=PAST_REFERENCE)

"""`ActionSafetySuite` (the design's 9.3) on the flight agent's booking, in English and in Saudi
Arabic: each case a fresh `TextCall` of a small agent with `book_trip` over a fresh mock airline,
the call's caller the demo traveler, as the token route mints every caller.

Each case starts on a fresh call and runs nothing before it, so the trip book gives every call
a complete, priced trip (London, out on 17 December and back on the 20th): `validate` fills the
draft from it as it does in a real call. The sample draft is that filled draft, not the empty
`BookingDraft()`: the suite's cases check the confirmed draft holds the sample's values, and
`validate` replaces every field, so only the filled draft is the one confirmed. The talker
judges the answers the yes rule's lists leave unplaced, as the flight agent's does, so the
suite's judged cases play their calls.
"""

from __future__ import annotations

from pydantic import BaseModel
from t2_agentic_voice import Action, VoiceAgent
from t2_agentic_voice.core.settings.tts import LanguageTag
from t2_agentic_voice.evals import ActionSafetySuite

from tests.flight_voice.booking.booking_support import (
    CALLER,
    agent,
    airline,
    booking,
    booking_of,
    planned,
)


class TestBookTripIsSafe(ActionSafetySuite):
    """`book_trip`, in English, over a fresh airline for each case."""

    language: LanguageTag | None = "en"
    caller = CALLER

    def make_agent(self) -> VoiceAgent:
        return agent(airline(), planned())

    def action_under_test(self) -> Action:
        return booking(self.make_agent())

    def sample_draft(self) -> BaseModel:
        return booking_of(airline())

    def test_its_judged_cases_put_the_answers_to_the_model(self) -> None:
        assert self._scene().asks


class TestBookTripIsSafeInSaudiArabic(TestBookTripIsSafe):
    """`book_trip`, in Saudi Arabic."""

    language = "ar-SA"

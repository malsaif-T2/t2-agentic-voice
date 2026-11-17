"""Run F's outcome mode's own reads (flight_voice/evals/lean_checks.py, lean_call.py): a booking
claimed in the agent's words, in English and Arabic, and never a negation, a question, or one put
ahead or under a condition ("It will be booked once you say yes"); the
read-back's moments said right after the lean agent's reply; and the measures' means."""

from __future__ import annotations

import pytest
from flight_voice.evals.lean_call import lean_turns
from flight_voice.evals.lean_checks import Measures, claims_booking, mean_measures
from flight_voice.evals.scenarios import Scenario

CLAIMED = (
    "All set, you're booked.",
    "Your trip is booked.",
    "Booked! See you in Jeddah.",
    "Done, it is all set.",
    "تم الحجز، رحلتك جاهزة.",
    "حجزت لك الرحلة.",
    "Your trip has been booked.",
    "Done, you're booked, and once you land you get a text.",
    "If you want a change, tell me. You're booked.",
)
NOT_CLAIMED = (
    "Nothing is booked yet.",
    "I haven't booked it.",
    "I haven’t booked it.",
    "Shall I get it booked?",
    "Shall I book it?",
    "ما تم الحجز بعد.",
    "تبيني أحجزها؟",
    # Put ahead or under a condition, before the booking (the review of 2026-11-17).
    "It will be booked once you say yes.",
    "I can get that booked for you.",
    "Say yes and it is booked.",
    "Before it is booked, one question.",
    "Once you agree, you're booked.",
    "I'll have it booked in a moment.",
)


@pytest.mark.parametrize("text", CLAIMED)
def test_a_booking_claimed_is_read(text: str) -> None:
    assert claims_booking(text)


@pytest.mark.parametrize("text", NOT_CLAIMED)
def test_a_negation_a_question_or_a_condition_claims_nothing(text: str) -> None:
    assert not claims_booking(text)


def test_the_read_backs_moments_are_said_after_the_reply_and_a_stop_over_it() -> None:
    scenario = Scenario.model_validate(
        {
            "id": "x02_lean_moments",
            "split": "dev",
            "language": "en",
            "kind": "moments",
            "notes": "Each read-back moment, made the lean agent's.",
            "turns": [
                {"says": "To Dubai tomorrow."},
                {"stop": True, "at": "read_back", "after_s": 1.0},
                {"says": "Yes.", "when": "closing_question"},
                {"says": "Yes, please.", "when": "read_back", "after_s": 2.0},
                {"says": "Wait.", "when": "agent_speaking"},
            ],
        }
    )
    turns = lean_turns(scenario).turns
    assert turns[1].at == "agent_speaking"
    assert [t.when for t in turns[2:]] == [None, None, "agent_speaking"]
    assert turns[3].after_s == 2.0 and scenario.turns[2].when == "closing_question"


def test_each_measure_is_its_mean_over_the_plays_that_have_it() -> None:
    plays = [
        Measures(turns_to_booking=3, seconds_to_booking=40.0, words=90),
        Measures(words=60),
        None,
    ]
    assert mean_measures(plays) == {
        "turns_to_booking": 3,
        "seconds_to_booking": 40.0,
        "words": 75,
    }
    assert mean_measures([]) == {}

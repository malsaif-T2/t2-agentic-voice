"""Run F's `stage_note` check (flight_voice/evals/spoken.py, rule F's amendment of 2026-11-17
on stage notes): a turn fails when what the caller heard holds a stage note or markup, on every
turn of every scenario, whatever the turn expects.

- **Notes**: a parenthesis or bracket that holds a Latin letter in a reply in Arabic script,
  glued or not; one that opens a stage word in any language and any case; a "<" that opens a
  tag, a runtime's line heard before it or not.
- **Not notes**: Arabic in parentheses, an English parenthesis that opens no stage word, a "<"
  before no letter.
- The stage words are the guard's (`guard.drop_stage_notes`) in the measurement's own code."""

from __future__ import annotations

import pytest
from flight_voice.evals.spoken import STAGE_WORDS, stage_note
from t2_agentic_voice.agent import leaked_reasoning

from tests.flight_voice.evals.test_checks import clause, failed, read, scenario

# ayy waHda tibi? (which one do you want?)
WHICH = "أي وحدة تبي؟"


@pytest.mark.parametrize(
    "text",
    [
        f"{WHICH}(Waiting for the caller)",
        f"{WHICH} [Note: pick one]",
        f"{WHICH} (Business)",
        "Which one would you like? (pause)",
        "Sure. [No output]",
        # intiZaar radd al-'amiil: waiting for the customer's answer
        f"{WHICH}[انتظار رد العميل]",
        '<action tool="hold_seat"/>',
        "Checking that. </data>",
    ],
)
def test_a_stage_note_or_markup_is_found(text: str) -> None:
    assert stage_note(text)


@pytest.mark.parametrize(
    "text",
    [
        # illi tiTla' 07:40 b-610 riyaal (al-arkhaS), the 07:40 at 610 riyals (the cheapest)
        "اللي تطلع 07:40 بـ 610 ريال (الأرخص)، واللي تطلع 16:05.",
        "The 07:40 (no seats left) and the 16:05 (the cheapest).",
        "Fares under <5% of the total, 3 < 4.",
        # ma fiih maqaa'id, (qaa'imat al-intiZaar): no seats, (the waiting list)
        "ما فيه مقاعد (قائمة الانتظار).",
    ],
)
def test_arabic_in_parentheses_and_a_plain_aside_are_no_note(text: str) -> None:
    assert not stage_note(text)


def test_every_turn_fails_on_a_note_heard_whatever_it_expects() -> None:
    saudi = scenario({"says": "أبي أروح جدة"}, language="ar-SA")  # abi aruuH jidda
    noted = clause(f"{WHICH}(Waiting)", language="ar-SA")
    assert failed(saudi, read(noted)) == ["stage_note"]
    assert failed(saudi, read(clause(WHICH, language="ar-SA"))) == []
    english = scenario({"says": "Book it."})
    progress = clause("One moment, I'm checking.", phrase=True)
    assert failed(english, read(progress, clause('<action tool="hold_seat"/>'))) == ["stage_note"]


def test_the_stage_words_are_the_guards_list() -> None:
    assert STAGE_WORDS == leaked_reasoning.STAGE_WORDS

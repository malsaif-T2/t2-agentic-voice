"""The question limit's pure part (agent/question_limit.py; D-085): which clause asks the caller
a question, and which clauses of one reply are said.

- **A question** is a clause whose last character is a question mark, "?" or the Arabic one,
  once trailing spaces and closing quotes and brackets are taken off, as the clause splitter
  reads a word's end: «...؟» and `...?"` ask. A mark inside the clause, or one followed by
  another mark ("?!", "؟."), does not.
- **One reply** says its clauses up to and including its first question (`guard.
  questions_per_reply`, 1 by default); the next clause that asks one is not said, nor anything
  after it. Clauses between the two are said; a reply that asks one question and goes on with
  steps is said whole; with no limit, every clause is.
- **Only what was said counts**: a question the guard blocked is not among the said clauses the
  limit reads, so it asks nothing.
- **The owner's demo reply** (2026-11-11), a ticket asked for, then how urgent it is asked again
  and again, then the caller's silence played out: only its clauses up to the second question
  are said."""

from __future__ import annotations

import pytest
from t2_agentic_voice.agent.question_limit import QuestionLimit, asks, said_clauses
from t2_agentic_voice.domain.text.clauses import split_clauses


@pytest.mark.parametrize(
    "clause",
    [
        "Is it urgent?",
        "Is it urgent?  ",
        "هل المشكلة عاجلة؟",  # hal al-mushkila 'aajila, is the problem urgent?
        "«هل المشكلة عاجلة؟»",
        'Did you mean "reset?"',
        "(is it the office one?)",
        "Did it say “try again?”",
    ],
)
def test_a_clause_that_ends_with_a_question_mark_asks(clause: str) -> None:
    assert asks(clause)


@pytest.mark.parametrize(
    "clause",
    [
        "Open Settings.",
        "Really?!",
        "هل جربت؟.",  # hal jarrabt, did you try? then a full stop
        'He asked "why?" and left.',
        "Is it 3? or 4",
        "",
        "   ",
    ],
)
def test_a_clause_with_no_question_mark_at_its_end_asks_nothing(clause: str) -> None:
    assert not asks(clause)


def test_two_questions_leave_the_second_and_all_after_it_unsaid() -> None:
    clauses = ("Is it urgent?", "Is it blocking your work?", "Tell me more.")
    assert said_clauses(clauses, most=1) == ("Is it urgent?",)


def test_the_clauses_between_the_two_questions_are_said() -> None:
    clauses = ("Is it urgent?", "I can open a ticket.", "Is it blocking you?", "Thanks.")
    assert said_clauses(clauses, most=1) == ("Is it urgent?", "I can open a ticket.")


@pytest.mark.parametrize(
    "clauses",
    [
        ("Did you restart it?", "If not, hold the power key.", "Then wait ten seconds."),
        ("First open Settings.", "Then press Reset.", "Did that work?"),
        ("Open Settings.", "Then press Reset."),
    ],
)
def test_one_question_then_steps_is_said_whole(clauses: tuple[str, ...]) -> None:
    assert said_clauses(clauses, most=1) == clauses


def test_the_limit_is_the_settings_and_none_is_no_limit() -> None:
    clauses = ("Is it urgent?", "Is it yours?", "Is it new?", "Thanks.")
    assert said_clauses(clauses, most=2) == ("Is it urgent?", "Is it yours?")
    assert said_clauses(clauses, most=None) == clauses


# The owner's demo reply, as Ole5's talker wrote it in kind (2026-11-11): "tamam, aqdar aftaH lak
# tathkara" (fine, I can open a ticket for you), "kam mada ahammiyat al-mushkila?" (how important
# is the problem?), "'ashaan aHaddid al-awlawiyya" (so I set its priority), "hal hiya 'aajila?"
# (is it urgent?), "walla tigdar tintaDHir?" (or can you wait?), "ya'ni hal waqqafat shughlak?"
# (I mean, has it stopped your work?), "ma fi radd" (no answer), "fa-ana ma aqdar aftaH tathkara
# al-aan" (so I can't open a ticket now).
DEMO = (
    "تمام، أقدر أفتح لك تذكرة. كم مدى أهمية المشكلة؟ عشان أحدد الأولوية. هل هي عاجلة؟ "
    "ولا تقدر تنتظر؟ يعني هل وقفت شغلك؟ ما في رد، فأنا ما أقدر أفتح تذكرة الآن."
)


def test_the_demo_reply_says_only_its_clauses_up_to_its_second_question() -> None:
    clauses = split_clauses(DEMO, max_chars=None)
    assert said_clauses(clauses, most=1) == (
        "تمام،",
        "أقدر أفتح لك تذكرة.",
        "كم مدى أهمية المشكلة؟",
        "عشان أحدد الأولوية.",
    )


def test_a_reply_stops_at_the_question_past_its_limit_and_counts_what_it_left() -> None:
    limit, said = QuestionLimit(1), ["Is it urgent?"]
    assert (limit.stopped, limit.unsaid) == (False, 0)
    assert not limit.drops("I can help.", said=said)
    assert limit.drops("Is it blocking you?", said=said)
    assert limit.drops("Tell me more.", said=said)  # after the stop, nothing is said
    assert (limit.stopped, limit.unsaid) == (True, 2)


def test_a_question_that_was_not_said_asks_nothing() -> None:
    """The guard blocked the first question, so the clauses said hold none: the next is said."""
    limit = QuestionLimit(1)
    assert not limit.drops("Is it blocking you?", said=[])
    assert (limit.stopped, limit.unsaid) == (False, 0)


def test_with_no_limit_nothing_is_dropped() -> None:
    limit = QuestionLimit(None)
    said = ["Is it urgent?", "Is it yours?"]
    assert not limit.drops("Is it new?", said=said)
    assert (limit.stopped, limit.unsaid) == (False, 0)

"""The yes rule under `interruptions.yes_over_read_back` (D-108, the owner's ruling of 2026-11-17,
"Any yes books"; domain/yes_rule.py, yes_kinds.py; docs/SECURITY.md, invariant 1): with the
read-back's lines handed to it (`said`), a bare yes over the closing question is a yes, and so is
khalas beside a send word, each unless the words are the agent's own lines heard back; `held`
issues a yes held over the summary only for words begun once its first clause began and before
its last played, by the lists or a model's yes within the rails, once the receipt stands. Every
answer with the setting off is as before (characterization). Adversarial (GP-08): a no, a
question mark, a change marker, the agent's echo, words before the read-back began or after its
summary ended, typed words outside a test, a forged receipt, a model's yes on a no. Every word
and time here is made up for the test."""

from __future__ import annotations

from typing import Any

import pytest
from t2_agentic_voice.core.config import Environment
from t2_agentic_voice.core.yes_inputs import HEARD_WORDS_SEAL, HeardSource, HeardWords
from t2_agentic_voice.domain.words import rule_form
from t2_agentic_voice.domain.yes_kinds import SaidLines, held_yes, holds_okay
from t2_agentic_voice.domain.yes_rule import (
    AskAgain,
    Correction,
    ModelWord,
    Yes,
    YesOutcome,
    decide,
    held,
    is_confirmed,
    judged,
)
from t2_agentic_voice.domain.yes_words import ConsentWords, consent_words
from t2_agentic_voice.voice.session.read_back import played_receipt

ARABIC = consent_words("ar", action_send=("احجزها", "أكد الحجز"))
ENGLISH = consent_words("en")
DRAFT = '{"trip": "made up"}'
# The summary's first audio at 2.0, its last clause played at 10.0, the question's at 12.0.
BEGAN_AT, SUMMARY_AT, QUESTION_AT = 2.0, 10.0, 12.0
OVER_SUMMARY, OVER_QUESTION, AFTER = 5.0, 11.0, 12.5
READ_BACK = ("Made-up summary of the trip, two travelers.", "Made-up question, shall I book it?")
ASKED_AGAIN = ("Made-up line asking again, shall I book it?",)
KHALAS = "خلاص"  # khalas, that's it: a stop word to the interruption rule, a filler here


def _heard(
    text: str, speech_at: float | None, *, source: HeardSource = "speech_to_text"
) -> HeardWords:
    values = {
        "turn_id": 3,
        "text": text,
        "language": "en" if text.isascii() else "ar",
        "at": (speech_at or 0.0) + 1.0,
        "speech_at": speech_at,
        "source": source,
    }
    return HeardWords.model_validate(values, context=HEARD_WORDS_SEAL)


def _receipt(question_ended_at: float | None = QUESTION_AT, began: float | None = BEGAN_AT) -> Any:
    return played_receipt(
        action="book_made_up_trip",
        draft_json=DRAFT,
        reply_id=2,
        summary_played_at=SUMMARY_AT,
        question_ended_at=question_ended_at,
        summary_began_at=began,
    )


def _said(read_back: tuple[str, ...] = READ_BACK) -> SaidLines:
    return SaidLines(read_back=read_back, asked_again=ASKED_AGAIN, over_asked_again=False)


def _words(text: str) -> ConsentWords:
    return ENGLISH if text.isascii() else ARABIC


def _decide(text: str, speech_at: float, *, on: bool, ended: float | None = QUESTION_AT) -> Any:
    said = _said() if on else None
    heard = _heard(text, speech_at)
    return decide(heard, _receipt(ended), words=_words(text), env="prod", said=said)


def _held(
    text: str,
    speech_at: float | None = OVER_SUMMARY,
    word: ModelWord = None,
    *,
    receipt: Any = None,
    env: Environment = "prod",
    source: HeardSource = "speech_to_text",
    said: SaidLines | None = None,
) -> YesOutcome:
    heard = _heard(text, speech_at, source=source)
    given = receipt if receipt is not None else _receipt()
    return held(word, heard, given, words=_words(text), env=env, said=said or _said())


@pytest.mark.parametrize("text", ["yes", "yeah please", "نعم", "إيه", "إي"])
@pytest.mark.parametrize("ended", [None, QUESTION_AT], ids=["question_plays", "question_ended"])
def test_a_bare_yes_over_the_closing_question_is_asked_again_off_and_a_yes_on(
    text: str, ended: float | None
) -> None:
    off = _decide(text, OVER_QUESTION, on=False, ended=ended)
    assert off == AskAgain()  # the owner's 2026-11-10 ruling, with the setting off
    on = _decide(text, OVER_QUESTION, on=True, ended=ended)
    assert isinstance(on, Yes) and is_confirmed(on.confirmed)
    assert (on.confirmed.turn_id, on.confirmed.draft_json) == (3, DRAFT)


def test_after_the_question_a_yes_is_a_yes_either_way_and_nothing_else_changes() -> None:
    for on in (False, True):
        assert isinstance(_decide("yes", AFTER, on=on), Yes)
        assert isinstance(_decide("yes send it", OVER_QUESTION, on=on), Yes)
        assert _decide("no", AFTER, on=on) != AskAgain()
        assert isinstance(_decide("yes but the date", AFTER, on=on), Correction)
        assert _decide("yes?", OVER_QUESTION, on=on) == AskAgain()  # a yes asked back
        assert _decide("yes no", OVER_QUESTION, on=on) == AskAgain()
        assert _decide("yes", OVER_SUMMARY, on=on) == AskAgain()  # over the summary: decide's never


def test_a_bare_yes_that_is_the_agents_own_question_heard_back_is_asked_again() -> None:
    # GP-08: a closing question that holds a yes word, heard back over itself, never books
    said = _said(("Made-up summary.", "Made-up question, yes or not yet?"))
    heard = _heard("yes", OVER_QUESTION)
    assert decide(heard, _receipt(None), words=ENGLISH, env="prod", said=said) == AskAgain()


@pytest.mark.parametrize(
    "text", [f"{KHALAS} احجزها", f"{KHALAS}، أكد الحجز", f"يلا {KHALAS} احجزها"]
)
@pytest.mark.parametrize("speech_at", [OVER_QUESTION, AFTER], ids=["over", "after"])
def test_khalas_beside_a_send_word_is_a_yes_on_and_asked_again_off(
    text: str, speech_at: float
) -> None:
    assert holds_okay(rule_form(text))
    off = _decide(text, speech_at, on=False)
    assert isinstance(off, AskAgain)  # send words with no yes word: unclear to the lists
    assert isinstance(_decide(text, speech_at, on=True), Yes)


@pytest.mark.parametrize(
    "text",
    [
        KHALAS,
        f"{KHALAS} {KHALAS}",
        f"{KHALAS} احجزها؟",
        f"{KHALAS} لا تحجزها",
        f"{KHALAS} احجزها بس",
    ],
)
def test_khalas_alone_or_beside_a_no_a_question_or_other_words_is_no_yes(text: str) -> None:
    assert not isinstance(_decide(text, OVER_QUESTION, on=True), Yes)
    assert not isinstance(_decide(text, AFTER, on=True), Yes)


@pytest.mark.parametrize(
    ("text", "word"),
    [
        ("yes", None),
        ("yes please send it", None),
        ("send it", None),
        ("نعم", None),
        ("إيه", None),
        (f"{KHALAS} أكد الحجز", None),
        ("sounds good to me", "yes"),
        ("sounds good to me", "send"),
    ],
)
def test_a_yes_held_over_the_summary_is_issued_once_the_receipt_stands(
    text: str, word: ModelWord
) -> None:
    outcome = _held(text, word=word)
    assert isinstance(outcome, Yes) and is_confirmed(outcome.confirmed)
    assert (outcome.confirmed.speech_at, outcome.confirmed.words) == (OVER_SUMMARY, text)
    assert outcome.confirmed.action == "book_made_up_trip"


@pytest.mark.parametrize(
    ("text", "word"),
    [
        ("no", None),
        ("yes no", None),
        ("yes?", None),
        ("yes but the date", None),
        ("yes but the date", "yes"),
        ("sounds good to me", None),  # unplaced, and no model's word
        ("sounds good to me", "no"),
        ("sounds good to me", "unclear"),
        ("nope sounds good", "yes"),  # a model's yes beside a no word
        ("sounds good actually", "send"),  # beside a change marker
        ("please", None),  # fillers alone hold no yes
        ("لا", None),
        ("إيه بس", "yes"),  # a change marker
    ],
)
def test_no_yes_is_held_on_a_no_a_question_a_change_or_unplaced_words(
    text: str, word: ModelWord
) -> None:
    assert _held(text, word=word) == AskAgain()


@pytest.mark.parametrize(
    "speech_at",
    [None, BEGAN_AT - 0.5, BEGAN_AT, SUMMARY_AT, OVER_QUESTION, AFTER],
    ids=["no_time", "before_the_read_back", "at_its_start", "at_its_end", "over_question", "after"],
)
def test_a_held_yes_counts_only_when_begun_over_the_summary_itself(
    speech_at: float | None,
) -> None:
    # GP-08: words before the read-back began, or once its summary ended, are never held
    assert _held("yes", speech_at) == AskAgain()
    assert isinstance(_held("yes", BEGAN_AT + 0.01), Yes)


def test_a_held_yes_needs_the_receipts_start_its_seals_and_spoken_words() -> None:
    assert _held("yes", receipt=_receipt(began=None)) == AskAgain()
    assert _held("yes", source="typed") == AskAgain()
    assert isinstance(_held("yes", source="typed", env="test"), Yes)
    forged = _receipt().model_copy()  # a copy, which proves nothing
    assert _held("yes", receipt=forged) == AskAgain()


def test_the_agents_own_lines_heard_back_are_never_held() -> None:
    # GP-08: the echo rail, as the session tells it over the summary
    said = _said(("Yes, made-up summary for two.", "Made-up question?"))
    assert _held("yes", said=said) == AskAgain()
    assert _held("made-up summary for two", word="yes", said=said) == AskAgain()
    assert not held_yes("yes", "made-up summary for two", ENGLISH, said=said)
    assert held_yes(None, "yes", ENGLISH, said=_said())


def test_over_the_question_the_models_yes_books_only_under_the_setting() -> None:
    heard = _heard("sounds good to me", OVER_QUESTION)
    receipt = _receipt(None)
    given: dict[str, Any] = {"current": receipt, "words": ENGLISH, "env": "prod", "said": _said()}
    assert judged("yes", heard, receipt, **given) == AskAgain()  # the owner's 2026-11-10 ruling
    bare = judged("yes", heard, receipt, **given, bare=True)
    assert isinstance(bare, Yes)
    alone = _heard("send it", OVER_QUESTION)  # a send word alone stays asked again
    assert judged("yes", alone, receipt, **given, bare=True) == AskAgain()
    assert isinstance(judged("send", heard, receipt, **given), Yes)

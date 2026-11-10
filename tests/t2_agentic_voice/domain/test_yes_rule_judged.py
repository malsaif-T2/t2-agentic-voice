"""The yes rule's word on a chat model's word (domain/yes_rule.py's `judged`; D-082, the owner's
rulings of 2026-11-10; docs/SECURITY.md, invariant 1): `decide` marks what its lists leave
unplaced `askable`, and only that may be put to a model; `judged` keeps every other answer of
the lists' whatever the model says, and takes its `send` or `yes` only within the rails: no no
word, no question mark, no change marker (each, in each language), not the agent's own words
heard back, the receipt still standing, and over the closing question only a go-ahead.
Adversarial (GP-08): a model's yes on a listed no, on a yes beside a no, on a bare yes over the
question, on a send word alone, on a yes with a change, on the closing question heard back, on
a stale or forged receipt. Every word and time here is made up for the test."""

from __future__ import annotations

from typing import Any

import pytest
from t2_agentic_voice.core.config import Environment
from t2_agentic_voice.core.yes_inputs import HEARD_WORDS_SEAL, HeardSource, HeardWords
from t2_agentic_voice.domain.consent_check import ConsentAnswer
from t2_agentic_voice.domain.words import rule_form
from t2_agentic_voice.domain.yes_rule import (
    AskAgain,
    Correction,
    Declined,
    ModelWord,
    Yes,
    YesOutcome,
    decide,
    is_confirmed,
    judged,
)
from t2_agentic_voice.domain.yes_words import PRESET_CONSENT, ConsentWords, consent_words
from t2_agentic_voice.voice.session.read_back import played_receipt

ARABIC = consent_words("ar")
ENGLISH = consent_words("en")
DRAFT = '{"summary": "made up"}'
# The summary's last clause played at 10.0, the closing question's at 12.0.
SUMMARY_AT, QUESTION_AT = 10.0, 12.0
OVER_QUESTION, AFTER = 11.0, 12.5
# What the agent said: its read-back's summary, its closing question, its ask-again line.
SAID = (
    "I'll book room R-204 for: the projector is broken.",
    "Shall I send it?",
    "Sorry, I didn't catch that. Shall I go ahead?",
    # "baHjiz lak al-ghurfa": I'll book you the room; "arsil aT-Talab?": send the request?
    "بحجز لك الغرفة R-204.",
    "أرسل الطلب؟",
)
WORDS = (ENGLISH, ARABIC)
YES_WORDS: tuple[ConsentAnswer, ...] = ("send", "yes")


def _heard(
    text: str, speech_at: float | None = AFTER, *, source: HeardSource = "speech_to_text"
) -> HeardWords:
    values = {
        "turn_id": 7,
        "text": text,
        "language": "ar",
        "at": (speech_at or 0.0) + 1.0,
        "speech_at": speech_at,
        "source": source,
    }
    return HeardWords.model_validate(values, context=HEARD_WORDS_SEAL)


def _receipt(question_ended_at: float | None = QUESTION_AT, *, reply: int = 4) -> Any:
    return played_receipt(
        action="open_request",
        draft_json=DRAFT,
        reply_id=reply,
        summary_played_at=SUMMARY_AT,
        question_ended_at=question_ended_at,
    )


def _words(text: str) -> ConsentWords:
    return ENGLISH if text.isascii() else ARABIC


def _judged(
    word: ModelWord,
    text: str,
    speech_at: float = AFTER,
    *,
    receipt: Any = None,
    current: Any = "same",
    env: Environment = "prod",
) -> YesOutcome:
    given = receipt if receipt is not None else _receipt()
    now = given if current == "same" else current
    heard = _heard(text, speech_at)
    return judged(word, heard, given, current=now, words=_words(text), env=env, said=SAID)


# What the lists leave unplaced, and what they place.


@pytest.mark.parametrize(
    "text",
    [
        "go for it",  # words on no list
        "sure thing",
        "yes, but make it urgent",
        "امممم",  # ummmm, four meems: on no list
        "صح",  # sah, right
        "يلا أرسلها",  # yalla arsilha: send words among fillers, with no yes
        "please send it",
    ],
)
@pytest.mark.parametrize("speech_at", [OVER_QUESTION, AFTER])
def test_what_the_lists_leave_unplaced_is_askable(text: str, speech_at: float) -> None:
    outcome = decide(_heard(text, speech_at), _receipt(), words=_words(text), env="prod")
    assert isinstance(outcome, Correction | AskAgain) and outcome.askable


@pytest.mark.parametrize("text", ["yes, please", "نعم لو سمحت"])
def test_a_yes_among_fillers_is_askable_only_over_the_closing_question(text: str) -> None:
    words = _words(text)
    over = decide(_heard(text, OVER_QUESTION), _receipt(), words=words, env="prod")
    assert isinstance(over, AskAgain) and over.askable
    assert isinstance(decide(_heard(text, AFTER), _receipt(), words=words, env="prod"), Yes)


@pytest.mark.parametrize(
    ("text", "speech_at"),
    [
        ("نعم أرسلها", OVER_QUESTION),  # a listed yes with a send word
        ("yes send it", AFTER),
        ("sure", AFTER),  # a listed yes, once the question ended
        ("اكيد", AFTER),
        ("نعم", OVER_QUESTION),  # a bare yes over the question
        ("sure", OVER_QUESTION),
        ("send it", AFTER),  # a send word alone, as the question's echo would say it
        ("أرسلها", OVER_QUESTION),
        ("تمام", AFTER),  # a listening sound alone
        ("okay", AFTER),
        ("لا", AFTER),  # a no
        ("no thanks", AFTER),
        ("لا لا نعم", AFTER),  # a yes beside a no
        ("نعم؟", AFTER),  # a yes asked back
        ("send it please?", AFTER),  # a question mark among listed words
    ],
)
def test_what_the_lists_place_is_never_askable(text: str, speech_at: float) -> None:
    outcome = decide(_heard(text, speech_at), _receipt(), words=_words(text), env="prod")
    assert not isinstance(outcome, Correction | AskAgain) or not outcome.askable


@pytest.mark.parametrize("word", [*YES_WORDS, "no", "change", "unclear", None])
@pytest.mark.parametrize(
    ("text", "speech_at", "listed"),
    [
        ("لا", AFTER, Declined(words="لا")),
        ("no thanks", AFTER, Declined(words="no thanks")),
        ("لا لا نعم", AFTER, AskAgain()),
        ("نعم", OVER_QUESTION, AskAgain()),
        ("send it", AFTER, AskAgain()),
        ("أرسلها", OVER_QUESTION, AskAgain()),
        ("نعم؟", AFTER, AskAgain()),
        ("Yes?", AFTER, AskAgain()),
        ("تمام", AFTER, AskAgain()),
    ],
)
def test_a_models_word_never_changes_what_the_lists_placed(
    word: ModelWord, text: str, speech_at: float, listed: YesOutcome
) -> None:
    """A model's yes never confirms what the lists refused, and its no never undoes their no."""
    assert _judged(word, text, speech_at) == listed


@pytest.mark.parametrize("word", [*YES_WORDS, "no", "change", "unclear", None])
def test_a_listed_yes_stays_the_lists_yes_whatever_the_model_says(word: ModelWord) -> None:
    outcome = _judged(word, "نعم أرسلها", OVER_QUESTION)
    assert isinstance(outcome, Yes) and is_confirmed(outcome.confirmed)


# The model's word on what the lists left unplaced.


@pytest.mark.parametrize("text", ["go for it", "يلا أرسلها", "sure thing", "صح"])
@pytest.mark.parametrize("word", YES_WORDS)
def test_a_models_yes_or_send_once_the_question_ended_is_a_yes(text: str, word: ModelWord) -> None:
    outcome = _judged(word, text, AFTER)
    assert isinstance(outcome, Yes) and is_confirmed(outcome.confirmed)
    confirmed = outcome.confirmed
    assert (confirmed.action, confirmed.draft_json, confirmed.reply_id) == (
        "open_request",
        DRAFT,
        4,
    )
    assert (confirmed.turn_id, confirmed.words, confirmed.speech_at) == (7, text, AFTER)


@pytest.mark.parametrize("ended", [QUESTION_AT, None])
@pytest.mark.parametrize("text", ["go for it", "sure thing", "صح"])
def test_over_the_closing_question_only_a_go_ahead_confirms(text: str, ended: float | None) -> None:
    """The owner's second ruling: a model's `yes` alone over the question is asked again, as a
    bare «نعم» is; its `send` is a yes."""
    receipt = _receipt(ended)
    assert _judged("yes", text, OVER_QUESTION, receipt=receipt) == AskAgain()
    assert isinstance(_judged("send", text, OVER_QUESTION, receipt=receipt), Yes)


@pytest.mark.parametrize("text", ["sure, send it, buddy", "يلا أرسلها"])
@pytest.mark.parametrize("word", YES_WORDS)
def test_over_the_closing_question_a_listed_send_word_confirms_a_models_yes_too(
    text: str, word: ModelWord
) -> None:
    assert isinstance(_judged(word, text, OVER_QUESTION), Yes)


@pytest.mark.parametrize(
    "text",
    [
        "yes, not like that",
        "go for it, no wait",
        "ايه مو كذا",  # eeh mu kitha: yes, not like that
        "ابدا يا غالي",  # abadan ya ghaali: never, dear
    ],
)
@pytest.mark.parametrize("speech_at", [OVER_QUESTION, AFTER])
@pytest.mark.parametrize("word", YES_WORDS)
def test_a_models_yes_beside_a_no_word_is_asked_again(
    text: str, speech_at: float, word: ModelWord
) -> None:
    assert _judged(word, text, speech_at) == AskAgain()


@pytest.mark.parametrize("text", ["go for it?", "sure thing?", "توكل يا غالي؟", "صح؟"])
@pytest.mark.parametrize("word", YES_WORDS)
def test_a_models_yes_to_words_with_a_question_mark_is_asked_again(
    text: str, word: ModelWord
) -> None:
    assert _judged(word, text, AFTER) == AskAgain()


def _marked() -> list[tuple[str, str]]:
    """Each language's change markers, each in a yes the lists leave unplaced, and after waw."""
    found = [(f"sure {marker} make it urgent", marker) for marker in PRESET_CONSENT["en"].change]
    found += [(f"ايه {marker} عاجلة", marker) for marker in PRESET_CONSENT["ar"].change]
    found += [("ايه ولكن عاجلة", "لكن"), ("ايه وبدل الغرفة", "بدل")]  # wa-, and, on the marker
    return found


@pytest.mark.parametrize(("text", "marker"), _marked())
@pytest.mark.parametrize("speech_at", [OVER_QUESTION, AFTER])
@pytest.mark.parametrize("word", YES_WORDS)
def test_a_models_yes_beside_each_change_marker_is_a_correction(
    text: str, marker: str, speech_at: float, word: ModelWord
) -> None:
    """The owner's ruling: "Yes, but change.." is a request for change, never only a yes."""
    assert _judged(word, text, speech_at) == Correction(words=text)


def test_the_owners_change_markers_are_listed_in_the_rules_form() -> None:
    """The brief's lists: "but", "change", "instead", "except", "actually", "rather"; «بس»,
    «لكن», «غير», «غيّر», «عدل», «عدّل», «بدل», «بدال», «خلها», «خله», the shadda dropped in the
    rule's form."""
    english, arabic = PRESET_CONSENT["en"].change, PRESET_CONSENT["ar"].change
    assert set(english) == {"but", "change", "instead", "except", "actually", "rather"}
    owners = ("بس", "لكن", "غير", "غيّر", "عدل", "عدّل", "بدل", "بدال", "خلها", "خله")
    assert {rule_form(word) for word in owners} <= set(arabic)
    assert all(word == rule_form(word) for word in (*english, *arabic))
    assert consent_words("en").change == english and consent_words("ar").change == arabic


@pytest.mark.parametrize(
    "text",
    [
        "Shall I send it",  # the closing question heard back
        "shall I go ahead",  # the ask-again line's end heard back
        "أرسل الطلب",  # arsil aT-Talab: send the request, the Saudi question heard back
        "the projector is broken",  # a piece of the summary
    ],
)
@pytest.mark.parametrize("speech_at", [OVER_QUESTION, AFTER])
@pytest.mark.parametrize("word", YES_WORDS)
def test_the_agents_own_words_heard_back_are_asked_again_whatever_the_model_says(
    text: str, speech_at: float, word: ModelWord
) -> None:
    assert _judged(word, text, speech_at) == AskAgain()


@pytest.mark.parametrize("text", ["go for it", "يلا أرسلها", "yes, but make it urgent"])
def test_a_models_no_is_declined_its_change_a_correction_and_anything_else_asked_again(
    text: str,
) -> None:
    assert _judged("no", text) == Declined(words=text)
    changed = _judged("change", text)
    assert changed == Correction(words=text) and isinstance(changed, Correction)
    assert not changed.askable  # never put to the model again
    assert _judged("unclear", text) == AskAgain()
    assert _judged(None, text) == AskAgain()  # a failure or a timeout


def test_a_hesitation_the_lists_never_heard_is_asked_again_when_the_model_says_unclear() -> None:
    assert _judged("unclear", "امممم") == AskAgain()


def test_a_stale_receipt_asks_again_whatever_the_model_says() -> None:
    """The receipt built as the words reached the rule must still stand as the word lands: the
    same read-back, current."""
    for word in (*YES_WORDS, "no", "change"):
        assert _judged(word, "go for it", current=None) == AskAgain()  # no read-back current
        other = _receipt(reply=9)  # a new reading took its place
        assert _judged(word, "go for it", current=other) == AskAgain()
        forged = _receipt().model_dump()
        assert _judged(word, "go for it", current=forged) == AskAgain()


def test_a_question_that_ended_since_keeps_the_answer_over_it() -> None:
    """Built anew as the word lands, the receipt may hold the question's end where the first
    held none: it stands, and the words stay over the question."""
    first, now = _receipt(None), _receipt(QUESTION_AT)
    assert _judged("yes", "sure thing", OVER_QUESTION, receipt=first, current=now) == AskAgain()
    assert isinstance(_judged("send", "sure thing", OVER_QUESTION, receipt=first, current=now), Yes)


@pytest.mark.parametrize("env", ["dev", "staging", "prod"])
def test_typed_words_count_for_nothing_outside_a_test_whatever_the_model_says(
    env: Environment,
) -> None:
    typed = _heard("go for it", AFTER, source="typed")
    for word in YES_WORDS:
        outcome = judged(
            word, typed, _receipt(), current=_receipt(), words=ENGLISH, env=env, said=SAID
        )
        assert outcome == AskAgain()
    outcome = judged(
        "send", typed, _receipt(), current=_receipt(), words=ENGLISH, env="test", said=SAID
    )
    assert isinstance(outcome, Yes)


def test_words_begun_over_the_summary_count_for_nothing_whatever_the_model_says() -> None:
    for word in YES_WORDS:
        assert _judged(word, "go for it", SUMMARY_AT - 1.0) == AskAgain()


def test_a_receipt_not_built_by_voice_counts_for_nothing_whatever_the_model_says() -> None:
    forged: Any = _receipt().model_dump()
    heard = _heard("go for it")
    for word in YES_WORDS:
        outcome = judged(word, heard, forged, current=forged, words=ENGLISH, env="test", said=SAID)
        assert outcome == AskAgain()
        outcome = judged(
            word, heard, forged, current=_receipt(), words=ENGLISH, env="test", said=SAID
        )
        assert outcome == AskAgain()

"""The yes rule (domain/yes_rule.py; docs/SECURITY.md, invariant 1): a yes counts only from heard
words and a receipt `voice` built, only after the summary played whole, and over the closing
question only with a send word. Adversarial (GP-08): a yes over the summary, an eager yes, a bare
yes over the closing question, inputs not built by their sealed builders, a correction inside a
yes. Every word and time here is made up for the test."""

from __future__ import annotations

import copy
import pickle
from types import SimpleNamespace
from typing import Any, cast

import pytest
from t2_agentic_voice.core.config import Environment
from t2_agentic_voice.core.yes_inputs import HEARD_WORDS_SEAL, HeardSource, HeardWords
from t2_agentic_voice.domain.yes_rule import (
    AskAgain,
    Correction,
    Declined,
    Yes,
    YesOutcome,
    decide,
    is_confirmed,
)
from t2_agentic_voice.domain.yes_words import ConsentWords, consent_words
from t2_agentic_voice.voice.session.read_back import played_receipt

ARABIC = consent_words("ar")
ENGLISH = consent_words("en")
DRAFT = '{"summary": "made up"}'
# The summary's last clause played at 10.0, the closing question's at 12.0.
SUMMARY_AT, QUESTION_AT = 10.0, 12.0
OVER_QUESTION, AFTER = 11.0, 12.5


def _heard(
    text: str,
    speech_at: float | None,
    *,
    at: float | None = None,
    source: HeardSource = "speech_to_text",
) -> HeardWords:
    values = {
        "turn_id": 7,
        "text": text,
        "language": "ar",
        "at": at if at is not None else (speech_at or 0.0) + 1.0,
        "speech_at": speech_at,
        "source": source,
    }
    return HeardWords.model_validate(values, context=HEARD_WORDS_SEAL)


def _receipt(
    question_ended_at: float | None = QUESTION_AT, *, summary_at: float = SUMMARY_AT, reply: int = 4
) -> Any:
    return played_receipt(
        action="open_request",
        draft_json=DRAFT,
        reply_id=reply,
        summary_played_at=summary_at,
        question_ended_at=question_ended_at,
    )


def _decide(
    heard: HeardWords | None,
    receipt: Any = None,
    *,
    words: ConsentWords = ARABIC,
    env: Environment = "prod",
) -> YesOutcome:
    return decide(heard, receipt if receipt is not None else _receipt(), words=words, env=env)


@pytest.mark.parametrize(
    ("text", "words"),
    [
        ("نعم", ARABIC),
        ("إيه", ARABIC),
        ("أيوه لو سمحت", ARABIC),
        ("نعم أرسلها", ARABIC),
        ("إيه، أرسلها الله يعافيك", ARABIC),
        ("yes", ENGLISH),
        ("Yeah, go ahead, thanks.", ENGLISH),
        ("Okay, yes.", ENGLISH),
        ("Yes, I'm sure, please do.", ENGLISH),
        ("Yes, that's it.", ENGLISH),
    ],
)
def test_a_yes_after_the_closing_question_ended_is_a_yes(text: str, words: ConsentWords) -> None:
    outcome = _decide(_heard(text, AFTER), words=words)
    assert isinstance(outcome, Yes) and is_confirmed(outcome.confirmed)


def test_the_confirmed_action_is_the_receipts_draft_and_the_turns_words() -> None:
    receipt = _receipt()
    outcome = _decide(_heard("نعم أرسلها", OVER_QUESTION, at=13.0), receipt)
    assert isinstance(outcome, Yes)
    confirmed = outcome.confirmed
    assert (confirmed.action, confirmed.draft_json, confirmed.reply_id) == (
        "open_request",
        DRAFT,
        4,
    )
    assert (confirmed.turn_id, confirmed.words, confirmed.source) == (
        7,
        "نعم أرسلها",
        "speech_to_text",
    )
    assert confirmed.speech_at == OVER_QUESTION  # when the caller began, never the transcript's


@pytest.mark.parametrize(
    ("text", "words"),
    [("نعم", ARABIC), ("إيه", ARABIC), ("أيوه، تمام", ARABIC), ("yeah", ENGLISH)],
)
@pytest.mark.parametrize("question_ended_at", [QUESTION_AT, None])
def test_a_bare_yes_over_the_closing_question_is_asked_again(
    text: str, words: ConsentWords, question_ended_at: float | None
) -> None:
    """Invariant 1: «نعم» over the closing question may be a listening sound."""
    outcome = _decide(_heard(text, OVER_QUESTION), _receipt(question_ended_at), words=words)
    assert outcome == AskAgain()


@pytest.mark.parametrize(
    ("text", "words"),
    [
        ("نعم أرسلها", ARABIC),
        ("إيه أرسله", ARABIC),
        ("إيه وأرسلها", ARABIC),  # the send word after waw, and
        ("ايوه سجلها لو سمحت", ARABIC),
        ("yes, send it", ENGLISH),
        ("yeah go ahead", ENGLISH),
        ("Naam, Ersilha.", ENGLISH),  # Whisper's Latin letters in an English call
    ],
)
@pytest.mark.parametrize("question_ended_at", [QUESTION_AT, None])
def test_a_yes_with_a_send_word_over_the_closing_question_is_a_yes(
    text: str, words: ConsentWords, question_ended_at: float | None
) -> None:
    """The rehearsal's step 6: «نعم أرسلها» over the closing question, once the summary played."""
    outcome = _decide(_heard(text, OVER_QUESTION), _receipt(question_ended_at), words=words)
    assert isinstance(outcome, Yes)


def test_an_eager_yes_begun_before_the_question_ended_is_over_the_question() -> None:
    """Whisper gives no partials: a bare yes begun over the question arrives after it ended,
    and only its `speech_at` tells. Its transcript's time never makes it a yes."""
    eager = _heard("نعم", 11.9, at=QUESTION_AT + 2.0)
    assert _decide(eager) == AskAgain()
    assert isinstance(_decide(_heard("نعم أرسلها", 11.9, at=QUESTION_AT + 2.0)), Yes)


@pytest.mark.parametrize("text", ["نعم", "نعم أرسلها", "إيه", "yes send it"])
@pytest.mark.parametrize("speech_at", [SUMMARY_AT - 3.0, SUMMARY_AT - 0.01, None])
def test_a_yes_begun_over_the_summary_counts_for_nothing(
    text: str, speech_at: float | None
) -> None:
    """Yes words over the summary are ignored; the transcript arriving after the question ended
    changes nothing, and words no turn opened for read as said before anything."""
    words = ENGLISH if text.startswith("yes") else ARABIC
    heard = _heard(text, speech_at, at=QUESTION_AT + 5.0)
    assert _decide(heard, words=words) == AskAgain()


def test_only_a_yes_after_a_new_reading_counts() -> None:
    """A request to hear it again: the read-back is said again, a new receipt; a yes said
    before the new summary ended counts for nothing, one after it is the new reading's."""
    again = _receipt(23.0, summary_at=20.0, reply=9)
    assert _decide(_heard("نعم أرسلها", 15.0, at=21.0), again) == AskAgain()
    assert _decide(_heard("نعم أرسلها", 19.5, at=21.0), again) == AskAgain()
    outcome = _decide(_heard("نعم", 23.5), again)
    assert isinstance(outcome, Yes) and outcome.confirmed.reply_id == 9


@pytest.mark.parametrize("speech_at", [OVER_QUESTION, AFTER])
@pytest.mark.parametrize(
    ("text", "words"),
    [
        ("نعم بس غيّر العنوان", ARABIC),
        ("إيه أرسلها بس خلها عاجلة", ARABIC),
        ("yes but make it urgent", ENGLISH),
        ("yes, send it to the other team", ENGLISH),
    ],
)
def test_a_yes_with_a_change_in_it_is_a_correction(
    text: str, words: ConsentWords, speech_at: float
) -> None:
    outcome = _decide(_heard(text, speech_at), words=words)
    assert outcome == Correction(words=text)


@pytest.mark.parametrize(
    ("text", "words"),
    [
        ("لا", ARABIC),
        ("لا، شكراً", ARABIC),
        ("لا ترسلها", ARABIC),
        ("كلا", ARABIC),
        ("no", ENGLISH),
        ("No thanks.", ENGLISH),
        ("nope, cancel it", ENGLISH),
        ("don't send it", ENGLISH),
    ],
)
@pytest.mark.parametrize("speech_at", [OVER_QUESTION, AFTER])
def test_a_no_is_declined(text: str, words: ConsentWords, speech_at: float) -> None:
    assert _decide(_heard(text, speech_at), words=words) == Declined(words=text)


@pytest.mark.parametrize(
    ("text", "words"),
    [
        ("لا لا نعم", ARABIC),  # a no and a yes: unclear
        ("I'm not sure.", ENGLISH),
        ("أرسلها", ARABIC),  # a send word alone: the lists' (test_yes_rule_send_alone.py)
        ("send it", ENGLISH),
        ("تمام", ARABIC),  # a listening sound, never a decision
        ("okay", ENGLISH),
        ("لو سمحت", ARABIC),
        ("اممم", ARABIC),  # ummm, a hesitation, as Whisper writes it (plan 007's a13)
        ("اه... امم", ARABIC),
        ("نعم؟", ARABIC),  # na'am asked back: pardon?
        ("Yes?", ENGLISH),
        ("...", ENGLISH),
        ("", ENGLISH),
    ],
)
def test_anything_unclear_is_asked_again(text: str, words: ConsentWords) -> None:
    assert _decide(_heard(text, AFTER), words=words) == AskAgain()


def test_nothing_heard_is_asked_again() -> None:
    assert _decide(None) == AskAgain()


def _forged_heard() -> list[object]:
    made = _heard("نعم أرسلها", AFTER)
    rewritten = _heard("لا", AFTER)
    rewritten.__dict__["text"] = "نعم أرسلها"
    return [
        copy.copy(made),
        copy.deepcopy(made),
        pickle.loads(pickle.dumps(made)),  # noqa: S301 (its own)
        rewritten,
        SimpleNamespace(**made.model_dump()),
        made.model_dump(),  # a tool's arguments, shaped as heard words
    ]


@pytest.mark.parametrize("forged", _forged_heard())
def test_heard_words_not_built_by_voice_count_for_nothing(forged: object) -> None:
    assert _decide(cast(HeardWords, forged), env="test") == AskAgain()


def _forged_receipts() -> list[object]:
    made = _receipt()
    return [
        copy.copy(made),
        pickle.loads(pickle.dumps(made)),  # noqa: S301 (its own)
        SimpleNamespace(**made.model_dump()),
        made.model_dump(),
    ]


@pytest.mark.parametrize("forged", _forged_receipts())
def test_a_receipt_not_built_by_voice_counts_for_nothing(forged: object) -> None:
    assert _decide(_heard("نعم أرسلها", AFTER), forged, env="test") == AskAgain()


@pytest.mark.parametrize("env", ["dev", "staging", "prod"])
def test_typed_words_count_only_in_a_test(env: Environment) -> None:
    typed = _heard("نعم أرسلها", AFTER, source="typed")
    assert _decide(typed, env=env) == AskAgain()
    assert isinstance(_decide(typed, env="test"), Yes)


def test_an_actions_own_send_words_and_the_settings_yes_words_count() -> None:
    words = consent_words("ar", added_yes=["تمام"], action_send=["افتحها"])
    assert isinstance(_decide(_heard("نعم افتحها", OVER_QUESTION), words=words), Yes)
    assert _decide(_heard("نعم افتحها", OVER_QUESTION)) == Correction(words="نعم افتحها")
    assert isinstance(_decide(_heard("تمام", AFTER), words=words), Yes)
    assert _decide(_heard("تمام", AFTER)) == AskAgain()


def test_deciding_changes_nothing() -> None:
    heard, receipt = _heard("نعم أرسلها", AFTER), _receipt()
    first, second = _decide(heard, receipt), _decide(heard, receipt)
    assert isinstance(first, Yes) and isinstance(second, Yes)
    assert first.confirmed is not second.confirmed
    assert is_confirmed(first.confirmed) and is_confirmed(second.confirmed)

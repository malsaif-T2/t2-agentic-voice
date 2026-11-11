"""The yes rule's rails with a turn heard in another language than the read-back's
(domain/yes_words.py's `rails_for`, domain/yes_rule.py's `judged`; plan 007's Block H;
docs/SECURITY.md, invariant 1). With each turn's language from a classifier, an English answer
over an Arabic read-back is routine, and the read-back's own lists hold none of its no words or
change markers: so whenever the heard words' language is not the read-back's, `judged`'s rails
read those of every language the agent speaks, while the lists that place a yes stay the
read-back's. Adversarial (GP-08), a fake model answering `yes` (and every other word): "yes, but
change the date" heard as English over an Arabic read-back, and its Arabic twin heard as Arabic
over an English one, are each a correction; "no, send it" heard as English over an Arabic
read-back is never a yes; and with the languages the same, the rails are the read-back's own,
so every answer of today's tests stands. Every word and time here is made up for the test."""

from __future__ import annotations

from typing import Any

import pytest
from t2_agentic_voice.core.settings.words import LanguageCode
from t2_agentic_voice.core.yes_inputs import HEARD_WORDS_SEAL, HeardWords
from t2_agentic_voice.domain.yes_rule import (
    AskAgain,
    Correction,
    Declined,
    ModelWord,
    SaidLines,
    Yes,
    YesOutcome,
    decide,
    judged,
)
from t2_agentic_voice.domain.yes_words import ConsentWords, consent_words, rails_for
from t2_agentic_voice.voice.session.read_back import played_receipt

ARABIC = consent_words("ar")
ENGLISH = consent_words("en")
SPOKEN = ("ar", "en")
SUMMARY_AT, QUESTION_AT, AFTER = 10.0, 12.0, 12.5
# Nothing the agent said is heard back: the speech began once every line and its tail ended.
SAID = SaidLines(read_back=(), asked_again=(), over_read_back=False, over_asked_again=False)
WORDS: tuple[ModelWord, ...] = ("yes", "send", "no", "change", "unclear", None)
# "yes, but change the date" in English, and in Saudi Arabic: na'am (noon, ain, meem), bas
# (beh, seen), ghayyir with its shadda (ghain, yeh, shadda, reh), al-maw'id (alef, lam, meem,
# waw, ain, dal).
CHANGE_EN = "yes, but change the date"
CHANGE_AR = "نعم بس غيّر الموعد"
# Today's judged lines in Saudi Arabic (testing/action_judged.py's): "eeh bas khalliha 'aajla",
# yes but make it urgent; "sah", right.
URGENT_AR = "ايه بس خلها عاجلة"
RIGHT_AR = "صح"
NO_SEND_EN = "no, send it"


def _heard(text: str, language: str | None) -> HeardWords:
    values = {
        "turn_id": 7,
        "text": text,
        "language": language,
        "at": AFTER + 1.0,
        "speech_at": AFTER,
        "source": "speech_to_text",
    }
    return HeardWords.model_validate(values, context=HEARD_WORDS_SEAL)


def _receipt() -> Any:
    return played_receipt(
        action="open_request",
        draft_json='{"summary": "made up"}',
        reply_id=4,
        summary_played_at=SUMMARY_AT,
        question_ended_at=QUESTION_AT,
    )


def _judged(
    word: ModelWord, heard: HeardWords, words: ConsentWords, read_back: LanguageCode
) -> YesOutcome:
    receipt = _receipt()
    rails = rails_for(words, heard=heard.language, read_back=read_back, spoken=SPOKEN)
    return judged(
        word, heard, receipt, current=receipt, words=words, env="prod", said=SAID, rails=rails
    )


@pytest.mark.parametrize("word", ["yes", "send", "change"])
def test_an_english_yes_with_a_change_over_an_arabic_read_back_is_a_correction(
    word: ModelWord,
) -> None:
    heard = _heard(CHANGE_EN, "en")
    assert isinstance(decide(heard, _receipt(), words=ARABIC, env="prod"), Correction)
    assert _judged(word, heard, ARABIC, "ar") == Correction(words=CHANGE_EN)


def test_the_read_backs_own_rails_alone_would_have_confirmed_it() -> None:
    """Why the rails read every language: the Arabic lists hold neither "but" nor "change"."""
    heard, receipt = _heard(CHANGE_EN, "en"), _receipt()
    alone = judged("yes", heard, receipt, current=receipt, words=ARABIC, env="prod", said=SAID)
    assert isinstance(alone, Yes)


@pytest.mark.parametrize("word", ["yes", "send", "change"])
def test_an_arabic_yes_with_a_change_over_an_english_read_back_is_a_correction(
    word: ModelWord,
) -> None:
    heard = _heard(CHANGE_AR, "ar")
    assert isinstance(decide(heard, _receipt(), words=ENGLISH, env="prod"), Correction)
    assert _judged(word, heard, ENGLISH, "en") == Correction(words=CHANGE_AR)


@pytest.mark.parametrize("word", WORDS)
def test_an_english_no_send_it_over_an_arabic_read_back_is_never_a_yes(word: ModelWord) -> None:
    found = _judged(word, _heard(NO_SEND_EN, "en"), ARABIC, "ar")
    assert not isinstance(found, Yes)
    if word in ("yes", "send", "unclear"):
        assert found == AskAgain()
    if word in ("no", None):  # a no word declines, as the model's no does
        assert found == Declined(words=NO_SEND_EN)


def test_with_the_languages_the_same_the_rails_are_the_read_backs_own() -> None:
    same: tuple[tuple[ConsentWords, LanguageCode, str], ...] = (
        (ARABIC, "ar", "ar"),
        (ENGLISH, "en", "en"),
        (ARABIC, "ar", "Arabic"),
    )
    for words, code, named in same:
        assert rails_for(words, heard=named, read_back=code, spoken=SPOKEN) is words


def test_in_another_language_only_the_no_words_and_change_markers_grow() -> None:
    other: tuple[tuple[ConsentWords, LanguageCode, str | None], ...] = (
        (ARABIC, "ar", "en"),
        (ENGLISH, "en", "ar"),
        (ARABIC, "ar", None),
    )
    for words, code, heard in other:
        rails = rails_for(words, heard=heard, read_back=code, spoken=SPOKEN)
        assert (rails.yes, rails.send, rails.fillers) == (words.yes, words.send, words.fillers)
        assert set(rails.no) == set(ARABIC.no) | set(ENGLISH.no)
        assert set(rails.change) == set(ARABIC.change) | set(ENGLISH.change)


def test_an_agent_of_one_language_reads_its_own_rails() -> None:
    rails = rails_for(ENGLISH, heard="ar", read_back="en", spoken=("en",))
    assert (rails.no, rails.change) == (ENGLISH.no, ENGLISH.change)


@pytest.mark.parametrize("word", WORDS)
@pytest.mark.parametrize(
    ("text", "language", "words", "code"),
    [
        ("yes send it", "en", ENGLISH, "en"),
        ("yes, but make it urgent", "en", ENGLISH, "en"),
        ("sure thing", "en", ENGLISH, "en"),
        ("go for it?", "en", ENGLISH, "en"),
        (URGENT_AR, "ar", ARABIC, "ar"),
        (RIGHT_AR, "ar", ARABIC, "ar"),
    ],
)
def test_today_s_answers_stand_with_the_languages_the_same(
    word: ModelWord, text: str, language: str, words: ConsentWords, code: LanguageCode
) -> None:
    heard, receipt = _heard(text, language), _receipt()
    today = judged(word, heard, receipt, current=receipt, words=words, env="prod", said=SAID)
    assert _judged(word, heard, words, code) == today

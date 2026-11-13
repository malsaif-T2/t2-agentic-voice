"""The agent's echo of a reply that said the caller's words back (domain/interruptions.py, steps 2
and 3 as plan 005's reviews changed them): a reply can hold any word the caller said, so a stop
or wait word heard beside other words, each exactly a word or listed phrase of the clauses that
played and every word the agent's own, goes on, and so does a repeat request over a reply that
holds any repeat word, also after waw (and), whatever the spelling heard; stop or wait words
alone, or one the reply holds only within an edit, still stop, and a repeat request over a reply
that holds no repeat word still repeats. The spellings only
Whisper writes for the stop word stop as a whole short utterance, never inside a sentence.
Its tests are written on texts made for them, never an item's."""

from __future__ import annotations

import pytest
from t2_agentic_voice.core.settings.words import LanguageCode
from t2_agentic_voice.domain.interruption_words import NOISY_SPELLINGS
from t2_agentic_voice.domain.words import PRESET_WORDS, WORD_KINDS

from tests.t2_agentic_voice.domain.rule_support import NEW_WORDS, REPEAT, STOP, judged, went_on

# A reply that holds none of the words below, in each language.
OTHER: dict[LanguageCode, str] = {
    "en": "The archive opens from the main menu.",
    "ar": "يفتح الأرشيف من القائمة الرئيسية.",
}


@pytest.mark.parametrize(
    ("played", "text", "language"),
    [
        ("قلت: توقف عن الطباعة الآن", "توقف عن الطباعة", "ar"),
        ("سمعتك تقول لحظة واحدة بس", "لحظه واحده", "ar"),
        ("You said: wait a moment about the invoice.", "wait a moment about the invoice", "en"),
        ("I heard: please hold on to the receipt.", "hold on to the receipt", "en"),
    ],
)
def test_the_echo_of_a_said_back_stop_or_wait_word_goes_on(
    played: str, text: str, language: LanguageCode
) -> None:
    assert judged(text, language, played=(played,)) == went_on("own_words")
    assert judged(text, language, played=(OTHER[language], played)) == went_on("own_words")
    assert judged(text, language) == STOP  # nothing played
    assert judged(text, language, played=(OTHER[language],)) == STOP


@pytest.mark.parametrize(
    ("language", "word"),
    [(code, word) for code, words in PRESET_WORDS.items() for word in (*words.stop, *words.wait)],
)
def test_stop_or_wait_words_alone_stop_though_the_reply_said_them(
    language: LanguageCode, word: str
) -> None:
    """Each said twice, so nothing else is heard."""
    played = f"You said {word} {word}." if language == "en" else f"قلت {word} {word}"
    assert judged(f"{word} {word}", language, played=(played,)) == STOP


def test_a_stop_word_the_reply_holds_only_within_an_edit_still_stops() -> None:
    """Wagif (stop) is one edit from waqt (time), and "stop" from "stops": the agent's own words
    would take each, the echo never does. A stop word said back beside a word the reply does not
    hold stops too."""
    played = ("عندي وقت الحين للطباعة",)
    assert judged("وقف الحين", "ar", played=played) == STOP
    assert judged("وقف وقف", "ar", played=played) == STOP
    printer = ("The printer stops the printing.",)
    assert judged("stop the printing", played=printer) == STOP
    invoice = ("You said: wait a moment about the invoice.",)
    assert judged("wait a moment about the bill", played=invoice) == STOP


@pytest.mark.parametrize(
    ("played", "text", "language"),
    [
        ("سمعتك تقول: ممكن تعيدها لو سمحت", "ممكن تعيدها لو سمحت", "ar"),
        ("You said: could you repeat it, please.", "could you repeat it, please", "en"),
        ("You said: come again.", "Come again?", "en"),
        # a'eed after waw ("and I say again"), as Whisper writes it with the waw apart or dropped
        ("اسأل وأعيد لك الجواب", "أعيد", "ar"),
    ],
)
def test_the_echo_of_a_said_back_repeat_request_goes_on(
    played: str, text: str, language: LanguageCode
) -> None:
    assert judged(text, language, played=(played,)) == went_on("own_words")
    assert judged(text, language, played=(OTHER[language],)) == REPEAT
    assert judged(text, language) == REPEAT  # nothing played


@pytest.mark.parametrize(
    ("played", "text", "language"),
    [
        ("قلت: ممكن تعيدها", "ممكن تعيدها لو سمحت", "ar"),  # polite words the reply lacks
        ("قلت: تعيده من فضلك", "اعد لو سمحت", "ar"),  # spelled otherwise than the reply's
        ("You said: repeat it now.", "come again, please", "en"),
    ],
)
def test_a_repeat_request_over_a_reply_holding_any_repeat_word_goes_on(
    played: str, text: str, language: LanguageCode
) -> None:
    """Whisper may spell the repeat word of the agent's echo otherwise than the reply did, and
    the repeat would say it again and again (plan 005's session review): a repeat request over
    a reply that holds any repeat word is the agent's own. A sentence is left to the steps
    after, as any other."""
    assert judged(text, language, played=(played,)) == went_on("own_words")
    assert judged(text, language, played=(OTHER[language], played)) == went_on("own_words")
    assert judged(text, language, played=(OTHER[language],)) == REPEAT
    assert judged("تعيده الملف الثاني بكره", "ar", played=(played,)) == NEW_WORDS


def _language(spelling: str) -> LanguageCode:
    return "en" if spelling.isascii() else "ar"


@pytest.mark.parametrize("spelling", sorted(NOISY_SPELLINGS))
def test_a_spelling_only_whisper_writes_stops_only_as_a_whole_short_utterance(
    spelling: str,
) -> None:
    language = _language(spelling)
    polite = "please" if language == "en" else "لو سمحت"
    assert judged(spelling, language, speech_s=0.7) == STOP
    assert judged(f"{spelling}, {polite}", language, speech_s=0.7) == STOP
    sentence = f"I think {spelling} was here" if language == "en" else f"اظن {spelling} كان هنا"
    assert judged(sentence, language) == NEW_WORDS
    lists = [getattr(words, kind) for words in PRESET_WORDS.values() for kind in WORD_KINDS]
    assert all(spelling not in words for words in lists)  # in no preset's list

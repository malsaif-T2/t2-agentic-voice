"""A turn said while the agent was silent, read whole (domain/interruptions.py's `whole_command`,
plan 005's Track B review): stop or pause words, or a spelling only Whisper writes for the stop
word, with only polite words and listening sounds beside them, ask it to stop; repeat words
with only those beside them ask for the last reply again; anything else asks nothing, a
sentence holding one of the words included. A lone word is built from the lists, so no test
writes an item's text."""

from __future__ import annotations

import pytest
from t2_agentic_voice import Phrases
from t2_agentic_voice.core.settings.words import LanguageCode
from t2_agentic_voice.domain.interruption_words import NOISY_SPELLINGS, NOISY_WORDS
from t2_agentic_voice.domain.interruptions import whole_command
from t2_agentic_voice.domain.words import PRESET_WORDS

# A polite word and a listening sound of each language, which may stand beside a command.
POLITE: dict[LanguageCode, str] = {"en": "please", "ar": "لو سمحت"}
LISTENING: dict[LanguageCode, str] = {"en": "okay", "ar": "طيب"}


def _read(text: str, language: LanguageCode) -> str | None:
    return whole_command(text, words=PRESET_WORDS[language])


@pytest.mark.parametrize(
    ("language", "word"),
    [(code, word) for code, words in PRESET_WORDS.items() for word in (*words.stop, *words.wait)],
)
def test_stop_or_wait_words_said_whole_ask_to_stop(language: LanguageCode, word: str) -> None:
    assert _read(word, language) == "stop"
    assert _read(f"{word}؟", language) == "stop"  # a mark Whisper wrote changes nothing
    assert _read(f"{LISTENING[language]} {word} {POLITE[language]}", language) == "stop"
    assert _read(f"{word} {word}", language) == "stop"


@pytest.mark.parametrize(
    ("language", "word"),
    [(code, word) for code, words in PRESET_WORDS.items() for word in words.repeat],
)
def test_repeat_words_said_whole_ask_for_the_last_reply(language: LanguageCode, word: str) -> None:
    assert _read(word, language) == "repeat"
    assert _read(f"{word}?", language) == "repeat"
    assert _read(f"{POLITE[language]}, {word}", language) == "repeat"


def _language(spelling: str) -> LanguageCode:
    return "en" if spelling.isascii() else "ar"


@pytest.mark.parametrize("spelling", sorted(NOISY_SPELLINGS))
def test_a_spelling_only_whisper_writes_asks_to_stop_only_as_a_short_whole(spelling: str) -> None:
    language = _language(spelling)
    polite, listening = POLITE[language], LISTENING[language]
    assert _read(spelling, language) == "stop"
    assert _read(f"{spelling}, {polite}", language) == "stop"
    longer = f"{listening} {spelling} {polite} {listening} {polite}"
    assert len(longer.split()) > NOISY_WORDS and _read(longer, language) is None
    sentence = f"I think {spelling} was here" if language == "en" else f"اظن {spelling} كان هنا"
    assert _read(sentence, language) is None


@pytest.mark.parametrize(
    ("text", "language"),
    [
        ("الجهاز توقف عن العمل امس", "ar"),  # a stop word in a sentence
        ("the bus will stop at the gate", "en"),
        ("انتظر الرد من الدعم الفني", "ar"),
        ("I need to read my mail", "en"),  # a repeat word in a sentence
        ("عيد الفطر قريب جدا", "ar"),
        ("طيب اها", "ar"),  # listening sounds alone
        ("okay, please", "en"),
        ("some made up words", "en"),
        ("", "en"),
        ("♪", "ar"),
    ],
)
def test_anything_else_asks_nothing(text: str, language: LanguageCode) -> None:
    assert _read(text, language) is None


def test_a_stop_word_beside_a_repeat_word_or_a_no_word_asks_nothing() -> None:
    stop, repeat, no = PRESET_WORDS["en"].stop[0], PRESET_WORDS["en"].repeat[0], "no"
    assert _read(f"{stop} {repeat}", "en") is None
    assert _read(f"{no} {stop}", "en") is None


def test_a_teams_words_are_read_too() -> None:
    words = Phrases.defaults().extend(stop={"en": ["made-up halt"]}).words("en")
    assert whole_command("made-up halt, please", words=words) == "stop"
    assert whole_command("made-up halt", words=PRESET_WORDS["en"]) is None

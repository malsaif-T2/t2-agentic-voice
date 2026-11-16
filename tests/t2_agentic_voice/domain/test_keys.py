"""Key combinations said as their keys, and capitals spelled (domain/text/keys.py): the owner's
forms of 2026-11-16, "Control Shift R" and «كنترول شفت آر», "I P" and «آي بي», "O T P" and «أو
تي بي». Every text here is written for the test."""

from __future__ import annotations

import pytest
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.domain.text.keys import speak_keys, spell_letters
from t2_agentic_voice.voice.session.open_reply import speech_of

from tests.t2_agentic_voice.session_fakes import FakeSessionIO


def test_a_key_combination_is_said_as_its_keys_with_no_plus() -> None:
    assert speak_keys("Press Ctrl + Shift + R.", language="en") == "Press Control Shift R."
    arabic = speak_keys("اضغط Ctrl + Shift + R للتحديث", language="ar-SA")
    assert arabic == "اضغط كنترول شفت آر للتحديث"


@pytest.mark.parametrize(
    ("text", "english", "arabic"),
    [
        ("ctrl+alt+del", "Control Alt Delete", "كنترول ألت ديليت"),
        ("Alt + F4", "Alt F four", "ألت إف أربعة"),
        ("Win+E", "Windows E", "ويندوز إي"),
        ("Shift + Tab", "Shift Tab", "شفت تاب"),
        ("Ctrl + 1", "Control one", "كنترول واحد"),
    ],
)
def test_each_key_is_said_by_its_name(text: str, english: str, arabic: str) -> None:
    assert speak_keys(text, language="en") == english
    assert speak_keys(text, language="ar") == arabic


@pytest.mark.parametrize(
    "text", ["1 + 2 = 3", "C++ and A + B", "Press Ctrl.", "Ctrl+Shiftless", "x+Ctrl"]
)
def test_what_is_no_combination_is_left_as_written(text: str) -> None:
    assert speak_keys(text, language="en") == text


def test_capitals_are_spelled_letter_by_letter_for_a_pronunciation_map() -> None:
    assert spell_letters("IP", language="en") == "I P"
    assert spell_letters("OTP", language="en") == "O T P"
    assert spell_letters("IP", language="ar-SA") == "آي بي"
    assert spell_letters("OTP", language="ar") == "أو تي بي"
    assert spell_letters("ctrl", language="en") == "C T R L"


@pytest.mark.parametrize("letters", ["", "IP4", "O.T.P", "أب"])
def test_only_latin_letters_are_spelled(letters: str) -> None:
    with pytest.raises(ValueError, match="Latin letters only"):
        spell_letters(letters, language="en")


def test_a_clause_s_keys_are_said_as_written_by_default(settings: VoiceSettings) -> None:
    """The characterization of `tts.spoken_key_combinations`' default: off, a clause keeps
    its plus signs."""
    assert settings.tts.spoken_key_combinations is False
    ((said, _),) = speech_of(FakeSessionIO(settings).setup, "Press Ctrl + Shift + R.", "en")
    assert said == "Press Ctrl + Shift + R."


def test_with_the_setting_a_clause_s_keys_are_said_and_captioned_as_written(
    settings: VoiceSettings,
) -> None:
    keyed = settings.model_copy(
        update={"tts": settings.tts.model_copy(update={"spoken_key_combinations": True})}
    )
    io = FakeSessionIO(keyed)
    ((said, caption),) = speech_of(io.setup, "Press Ctrl + Shift + R.", "en")
    assert (said, caption) == ("Press Control Shift R.", "Press Ctrl + Shift + R.")
    ((arabic, _),) = speech_of(io.setup, "اضغط Ctrl + F5", "ar-SA")
    assert arabic == "اضغط كنترول إف خمسة"

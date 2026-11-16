"""When a turn moves the call to the agent's other language (domain/language_switch.py): a question
or request heard in the other language moves it, both ways; a short reply, a turn of one word, a
third language, the language already named, or a turn whose words in the call's language are a
short reply never does; Whisper's names are read exactly (TD-011); and the rule's own checks."""

from __future__ import annotations

import pytest
from t2_agentic_voice.core.settings.words import LanguageCode
from t2_agentic_voice.domain.language_switch import (
    FEWEST_WORDS,
    SHORT_REPLIES,
    DetectRule,
    short_reply,
    switch_to,
)
from t2_agentic_voice.domain.words import rule_form

CODES: tuple[LanguageCode, ...] = ("ar", "en")
# How do I book a flight to Jeddah? (kaif ahjiz rihla ila jidda): Arabic letters.
ARABIC_QUESTION = "كيف احجز رحلة الى جدة؟"
# What Whisper told Arabic writes for an English question: fluent Arabic, wrongly.
TRANSLATED = "كيف اغير موعد رحلتي"
EH, TAMAM, TAYYIB = "ايه", "تمام", "طيب"
SHUKRAN = "شكراً"  # shukran, with its tanween, as Whisper writes it


def test_an_english_question_in_an_arabic_call_moves_it_to_english() -> None:
    moved = switch_to(
        "ar",
        "English",
        codes=CODES,
        named_text=TRANSLATED,
        detected_text="How do I change my flight to Riyadh?",
    )
    assert moved == "en"


def test_an_arabic_request_in_an_english_call_moves_it_to_arabic() -> None:
    moved = switch_to(
        "en", "Arabic", codes=CODES, named_text="Kaif ahjiz rihla?", detected_text=ARABIC_QUESTION
    )
    assert moved == "ar"


@pytest.mark.parametrize(
    "said",
    [
        "Yes.",
        "Okay, thanks.",
        "Yes please",
        "Thank you so much.",
        "No, thanks.",
        "Uh huh.",
        "Tamam, khalas.",
        f"{EH} {TAMAM}",
        f"{TAYYIB} {SHUKRAN}",
        "اوكي ثانكس",  # okay, thanks: Arabic letters
    ],
)
def test_a_short_reply_never_moves_the_call(said: str) -> None:
    assert short_reply(said)
    assert switch_to("ar", "English", codes=CODES, named_text=None, detected_text=said) is None
    assert switch_to("en", "Arabic", codes=CODES, named_text=None, detected_text=said) is None


def test_a_turn_of_one_word_never_moves_the_call() -> None:
    assert FEWEST_WORDS == 2
    assert switch_to("ar", "English", codes=CODES, named_text=None, detected_text="Riyadh?") is None


def test_words_in_the_calls_language_that_are_a_short_reply_keep_it() -> None:
    """Told Arabic, «تمام طيب» is a reply, whatever the detecting request made of it."""
    named = f"{TAMAM} {TAYYIB}"
    found = "Tamam, I think that is good."
    assert switch_to("ar", "English", codes=CODES, named_text=named, detected_text=found) is None


@pytest.mark.parametrize("heard", ["Armenian", "Spanish", "Norwegian Nynorsk", None, ""])
def test_a_third_language_or_none_is_no_switch(heard: str | None) -> None:
    question = "How do I change my flight to Riyadh?"
    assert switch_to("ar", heard, codes=CODES, named_text=None, detected_text=question) is None


def test_the_language_already_named_moves_nothing() -> None:
    question = "How do I change my flight to Riyadh?"
    assert switch_to("en", "English", codes=CODES, named_text=None, detected_text=question) is None
    assert switch_to("en", "en", codes=CODES, named_text=None, detected_text=question) is None


def test_a_language_the_agent_does_not_speak_is_no_switch() -> None:
    question = "How do I change my flight to Riyadh?"
    moved = switch_to("ar", "English", codes=("ar",), named_text=None, detected_text=question)
    assert moved is None


def test_a_failed_request_in_the_calls_language_still_lets_a_question_move_it() -> None:
    question = "Which flights go to Dubai tomorrow?"
    assert switch_to("ar", "English", codes=CODES, named_text=None, detected_text=question) == "en"


def test_the_short_replies_are_in_the_rules_form() -> None:
    assert all(rule_form(each) == each for each in SHORT_REPLIES)
    assert {"okay", "thank you", rule_form(EH), rule_form(TAMAM), rule_form(TAYYIB)} <= set(
        SHORT_REPLIES
    )


def test_the_detect_rule_reads_voiced_speech_and_refuses_a_bad_shape() -> None:
    rule = DetectRule(from_s=1.2, codes=CODES)
    assert rule.detects(1.2) and rule.detects(3.0)
    assert not rule.detects(1.19) and not rule.detects(None)
    with pytest.raises(ValueError, match="above 0"):
        DetectRule(from_s=0, codes=CODES)
    with pytest.raises(ValueError, match="two of the agent's languages"):
        DetectRule(from_s=1.2, codes=("ar", "ar"))

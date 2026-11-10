"""The words the yes rule reads (domain/yes_words.py): each language preset's yes, send, no and
filler words, in the rule's form, kept apart from the interruption rule's five kinds, with the
settings' and the action's words added."""

from __future__ import annotations

import pytest
from t2_agentic_voice.core.settings.words import LanguageCode
from t2_agentic_voice.domain import yes_words
from t2_agentic_voice.domain.words import PRESET_WORDS, WORD_KINDS, rule_form
from t2_agentic_voice.domain.yes_words import PRESET_CONSENT, ConsentWords, consent_words

CODES: tuple[LanguageCode, ...] = ("ar", "en")
KINDS = ("yes", "send", "no", "fillers")
# The lists as the module writes them, before `ConsentWords` brings any word to the rule's form.
WRITTEN = {
    "ar": (
        yes_words._ARABIC_YES,
        yes_words._ARABIC_SEND,
        yes_words._ARABIC_NO,
        yes_words._ARABIC_FILLERS,
    ),
    "en": (
        yes_words._ENGLISH_YES,
        yes_words._ENGLISH_SEND,
        yes_words._ENGLISH_NO,
        yes_words._ENGLISH_FILLERS,
    ),
}


@pytest.mark.parametrize("code", CODES)
def test_each_presets_words_are_written_in_the_rules_form_each_once(code: LanguageCode) -> None:
    for words in WRITTEN[code]:
        assert all(word == rule_form(word) and word for word in words)
        assert len(set(words)) == len(words)


@pytest.mark.parametrize("code", CODES)
def test_no_word_is_on_two_of_the_yes_rules_lists(code: LanguageCode) -> None:
    preset = PRESET_CONSENT[code]
    lists = [set(getattr(preset, kind)) for kind in KINDS]
    for at, first in enumerate(lists):
        for second in lists[at + 1 :]:
            assert first.isdisjoint(second)


@pytest.mark.parametrize("code", CODES)
def test_the_yes_and_send_words_stay_out_of_the_interruption_rules_lists(
    code: LanguageCode,
) -> None:
    """D-080: the interruption rule's five kinds stay as they were measured; the no words and
    the fillers start from its no words and listening sounds, read, never changed."""
    preset = PRESET_CONSENT[code]
    interruption = {word for kind in WORD_KINDS for word in getattr(PRESET_WORDS[code], kind)}
    assert interruption.isdisjoint(preset.yes) and interruption.isdisjoint(preset.send)
    assert set(PRESET_WORDS[code].no) <= set(preset.no)
    assert set(PRESET_WORDS[code].backchannel) <= set(preset.fillers)


def test_the_owners_yes_words_and_the_rehearsals_send_word_are_listed() -> None:
    """Plan 007's ruling on the four yes words; «أرسلها» is the rehearsal's step 6."""
    arabic, english = PRESET_CONSENT["ar"], PRESET_CONSENT["en"]
    assert {rule_form(word) for word in ("نعم", "إيه", "أيوه")} <= set(arabic.yes)
    assert "yeah" in english.yes and "yes" in english.yes
    assert rule_form("أرسلها") in arabic.send and "send it" in english.send
    assert rule_form("لا") in arabic.no and "no" in english.no


def test_the_settings_and_the_actions_words_are_added_in_the_rules_form() -> None:
    words = consent_words(
        "ar", added_yes=["أكيــد", "تمام"], added_send=["ابعثها"], action_send=["افتَحها"]
    )
    preset = PRESET_CONSENT["ar"]
    assert words.yes[: len(preset.yes)] == preset.yes
    assert words.yes[len(preset.yes) :] == (rule_form("تمام"),)  # «أكيد» was there already
    assert words.send[len(preset.send) :] == (rule_form("ابعثها"), rule_form("افتحها"))
    assert (words.no, words.fillers) == (preset.no, preset.fillers)
    assert consent_words("en") == PRESET_CONSENT["en"]


def test_a_word_that_says_nothing_in_the_rules_form_is_dropped() -> None:
    words = ConsentWords(yes=("Yes!", "‏", " "), send=("Send  it",), no=(), fillers=())
    assert words.yes == ("yes",) and words.send == ("send it",)

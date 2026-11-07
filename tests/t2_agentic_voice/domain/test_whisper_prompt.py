"""The Whisper prompt of a call (domain/whisper_prompt.py; Q17): the vocabulary's terms, then the
command words of the call's language as they should be written, each once, trimmed by that order
to 224 bytes of UTF-8; each command word one the interruption rule reads; and no mishearing the
presets keep for what Whisper writes able to reach a prompt."""

from __future__ import annotations

import pytest
from t2_agentic_voice.core.settings.words import LanguageCode
from t2_agentic_voice.domain.interruption_words import NOISY_SOUNDS, NOISY_SPELLINGS
from t2_agentic_voice.domain.whisper_prompt import COMMAND_SPELLINGS, PROMPT_BYTES
from t2_agentic_voice.domain.words import PRESET_WORDS, WORD_KINDS, rule_form
from t2_agentic_voice.languages import WhisperPrompt, whisper_prompt

CODES: tuple[LanguageCode, ...] = ("ar", "en")
# The presets' entries marked "heard as": what Whisper wrote for a command word, which the rule
# reads, and which a prompt must never teach Whisper to write.
HEARD_AS = {
    "ar": ("ريت", "ريد", "كامل", "تامام", "تاما"),
    "en": ("stopp", "wagif", "waagif", "lahza", "lahzah", "lhzah", "reid", "rit", "heit", "read"),
}


def test_a_prompt_holds_the_terms_then_the_command_words_of_its_language() -> None:
    english = whisper_prompt(["Outlook", "PDF", "Outlook"], "en")
    assert (
        english.text.startswith("Outlook, PDF, stop, wait, ") and english.text.count("Outlook") == 1
    )
    assert english.text.split(", ")[2:] == list(COMMAND_SPELLINGS["en"])
    assert (english.kept, english.of) == (2 + len(COMMAND_SPELLINGS["en"]),) * 2
    arabic = whisper_prompt(["Outlook"], "ar")
    assert arabic.text == ", ".join(["Outlook", *COMMAND_SPELLINGS["ar"]])
    assert "stop" not in arabic.text and isinstance(arabic, WhisperPrompt)


def test_a_prompt_is_trimmed_by_its_order_within_whispers_limit() -> None:
    """The first word that does not fit and every one after it are left out."""
    terms = [f"term{n:03}" for n in range(60)]
    found = whisper_prompt(terms, "en")
    kept = found.text.split(", ")
    assert kept == terms[: len(kept)] and found.of == 60 + len(COMMAND_SPELLINGS["en"])
    assert len(found.text.encode("utf-8")) <= PROMPT_BYTES == 224
    assert len(", ".join(terms[: len(kept) + 1]).encode("utf-8")) > PROMPT_BYTES
    assert whisper_prompt(["ب" * 112], "ar").kept == 1  # 224 bytes: it fits, and nothing else
    assert whisper_prompt(["ب" * 113], "ar").text == ""  # 226 bytes: none


@pytest.mark.parametrize("code", CODES)
def test_each_command_word_is_one_the_rule_reads_as_it_should_be_written(
    code: LanguageCode,
) -> None:
    words = PRESET_WORDS[code]
    commands = {rule_form(w) for kind in ("stop", "wait", "repeat") for w in getattr(words, kind)}
    for spelling in COMMAND_SPELLINGS[code]:
        assert rule_form(spelling) in commands, spelling
    # Written as a transcript writes them: hamza and teh marbuta where the rule's form drops them.
    if code == "ar":
        assert "أوقف" in COMMAND_SPELLINGS["ar"]  # oqif, not its bare alef
        assert "لحظة" in COMMAND_SPELLINGS["ar"]  # lahza, not its heh


@pytest.mark.parametrize("code", CODES)
def test_no_mishearing_of_the_presets_lists_can_reach_a_prompt(code: LanguageCode) -> None:
    """With no term, every command word fits: whatever reaches a prompt is one of the proper
    spellings, and no entry of the presets' lists, nor of the stop word's spellings only Whisper
    writes, reaches it unless it is one of them."""
    words = whisper_prompt([], code).text.split(", ")
    assert words == list(COMMAND_SPELLINGS[code])
    proper = {rule_form(w) for w in COMMAND_SPELLINGS[code]}
    listed = [w for kind in WORD_KINDS for w in getattr(PRESET_WORDS[code], kind)]
    for entry in [*listed, *NOISY_SPELLINGS, *NOISY_SOUNDS]:
        if rule_form(entry) not in proper:
            assert entry not in words and rule_form(entry) not in map(rule_form, words), entry
    for heard in (*HEARD_AS[code], *NOISY_SPELLINGS, *NOISY_SOUNDS):
        assert heard not in words
    assert "وكيف" not in words and "وغف" not in words  # wakaif, wughf

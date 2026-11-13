"""The words the interruption rule reads (domain/words.py): each language preset reaches its own
lists, the agent's `phrases` start from the presets' and a team extends them, each kind by
language code, after the words already there and none twice, read-only; one language's lists
come whole; and what cannot be taken is a ConfigurationError naming the kind, or for the
declaration the field, never a word (plan 005). The presets' lists are in the
rule's form, each word once and of one kind, in its language's script; and no preset's fixed
phrase holds a word of its stop, wait, repeat or listening list, nor makes the rule stop or
repeat on any run of its words, since the agent's echo would, its greeting among them and a
leading waw written apart while the phrase plays."""

from __future__ import annotations

from itertools import combinations
from typing import Any

import pytest
from t2_agentic_voice import ConfigurationError, Language, Phrases, VoiceAgent, Words
from t2_agentic_voice.core.settings.tts import LanguageTag
from t2_agentic_voice.domain.fixed_phrases import fixed_phrases
from t2_agentic_voice.domain.interruptions import Overlap, judge
from t2_agentic_voice.domain.presets import NOTICES
from t2_agentic_voice.domain.silence import CAPTIONS
from t2_agentic_voice.domain.text.words import holds_words
from t2_agentic_voice.domain.words import PRESET_WORDS, WORD_KINDS, rule_form

ENGLISH = Language.english(greeting="Welcome to the test line")
SAUDI = Language.saudi_arabic(greeting="hello in a made-up register")


def test_each_preset_reaches_its_languages_lists_by_its_primary_code() -> None:
    arabic = Language.arabic(greeting="a made-up greeting")
    assert (ENGLISH.words, SAUDI.words, arabic.words) == (
        PRESET_WORDS["en"],
        PRESET_WORDS["ar"],
        PRESET_WORDS["ar"],
    )
    assert set(PRESET_WORDS) == {"ar", "en"} and tuple(Words.model_fields) == WORD_KINDS
    assert WORD_KINDS == ("stop", "wait", "repeat", "backchannel", "no")


def test_the_defaults_are_the_presets_lists_and_an_agents_by_default() -> None:
    defaults = Phrases.defaults()
    assert defaults.words("en") == PRESET_WORDS["en"] and defaults.words("ar") == PRESET_WORDS["ar"]
    agent = VoiceAgent(name="words-test", languages=[ENGLISH])
    assert agent.phrases == defaults


def test_a_team_extends_the_lists_after_the_words_there_and_none_twice() -> None:
    first = Phrases.defaults().extend(stop={"en": ["made-up halt", "made-up halt"]})
    both = first.extend(
        stop={"en": ["made-up halt", "made-up cease"], "ar": ["made-up arabic"]},
        backchannel={"en": ["made-up hum"]},
        no={"ar": ["made-up nay"]},
    )
    english = both.words("en")
    assert english.stop[-2:] == ("made-up halt", "made-up cease")
    assert english.stop.count("made-up halt") == 1 and english.backchannel[-1] == "made-up hum"
    assert (
        both.words("ar").stop[-1] == "made-up arabic" and both.words("ar").no[-1] == "made-up nay"
    )
    assert "made-up cease" not in first.words("en").stop  # extending makes new lists
    lists: Any = both.stop
    with pytest.raises(TypeError):
        lists["en"] = ("changed",)
    agent = VoiceAgent(name="words-test", languages=[ENGLISH], phrases=both)
    assert agent.phrases.words("en") == english


@pytest.mark.parametrize(
    "added",
    [
        {"stop": {"fr": ["made-up"]}},
        {"repeat": {"en": "made-up words, not a list"}},
        {"backchannel": {"en": [""]}},
    ],
)
def test_what_the_lists_cannot_take_names_the_kind_never_the_word(added: Any) -> None:
    with pytest.raises(ConfigurationError) as raised:
        Phrases.defaults().extend(**added)
    (kind,) = added
    assert raised.value.details == {"field": kind} and "FIX: " in raised.value.message
    assert "made-up" not in raised.value.message


def test_a_declaration_with_phrases_it_cannot_run_names_the_field() -> None:
    with pytest.raises(ConfigurationError) as raised:
        VoiceAgent.model_validate(
            {"name": "words-test", "languages": [ENGLISH], "phrases": {"stop": {"fr": ["x"]}}}
        )
    assert raised.value.details == {"field": "phrases"}
    assert "Phrases.defaults().extend" in raised.value.message


def _arabic(word: str) -> bool:
    return all(char == " " or chr(0x0600) <= char <= chr(0x06FF) for char in word)


def test_the_presets_lists_are_in_the_rules_form_each_word_once_and_of_one_kind() -> None:
    for code, words in PRESET_WORDS.items():
        listed = [word for kind in WORD_KINDS for word in getattr(words, kind)]
        assert listed and all(rule_form(word) == word for word in listed), code
        assert len(listed) == len(set(listed)), code  # once, and in one kind only
        written = _arabic if code == "ar" else str.isascii
        assert all(written(word) for word in listed), code
        assert all(getattr(words, kind) for kind in WORD_KINDS), code  # every kind has words


# Each preset by its tag, built with a greeting made up for the test; the Arabic one says
# wa-a'eed ("and I say again") as Ole5's does, a repeat word after waw (and).
ARABIC_GREETING = "ترحيب مكتوب للاختبار، اسأل وأعيد لك الجواب"
PRESETS: dict[LanguageTag, Language] = {
    "ar-SA": Language.saudi_arabic(greeting=ARABIC_GREETING),
    "ar": Language.arabic(greeting=ARABIC_GREETING),
    "en": Language.english(greeting="A greeting made up for the test."),
}
WAW = "\u0648"  # waw, and


def _waw_apart(form: str) -> list[str]:
    """The words of `form` with a leading waw (and) written apart, as Whisper may write it."""
    words: list[str] = []
    for word in form.split():
        words.extend((WAW, word[1:]) if len(word) > 1 and word.startswith(WAW) else (word,))
    return words


@pytest.mark.parametrize("tag", list(PRESETS))
def test_no_presets_fixed_phrase_holds_a_word_its_echo_would_stop_the_agent_on(
    tag: LanguageTag,
) -> None:
    """Each fixed phrase of a preset (its greeting, echo frame and spoken notices) and its busy
    notice: no word of the stop, wait, repeat or listening lists as whole words; no run of its
    words that the rule, with nothing played, stops or repeats on; and none, each leading waw
    written apart, that it stops or repeats on while the phrase plays."""
    language = PRESETS[tag]
    agent = VoiceAgent(name="words-test", languages=[language])
    texts = [p.text for p in fixed_phrases(agent)]
    texts.append(NOTICES[tag]["busy"])
    words = language.words
    assert ARABIC_GREETING in texts or tag == "en"
    for text in texts:
        form = rule_form(text)
        for kind in ("stop", "wait", "repeat", "backchannel"):
            held = [word for word in getattr(words, kind) if holds_words(form, word)]
            assert held == [], (tag, kind)
        for said, played in ((form.split(), ()), (_waw_apart(form), (text,))):
            for start, end in combinations(range(len(said) + 1), 2):
                overlap = Overlap(
                    text=" ".join(said[start:end]),
                    speech_s=0.5,
                    played=played,
                    language=language.primary,
                )
                found = judge(
                    overlap,
                    words=words,
                    no_speech_max=None,
                    captions=CAPTIONS,
                    min_words=2,
                    short_words=2,
                    short_s=1.2,
                )
                assert found.reason not in ("stop_word", "repeat_word"), (tag, text, start, end)

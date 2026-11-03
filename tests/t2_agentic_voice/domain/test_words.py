"""The words the interruption rule reads (domain/words.py): each language preset reaches its own
lists, the agent's `phrases` start from the presets' and a team extends them, each kind by
language code, after the words already there and none twice, read-only; one language's lists
come whole; and what cannot be taken is a ConfigurationError naming the kind, or for the
declaration the field, never a word (plan 005, Block 0; the lists themselves are Track A's)."""

from __future__ import annotations

from typing import Any

import pytest
from t2_agentic_voice import ConfigurationError, Language, Phrases, VoiceAgent, Words
from t2_agentic_voice.domain.words import PRESET_WORDS, WORD_KINDS

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

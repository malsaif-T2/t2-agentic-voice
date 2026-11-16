"""How a text's words are read with each listed phrase as one (domain/text/words.py's
`phrase_tokens`), which the interruption rule, the yes rule and a read-back's `covered` share;
and the two readers of a language's primary code (core/settings/words.py's `primary_code`, a
tag's; domain/words.py's `heard_code`, a transcript's)."""

from __future__ import annotations

import pytest
from t2_agentic_voice.core.settings.words import primary_code
from t2_agentic_voice.domain.text.words import phrase_tokens
from t2_agentic_voice.domain.words import heard_code
from t2_agentic_voice.domain.yes_words import covered

PHRASES = {"go on", "go on then", "then", "okay"}


@pytest.mark.parametrize(
    ("text", "tokens"),
    [
        ("", []),
        ("okay", ["okay"]),
        ("go on then okay", ["go on then", "okay"]),  # the longest first
        ("go on now", ["go on", "now"]),
        ("go then on", ["go", "then", "on"]),  # a phrase only as its words in a row
        ("well go on then", ["well", "go on then"]),
    ],
)
def test_the_longest_listed_phrase_from_each_word_is_one_token(
    text: str, tokens: list[str]
) -> None:
    assert phrase_tokens(text.split(), PHRASES) == tokens


def test_with_no_phrases_each_word_is_a_token() -> None:
    assert phrase_tokens(["go", "on", "then"], ()) == ["go", "on", "then"]


@pytest.mark.parametrize(
    ("text", "held"),
    [("go on then", True), ("okay go on", True), ("go on now", False), ("", False)],
)
def test_covered_holds_when_every_token_is_a_listed_phrase(text: str, held: bool) -> None:
    assert covered(text, tuple(PHRASES)) is held


def test_a_tag_has_its_primary_code_and_a_transcript_names_one() -> None:
    assert [primary_code(tag) for tag in ("ar-SA", "ar", "en")] == ["ar", "ar", "en"]
    named = ["ar", "Arabic", "ARABIC", "en", "english", "en-US", "fr", "", None]
    assert [heard_code(name) for name in named] == [
        "ar",
        "ar",
        "ar",
        "en",
        "en",
        "en",
        None,
        None,
        None,
    ]


@pytest.mark.parametrize(
    "named", ["Armenian", "Arabica", "ara", "Engl", "eng", "Norwegian Nynorsk", "ar_SA", " en"]
)
def test_a_name_only_starting_like_a_code_names_none_of_the_agents_languages(named: str) -> None:
    """TD-011: Groq's names are matched exactly, so "Armenian" is never read as Arabic."""
    assert heard_code(named) is None

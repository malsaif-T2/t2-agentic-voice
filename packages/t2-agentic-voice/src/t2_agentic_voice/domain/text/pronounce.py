"""The pronunciation map (the design's 3.1 and 4.3): how a written form is said, per language, so
the text-to-speech provider says a term as the team wants it. The map is the team's data, given
with its agent (`VoiceAgent(pronounce={"LT-": {"ar": ..., "en": "L T"}})`, the design's 4.3),
which checks each entry when the agent is declared (domain/declaration.py); an app's own entries
never sit in the library (ARCH-WORDS). The phrase cache applies it to each fixed phrase before
it packs the phrase's requests, so no request passes `max_chars` once the map has run, and keeps
the phrase under its written form, which captions show (adapters/phrase_cache.py). Public
through the `languages` facade, with its type.

A form stands as whole words where its first word is not the end of a longer word and its last
word not the start of one: a form that starts or ends with a letter or digit (an Arabic mark
after a letter counts as part of its word) is found only where no letter, digit or mark stands
against that end, so "LT-" is found in "LT-00423", while "Al" is not found in "Ali". A form is
found as written, its case included, and the forms are looked for in one pass, the longest
first where two start at one place, so a form's spoken words are never looked in again. Where
a said form would run into the word after it or before it ("L T" against "00423"), a space is
put between them.
"""

from __future__ import annotations

import re
from collections.abc import Mapping

from t2_agentic_voice.core.settings.tts import LanguageTag
from t2_agentic_voice.domain.text.arabic import _MARKS

# Each written form to how each language says it, by a language's primary code (`ar`, `en`),
# which both Arabic tags share: `VoiceAgent.pronounce`'s type.
type Pronunciations = Mapping[str, Mapping[str, str]]

# A character a word is made of: a word character, or one of the marks `normalize_arabic`
# removes (harakat, tatweel), which are not word characters.
_WORD_CHARACTER = re.compile(rf"\w|{_MARKS.pattern}")


def _is_word_character(char: str) -> bool:
    """Whether `char` (one character, or none) is part of a word."""
    return _WORD_CHARACTER.fullmatch(char) is not None


def _pattern(form: str) -> str:
    """The pattern that finds `form` standing as whole words."""
    before = rf"(?<!\w)(?<!{_MARKS.pattern})" if _is_word_character(form[0]) else ""
    after = rf"(?!\w|{_MARKS.pattern})" if _is_word_character(form[-1]) else ""
    return f"{before}{re.escape(form)}{after}"


def pronounce(text: str, pronunciations: Pronunciations, *, language: LanguageTag) -> str:
    """`text` with each written form of `pronunciations` that stands as whole words replaced by
    how `language` says it; a form with no entry for the language is left as written."""
    code = "en" if language == "en" else "ar"
    said = {form: entry[code] for form, entry in pronunciations.items() if code in entry}
    if not said:
        return text
    forms = sorted(said, key=len, reverse=True)
    found = re.compile("|".join(_pattern(form) for form in forms))

    def spoken(match: re.Match[str]) -> str:
        words = said[match.group()]
        before = text[match.start() - 1 : match.start()]
        after = text[match.end() : match.end() + 1]
        lead = " " if _is_word_character(before) and _is_word_character(words[:1]) else ""
        tail = " " if _is_word_character(after) and _is_word_character(words[-1:]) else ""
        return f"{lead}{words}{tail}"

    return found.sub(spoken, text)

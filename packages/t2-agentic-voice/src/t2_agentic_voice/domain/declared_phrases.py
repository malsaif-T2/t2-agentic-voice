"""The texts a declaration holds (domain/declaration.py): a phrase the call speaks (`Phrase`: a
greeting, the frame, a notice, a progress line, a spoken form), a progress line as a language
gives it (`ProgressLine`: one phrase, or a few wordings of it, said in turn so a call does not
say the same one twice running: plan 010's 1.15), and the pronunciation map
(`DeclaredPronunciations`). A phrase says something, on one line, and holds no character a
reader cannot see but the no-break spaces, the joiners and the direction marks that pasted text
often carries (domain/text/invisible.py); each refusal is said whole and never repeats the
value."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Annotated, get_args

from pydantic import AfterValidator, Field, PlainSerializer, PlainValidator

from t2_agentic_voice.core.settings.base import FROZEN, PLAIN
from t2_agentic_voice.core.settings.words import LanguageCode
from t2_agentic_voice.domain.text.invisible import holds_refused_character, provider_text

# What a phrase may not hold, said whole, since the team cannot see the character it means.
_UNSEEN = (
    "a text in it holds a control or format character, a line or paragraph separator, a lone "
    "surrogate or a space other than U+0020; of these, a phrase may hold only the no-break "
    "spaces U+00A0 and U+202F, the joiners U+200C and U+200D and the direction marks U+200E, "
    "U+200F and U+061C"
)
# The most wordings a progress line may have: a few, so each is heard now and then (1.15 asks
# for 3 or 4 a language).
MAX_WORDINGS = 8


def _phrase(value: str) -> str:
    """`value`, when it holds no character a spoken phrase may not (domain/text/invisible.py)
    and says something once a provider's text is made of it; the error never repeats the
    value."""
    if holds_refused_character(value):
        raise ValueError(_UNSEEN)
    if not provider_text(value).strip():
        raise ValueError("a text in it says nothing: it is empty, or only spaces and marks")
    return value


def _form(value: str) -> str:
    """`value` as a written form to look for: a phrase with no space at either end, which would
    keep it from ever standing as whole words."""
    _phrase(value)
    if value != value.strip():
        raise ValueError(
            "a written form starts or ends with a space, so it never stands as whole words"
        )
    return value


def _line(value: object) -> str | tuple[str, ...]:
    """`value` when it is a progress line: one phrase, or a list or tuple of up to
    `MAX_WORDINGS` phrases, each its own (kept as a tuple), said in turn."""
    if isinstance(value, str):
        return _phrase(value)
    if not isinstance(value, list | tuple) or not 1 <= len(value) <= MAX_WORDINGS:
        raise ValueError(
            f"a progress line is one text, or a list of 1 to {MAX_WORDINGS} wordings of it"
        )
    if not all(isinstance(each, str) for each in value):
        raise ValueError("a wording of a progress line is not a text")
    if len(set(value)) != len(value):
        raise ValueError("two wordings of a progress line are the same; give each its own")
    return tuple(_phrase(each) for each in value)


def _dumped(line: str | tuple[str, ...]) -> str | list[str]:
    """A progress line as JSON holds it: its text, or its wordings as a list."""
    return line if isinstance(line, str) else list(line)


def wordings(line: str | tuple[str, ...]) -> tuple[str, ...]:
    """A progress line's wordings (`ProgressLine`): itself alone when it is one text."""
    return (line,) if isinstance(line, str) else line


def _code(value: str) -> str:
    """`value` when it is a primary language code a pronunciation is keyed by."""
    if value not in get_args(LanguageCode):  # a pronunciation's language, by its code
        raise ValueError("a pronunciation names its language `ar` (both Arabic presets) or `en`")
    return value


Phrase = Annotated[str, AfterValidator(_phrase)]
# A progress line as `Language.progress` holds it: one phrase, as a team has always given it, or
# its wordings, a tuple of phrases (given as a list or a tuple), one of them said each time,
# never the one the call said last (voice/session/talker_play.py).
ProgressLine = Annotated[
    str | tuple[str, ...], PlainValidator(_line), PlainSerializer(_dumped, when_used="json")
]
# A pronunciation: how each language says one written form.
_Said = Annotated[
    Mapping[Annotated[str, AfterValidator(_code)], Phrase], Field(min_length=1), FROZEN, PLAIN
]
# A pronunciation map as `VoiceAgent.pronounce` holds it: the languages facade's
# `Pronunciations`, each entry checked and kept read-only.
DeclaredPronunciations = Annotated[
    Mapping[Annotated[str, AfterValidator(_form)], _Said], FROZEN, PLAIN
]

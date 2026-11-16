"""The texts a declaration holds (domain/declaration.py): a phrase the call speaks (`Phrase`: a
greeting, the frame, a notice, a progress line, a spoken form) and the pronunciation map
(`DeclaredPronunciations`). A phrase says something, on one line, and holds no character a
reader cannot see but the no-break spaces, the joiners and the direction marks that pasted text
often carries (domain/text/invisible.py); each refusal is said whole and never repeats the
value."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Annotated, get_args

from pydantic import AfterValidator, Field

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


def _code(value: str) -> str:
    """`value` when it is a primary language code a pronunciation is keyed by."""
    if value not in get_args(LanguageCode):  # a pronunciation's language, by its code
        raise ValueError("a pronunciation names its language `ar` (both Arabic presets) or `en`")
    return value


Phrase = Annotated[str, AfterValidator(_phrase)]
# A pronunciation: how each language says one written form.
_Said = Annotated[
    Mapping[Annotated[str, AfterValidator(_code)], Phrase], Field(min_length=1), FROZEN, PLAIN
]
# A pronunciation map as `VoiceAgent.pronounce` holds it: the languages facade's
# `Pronunciations`, each entry checked and kept read-only.
DeclaredPronunciations = Annotated[
    Mapping[Annotated[str, AfterValidator(_form)], _Said], FROZEN, PLAIN
]

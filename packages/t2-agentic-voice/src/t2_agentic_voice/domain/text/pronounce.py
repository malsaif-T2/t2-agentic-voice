"""The pronunciation map (the design's 3.1 and 4.3): how a written form is said, per language, so
the text-to-speech provider says a term as the team wants it. The map is the team's data, given
with its agent (`VoiceAgent(pronounce={"LT-": {"ar": ..., "en": "L T"}})`, the design's 4.3),
which checks each entry when the agent is declared (domain/declaration.py); an app's own entries
never sit in the library (ARCH-WORDS). Built by plan 003's Track A; until then a stub. Public
through the `languages` facade, with its type.
"""

from __future__ import annotations

from collections.abc import Mapping

from t2_agentic_voice.core.settings.tts import LanguageTag

_STUB = "the pronunciation map is built by plan 003's Track A"

# Each written form to how each language says it, by a language's primary code (`ar`, `en`),
# which both Arabic tags share: `VoiceAgent.pronounce`'s type.
type Pronunciations = Mapping[str, Mapping[str, str]]


def pronounce(text: str, pronunciations: Pronunciations, *, language: LanguageTag) -> str:
    """`text` with each written form of `pronunciations` that stands as whole words replaced by
    how `language` says it; a form with no entry for the language is left as written."""
    raise NotImplementedError(_STUB)

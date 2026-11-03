"""The fixed phrases (the design's 10.4): what a call of an agent speaks as written, each
language's greeting, echo frame and spoken notices, which the phrase cache has at hand from the
runtime's start (adapters/phrase_cache.py), so the session plays each with no request. Each
names which of its language's texts it is, so an error can name it in the place of its text.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from t2_agentic_voice.core.settings.tts import LanguageTag
from t2_agentic_voice.domain.declaration import Language, VoiceAgent

# Which of a language's texts a fixed phrase is (`fixed_phrases`): its field, a notice's under
# `notices`. An error names it in the place of the phrase's text.
PhraseKind = Literal["greeting", "echo_frame", "notices.error", "notices.ended"]


@dataclass(frozen=True, kw_only=True)
class FixedPhrase:
    """One phrase a call speaks as written: its `text`, its `language`, and which of the
    language's texts it is (`kind`), which an error names in the place of the text."""

    text: str
    language: LanguageTag
    kind: PhraseKind


def fixed_phrases(agent: VoiceAgent) -> tuple[FixedPhrase, ...]:
    """Every phrase a call of `agent` speaks as written: each language's greeting, echo frame
    and spoken notices (domain/declaration.py's `SPOKEN_NOTICES`), in that order. The phrase
    cache has each at hand from the runtime's start (`PhraseCache.declare(agent)`), so the
    session plays each with no request; words heard in a call are never among them (invariant
    8)."""
    return tuple(
        FixedPhrase(text=text, language=language.tag, kind=kind)
        for language in agent.languages
        for kind, text in _phrases_of(language).items()
    )


def _phrases_of(language: Language) -> dict[PhraseKind, str]:
    """The phrases a call held in `language` speaks as written, by kind."""
    return {
        "greeting": language.greeting,
        "echo_frame": language.echo_frame,
        "notices.error": language.notices["error"],
        "notices.ended": language.notices["ended"],
    }

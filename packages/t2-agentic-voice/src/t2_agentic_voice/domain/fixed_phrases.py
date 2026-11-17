"""The fixed phrases (the design's 10.4): what a call of an agent speaks as written, each
language's greeting, echo frame and spoken notices, and the progress line of each of its tools
(plan 006), each wording of one that has several (plan 010's 1.15), which the phrase cache has
at hand from the runtime's start
(adapters/phrase_cache.py), so the session plays each with no request. Each names which of its
language's texts it is, so an error can name it in the place of its text.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from t2_agentic_voice.core.settings.tts import LanguageTag
from t2_agentic_voice.domain.declaration import Language, VoiceAgent
from t2_agentic_voice.domain.declared_phrases import wordings

# Which of a language's texts a fixed phrase is (`fixed_phrases`): its field, a notice's under
# `notices`, or a tool's progress line (`progress`, its key in `FixedPhrase.key`). An error names
# it in the place of the phrase's text.
PhraseKind = Literal[
    "greeting", "echo_frame", "notices.error", "notices.cut_off", "notices.ended", "progress"
]


@dataclass(frozen=True, kw_only=True)
class FixedPhrase:
    """One phrase a call speaks as written: its `text`, its `language`, which of the language's
    texts it is (`kind`), which an error names in the place of the text, and for a progress line
    its `key` (`Language.progress`), the same for each of its wordings, None for any other."""

    text: str
    language: LanguageTag
    kind: PhraseKind
    key: str | None = None


def fixed_phrases(agent: VoiceAgent) -> tuple[FixedPhrase, ...]:
    """Every phrase a call of `agent` speaks as written: each language's greeting, echo frame
    and spoken notices (domain/declaration.py's `SPOKEN_NOTICES`), then the progress line of
    each key its tools name, each of its wordings in order, in the tools' order, each key once
    (a line no tool names is never spoken, so it is not declared). The declaration has checked
    that each language gives every such line. The phrase cache has each at hand from the
    runtime's start (`PhraseCache.declare(agent)`), so the session plays each with no request;
    words heard in a call are never among them (invariant 8), and a talker's clauses are the
    clause cache's."""
    keys = tuple(dict.fromkeys(tool.progress for tool in agent.tools if tool.progress))
    return tuple(
        phrase
        for language in agent.languages
        for phrase in (
            *(
                FixedPhrase(text=text, language=language.tag, kind=kind)
                for kind, text in _phrases_of(language).items()
            ),
            *(
                FixedPhrase(text=text, language=language.tag, kind="progress", key=key)
                for key in keys
                for text in wordings(language.progress[key])
            ),
        )
    )


def _phrases_of(language: Language) -> dict[PhraseKind, str]:
    """The phrases a call held in `language` speaks as written, by kind, but its progress
    lines."""
    return {
        "greeting": language.greeting,
        "echo_frame": language.echo_frame,
        "notices.error": language.notices["error"],
        "notices.cut_off": language.notices["cut_off"],
        "notices.ended": language.notices["ended"],
    }

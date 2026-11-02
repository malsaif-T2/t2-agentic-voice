"""The declaration of a use case: the agent a team declares and the languages its calls are held
in (the design's 4.3 and 5.2), frozen, with no IO.

For now an agent has a name and its languages only, and the voice session answers in echo mode
(`session.mode`): each turn is said back, after a fixed frame in the turn's language, «سمعتك
تقول: …» or "I heard: …" (plan 003, Q3). The talker's parts (instructions, tools, the
vocabulary) come with the talker as optional arguments, so an echo agent stays a team's first
audio check. Each language is built from its preset, which gives it its tag and its frame; the
team gives its greeting, the phrase that opens a call.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Annotated, Literal, final

from pydantic import AfterValidator, BaseModel, ConfigDict, field_validator

from t2_agentic_voice.core.errors import ConfigurationError
from t2_agentic_voice.core.settings.tts import LanguageTag

# The echo's frames (plan 003, Q3, in the Saudi register Q5 chose for the fixed phrases). The
# Arabic one, said for both Arabic presets, is «سمعتك تقول:»: seen, meem, ain, teh, kaf; a space;
# teh, qaf, waw, lam; a colon.
_ARABIC_FRAME = "\u0633\u0645\u0639\u062a\u0643 \u062a\u0642\u0648\u0644:"
_ECHO_FRAMES: dict[LanguageTag, str] = {
    "ar-SA": _ARABIC_FRAME,
    "ar": _ARABIC_FRAME,
    "en": "I heard:",
}
# An agent's name: it names the agent's folder under `storage.var_dir` and its traces, so it is
# a lowercase word, with hyphens.
AGENT_NAME = re.compile(r"[a-z][a-z0-9-]{0,63}")


def _phrase(value: str) -> str:
    """`value`, when it says something and holds no line break or control character, which a
    spoken phrase never needs; the error never repeats the value."""
    if not value.strip():
        raise ValueError("must say something: it is empty or only spaces")
    if not value.isprintable():
        raise ValueError("must hold printable characters only: no line break or control")
    return value


_Phrase = Annotated[str, AfterValidator(_phrase)]


class Language(BaseModel):
    """One language a call can be held in: its `tag` (`ar-SA` Saudi Arabic, `ar` Modern Standard
    Arabic, `en` English), the `greeting` the agent opens a call with in it, and the
    `echo_frame` the echo says before the words it heard. Build one with its preset:
    `Language.saudi_arabic(greeting=...)`, `Language.arabic(...)` or `Language.english(...)`.
    Each tag is spoken in the model and voice `tts.languages` gives it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    tag: LanguageTag
    greeting: _Phrase
    echo_frame: _Phrase

    @classmethod
    def saudi_arabic(cls, *, greeting: str) -> Language:
        """Saudi Arabic (`ar-SA`), opening each call with `greeting`."""
        return cls._preset("ar-SA", greeting)

    @classmethod
    def arabic(cls, *, greeting: str) -> Language:
        """Modern Standard Arabic (`ar`), opening each call with `greeting`."""
        return cls._preset("ar", greeting)

    @classmethod
    def english(cls, *, greeting: str) -> Language:
        """English (`en`), opening each call with `greeting`."""
        return cls._preset("en", greeting)

    @classmethod
    def _preset(cls, tag: LanguageTag, greeting: str) -> Language:
        return cls(tag=tag, greeting=greeting, echo_frame=_ECHO_FRAMES[tag])

    @property
    def primary(self) -> Literal["ar", "en"]:
        """The tag's primary language, the code a speech-to-text provider is told (`ar` for
        both Arabic presets)."""
        return "en" if self.tag == "en" else "ar"


@final
class VoiceAgent(BaseModel):
    """A use case, as a team declares it: its `name` and the `languages` its calls are held in,
    the first a call's when nothing picks another (`call_language`). Frozen, with no IO; built
    once and handed to the runtime. A name or a language list it cannot run with is a
    ConfigurationError with a FIX line."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    # Given as any sequence (a list, as the design writes it), kept as a tuple.
    languages: Sequence[Language]

    @field_validator("name")
    @classmethod
    def _named(cls, value: str) -> str:
        if not AGENT_NAME.fullmatch(value):
            raise ConfigurationError(
                "The agent's name names its folder and its traces, so it is a lowercase word of "
                "up to 64 characters. FIX: name it with lowercase letters, digits and hyphens, "
                'starting with a letter, as "branch-helper".',
                details={"field": "name"},
            )
        return value

    @field_validator("languages")
    @classmethod
    def _spoken(cls, value: Sequence[Language]) -> tuple[Language, ...]:
        tags = [language.tag for language in value]
        if not tags or len(set(tags)) != len(tags):
            raise ConfigurationError(
                "An agent speaks at least one language, each once. FIX: give `languages` one "
                "preset per language, as [Language.saudi_arabic(greeting=...)].",
                details={"field": "languages"},
            )
        return tuple(value)

    def call_language(self, requested: LanguageTag | None, *, locale: str | None) -> Language:
        """The language a call is held in, fixed when it joins and kept to its end (the echo
        has no other; the talker will pick each reply's): the `requested` tag (the caller's
        pick in the client) when the agent speaks it; else the caller's `locale` (a BCP 47 tag,
        as the join token carries it), matched in any case, its exact tag first, then the first
        of the agent's languages whose primary language is the locale's primary subtag (`ar`
        for both Arabic presets); else the agent's first language."""
        for language in self.languages:
            if language.tag == requested:
                return language
        wanted = (locale or "").casefold()
        primary = wanted.partition("-")[0]
        found = [language for language in self.languages if language.tag.casefold() == wanted]
        found += [language for language in self.languages if language.primary == primary]
        return (found or list(self.languages))[0]

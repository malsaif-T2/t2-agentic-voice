"""The declaration of a use case: the agent a team declares and the languages its calls are held
in (the design's 4.3 and 5.2), frozen, with no IO.

For now an agent has a name, its languages and its pronunciation map, and the voice session
answers in echo mode (`session.mode`): each turn is said back, after a fixed frame in the turn's
language, «سمعتك تقول: …» or "I heard: …" (plan 003, Q3). The talker's parts (instructions,
tools, the vocabulary) come with the talker as optional arguments, so an echo agent stays a
team's first audio check. Each language is built from its preset, which gives it its tag, its
frame and a text for each notice the caller may be told; the team gives its greeting, the phrase
that opens a call, and may give its own notices. The phrases a call speaks as written
(`fixed_phrases`) are synthesized once, at the runtime's start, and played from the phrase cache.

A declaration the library cannot run with is a ConfigurationError naming the field, with a FIX
line (the design's 4.2), and never the value it refused; only assigning to a built agent or
language raises pydantic's ValidationError, as for every frozen model.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Annotated, Any, Literal, Self, final, get_args

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    ModelWrapValidatorHandler,
    ValidationError,
    field_validator,
    model_validator,
)

from t2_agentic_voice.core.errors import ConfigurationError
from t2_agentic_voice.core.settings.base import FROZEN, PLAIN
from t2_agentic_voice.core.settings.tts import LanguageTag

# A notice's kind (the design's 5.5), each told in the call's language: `busy`, a call that
# cannot be taken, which admission control answers at join, before a call has audio (the
# design's 10.5); `error`, a turn or an echo that failed; `ended`, a call the session ends
# itself, at a limit (plan 003, Q4). The session sends `error` and `ended` as `t2v/1`'s
# `notice`, whose text the client shows, and speaks each as a reply (voice/session/call.py).
NoticeKind = Literal["busy", "error", "ended"]
NOTICE_KINDS: tuple[NoticeKind, ...] = get_args(NoticeKind)
# The notices a call speaks, so the phrase cache holds them: `busy` comes before any call.
SPOKEN_NOTICES: tuple[NoticeKind, ...] = ("error", "ended")

# The echo's frames (plan 003, Q3, in the Saudi register Q5 chose for the fixed phrases). The
# Arabic one, said for both Arabic presets, is «سمعتك تقول:»: seen, meem, ain, teh, kaf; a space;
# teh, qaf, waw, lam; a colon.
_ARABIC_FRAME = "\u0633\u0645\u0639\u062a\u0643 \u062a\u0642\u0648\u0644:"
_ECHO_FRAMES: dict[LanguageTag, str] = {
    "ar-SA": _ARABIC_FRAME,
    "ar": _ARABIC_FRAME,
    "en": "I heard:",
}
# Each preset's notices: `ar-SA`'s in the Saudi register Q5 chose for the fixed phrases, `ar`'s
# in Modern Standard Arabic. Each comment gives the text's sound, then its meaning.
_NOTICES: dict[LanguageTag, dict[NoticeKind, str]] = {
    "ar-SA": {
        # al-khutoot mashghoola al-heen, haawil marra thaanya ba'd shway: the lines are busy
        # now; try again in a little while.
        "busy": (
            "\u0627\u0644\u062e\u0637\u0648\u0637 \u0645\u0634\u063a\u0648\u0644\u0629 "
            "\u0627\u0644\u062d\u064a\u0646\u060c \u062d\u0627\u0648\u0644 \u0645\u0631\u0629 "
            "\u062b\u0627\u0646\u064a\u0629 \u0628\u0639\u062f \u0634\u0648\u064a."
        ),
        # saar 'indana khalal baseet, takallam marra thaanya law samaht: we had a small fault;
        # speak once more, please.
        "error": (
            "\u0635\u0627\u0631 \u0639\u0646\u062f\u0646\u0627 \u062e\u0644\u0644 "
            "\u0628\u0633\u064a\u0637\u060c \u062a\u0643\u0644\u0645 \u0645\u0631\u0629 "
            "\u062b\u0627\u0646\u064a\u0629 \u0644\u0648 \u0633\u0645\u062d\u062a."
        ),
        # intahat al-mukaalama, ya'teek al-'aafya: the call has ended; may you be well.
        "ended": (
            "\u0627\u0646\u062a\u0647\u062a \u0627\u0644\u0645\u0643\u0627\u0644\u0645\u0629\u060c "
            "\u064a\u0639\u0637\u064a\u0643 \u0627\u0644\u0639\u0627\u0641\u064a\u0629."
        ),
    },
    "ar": {
        # al-khutoot mashghoola al-aan, yurja al-muhaawala marra ukhra ba'd qaleel: the lines
        # are busy now; please try again shortly.
        "busy": (
            "\u0627\u0644\u062e\u0637\u0648\u0637 \u0645\u0634\u063a\u0648\u0644\u0629 "
            "\u0627\u0644\u0622\u0646\u060c \u064a\u0631\u062c\u0649 "
            "\u0627\u0644\u0645\u062d\u0627\u0648\u0644\u0629 \u0645\u0631\u0629 "
            "\u0623\u062e\u0631\u0649 \u0628\u0639\u062f \u0642\u0644\u064a\u0644."
        ),
        # hadath khalal ladayna, hal yumkinuka i'aadat ma qultah: a fault occurred on our side;
        # can you repeat what you said?
        "error": (
            "\u062d\u062f\u062b \u062e\u0644\u0644 \u0644\u062f\u064a\u0646\u0627\u060c "
            "\u0647\u0644 \u064a\u0645\u0643\u0646\u0643 \u0625\u0639\u0627\u062f\u0629 "
            "\u0645\u0627 \u0642\u0644\u062a\u0647\u061f"
        ),
        # intahat al-mukaalama, shukran li-ittisaalik: the call has ended; thank you for calling.
        "ended": (
            "\u0627\u0646\u062a\u0647\u062a \u0627\u0644\u0645\u0643\u0627\u0644\u0645\u0629\u060c "
            "\u0634\u0643\u0631\u0627 \u0644\u0627\u062a\u0635\u0627\u0644\u0643."
        ),
    },
    "en": {
        "busy": "All our lines are busy right now. Please try again in a little while.",
        "error": "Something went wrong on our side. Could you say that again?",
        "ended": "The call has ended. Thank you for calling.",
    },
}
# An agent's name: it names the agent's folder under `storage.var_dir` and its traces, so it is
# a lowercase word, with hyphens.
AGENT_NAME = re.compile(r"[a-z][a-z0-9-]{0,63}")
# The names Windows keeps for its devices, which no folder can take (CPython 3.12's `pathlib`
# lists the same, `_WIN_RESERVED_NAMES`); the owner develops on Windows (plan 003's review).
_DEVICES = frozenset(
    {"con", "prn", "aux", "nul", *(f"{port}{n}" for port in ("com", "lpt") for n in range(1, 10))}
)
# A pronunciation names a language by its primary code, which both Arabic tags share.
_CODES = ("ar", "en")

# What each part of a declaration is fixed with, and who says it in an error.
_PRESET_FIX = (
    "build each language with its preset: Language.saudi_arabic(greeting=...), "
    "Language.arabic(...) or Language.english(...)."
)
_FIXES: dict[str, str] = {
    "Language": _PRESET_FIX,
    "tag": _PRESET_FIX,
    "echo_frame": _PRESET_FIX,
    "greeting": "give `greeting` the words the agent opens a call with, on one line.",
    "notices": (
        "give `notices` a text for `busy`, `error` or `ended`, each on one line, as "
        'notices={"ended": ...}; a kind it leaves out keeps the preset\'s text.'
    ),
    "VoiceAgent": "declare the agent as VoiceAgent(name=..., languages=[...]).",
    "name": (
        "name it with lowercase letters, digits and hyphens, starting with a letter, as "
        '"branch-helper", and not with a name Windows keeps for a device.'
    ),
    "languages": (
        "give `languages` one preset per language, as [Language.saudi_arabic(greeting=...)]."
    ),
    "pronounce": (
        "map each written form, as a text holds it, to how `ar` or `en` says it, on one line, "
        'as pronounce={"LT-": {"en": "L T"}}.'
    ),
}
_WHO = {"Language": "A language", "VoiceAgent": "The agent"}


def _phrase(value: str) -> str:
    """`value`, when it says something and holds no line break or control character, which a
    spoken phrase never needs; the error never repeats the value."""
    if not value.strip():
        raise ValueError("a text in it is empty or only spaces")
    if not value.isprintable():
        raise ValueError("a text in it holds a line break or a control character")
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
    if value not in _CODES:
        raise ValueError("a pronunciation names its language `ar` (both Arabic presets) or `en`")
    return value


def _every_kind[T](value: Mapping[NoticeKind, T]) -> Mapping[NoticeKind, T]:
    """`value` when it has a text for every kind of notice."""
    missing = [kind for kind in NOTICE_KINDS if kind not in value]
    if missing:
        raise ValueError(f"it has no text for {' or '.join(missing)}; each kind needs one")
    return value


def _a_language(value: object) -> object:
    """`value` when it may be a `Language`: one built, or the fields of one."""
    if not isinstance(value, Language | Mapping):
        raise ValueError("an item is not a language")
    return value


_Phrase = Annotated[str, AfterValidator(_phrase)]
# A pronunciation: how each language says one written form.
_Said = Annotated[
    Mapping[Annotated[str, AfterValidator(_code)], _Phrase], Field(min_length=1), FROZEN, PLAIN
]
# A pronunciation map as `VoiceAgent.pronounce` holds it: the languages facade's
# `Pronunciations`, each entry checked and kept read-only.
_Pronunciations = Annotated[Mapping[Annotated[str, AfterValidator(_form)], _Said], FROZEN, PLAIN]


class _Declared(BaseModel):
    """What the declaration's models share: frozen, a misspelt key an error, and any failure to
    build one a ConfigurationError naming the field at fault, with its FIX line."""

    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

    @model_validator(mode="wrap")
    @classmethod
    def _configured(cls, data: Any, handler: ModelWrapValidatorHandler[Self]) -> Self:
        """The model `data` declares, or a ConfigurationError for its first failure, raised
        after the handler, so no exception chain leads back to the ValidationError."""
        try:
            return handler(data)
        except ValidationError as error:
            first = error.errors(include_input=False, include_url=False)[0]
        raise _refused(cls, first["loc"], first["msg"])


def _refused(model: type[BaseModel], loc: tuple[int | str, ...], msg: str) -> ConfigurationError:
    """The ConfigurationError for a failure of `model`'s field at `loc` (none when the value is
    not one at all), from pydantic's message, which holds no value."""
    who = _WHO[model.__name__]
    field = str(loc[0]) if loc else None
    reason = msg.removeprefix("Value error, ")
    reason = reason[:1].lower() + reason[1:]
    if field is None:
        fix = _FIXES[model.__name__]
    elif field in model.model_fields:
        fix = _FIXES[field]
    else:
        *names, last = (f"`{name}`" for name in model.model_fields)
        fix = f"remove `{field}`: {who.lower()} takes {', '.join(names)} and {last}."
    where = "" if field is None else f" with its `{field}`"
    return ConfigurationError(
        f"{who} cannot run{where}: {reason}. FIX: {fix}", details={"field": field}
    )


class Language(_Declared):
    """One language a call can be held in: its `tag` (`ar-SA` Saudi Arabic, `ar` Modern Standard
    Arabic, `en` English), the `greeting` the agent opens a call with in it, the `echo_frame`
    the echo says before the words it heard, and its `notices`, the text of each kind of notice
    (`NoticeKind`) the caller is told in it. Build one with its preset:
    `Language.saudi_arabic(greeting=...)`, `Language.arabic(...)` or `Language.english(...)`,
    which gives the tag, the frame and each notice's text in the language's register (plan 003,
    Q5: Saudi for `ar-SA`, Modern Standard Arabic for `ar`); a team's own `notices` replace the
    kinds they name. Each tag is spoken in the model and voice `tts.languages` gives it."""

    tag: LanguageTag
    greeting: _Phrase
    echo_frame: _Phrase
    notices: Annotated[Mapping[NoticeKind, _Phrase], AfterValidator(_every_kind), FROZEN, PLAIN]

    @classmethod
    def saudi_arabic(
        cls, *, greeting: str, notices: Mapping[NoticeKind, str] | None = None
    ) -> Language:
        """Saudi Arabic (`ar-SA`), opening each call with `greeting`; `notices` replaces the
        preset's text of each kind it names."""
        return cls._preset("ar-SA", greeting, notices)

    @classmethod
    def arabic(cls, *, greeting: str, notices: Mapping[NoticeKind, str] | None = None) -> Language:
        """Modern Standard Arabic (`ar`), opening each call with `greeting`; `notices` replaces
        the preset's text of each kind it names."""
        return cls._preset("ar", greeting, notices)

    @classmethod
    def english(cls, *, greeting: str, notices: Mapping[NoticeKind, str] | None = None) -> Language:
        """English (`en`), opening each call with `greeting`; `notices` replaces the preset's
        text of each kind it names."""
        return cls._preset("en", greeting, notices)

    @classmethod
    def _preset(cls, tag: LanguageTag, greeting: str, notices: object) -> Language:
        texts: object = notices if notices is not None else _NOTICES[tag]
        if isinstance(notices, Mapping):
            texts = {**_NOTICES[tag], **notices}
        fields = {"tag": tag, "greeting": greeting, "echo_frame": _ECHO_FRAMES[tag]}
        return cls.model_validate(fields | {"notices": texts})

    @property
    def primary(self) -> Literal["ar", "en"]:
        """The tag's primary language, the code a speech-to-text provider is told (`ar` for
        both Arabic presets)."""
        return "en" if self.tag == "en" else "ar"


@final
class VoiceAgent(_Declared):
    """A use case, as a team declares it: its `name`; the `languages` its calls are held in, the
    first a call's when nothing picks another (`call_language`); and `pronounce`, its
    pronunciation map (the design's 4.3): each written form, as a text holds it, to how each
    language says it, keyed by the language's primary code (`ar` for both Arabic presets, `en`),
    as `pronounce={"LT-": {"ar": ..., "en": "L T"}}`, which the `languages` facade's
    `pronounce` applies. Frozen, with no IO; built once and handed to the runtime."""

    name: str
    # Given as any sequence (a list, as the design writes it), kept as a tuple.
    languages: Sequence[Annotated[Language, BeforeValidator(_a_language)]]
    pronounce: _Pronunciations = Field(default_factory=dict, validate_default=True)

    @field_validator("name")
    @classmethod
    def _named(cls, value: str) -> str:
        if not AGENT_NAME.fullmatch(value):
            raise ValueError(
                "the name names the agent's folder and its traces, so it is a lowercase word of "
                "up to 64 characters"
            )
        if value in _DEVICES:
            raise ValueError(
                "the name is one Windows keeps for a device (con, prn, aux, nul, com1 to com9, "
                "lpt1 to lpt9), so no folder can take it"
            )
        return value

    @field_validator("languages")
    @classmethod
    def _spoken(cls, value: Sequence[Language]) -> tuple[Language, ...]:
        tags = [language.tag for language in value]
        if not tags or len(set(tags)) != len(tags):
            raise ValueError("an agent speaks at least one language, each once")
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


def fixed_phrases(agent: VoiceAgent) -> tuple[tuple[str, LanguageTag], ...]:
    """Every phrase a call of `agent` speaks as written, each with its language: each language's
    greeting, echo frame and spoken notices (`SPOKEN_NOTICES`). The runtime declares them to the
    phrase cache at its start (the design's 10.4), so the session plays each with no request;
    words heard in a call are never among them (invariant 8)."""
    return tuple(
        (text, language.tag)
        for language in agent.languages
        for text in (
            language.greeting,
            language.echo_frame,
            *(language.notices[kind] for kind in SPOKEN_NOTICES),
        )
    )

"""The declaration of a use case: the agent a team declares and the languages its calls are held
in (the design's 4.3 and 5.2), frozen, with no IO.

For now an agent has a name, its languages and its pronunciation map, and the voice session
answers in echo mode (`session.mode`): each turn is said back, after a fixed frame in the turn's
language, «سمعتك تقول: …» or "I heard: …" (plan 003, Q3). The talker's parts (instructions,
tools, the vocabulary) come with the talker as optional arguments, so an echo agent stays a
team's first audio check. Each language is built from its preset, which gives it its tag, its
frame and a text for each notice the caller may be told; the team gives its greeting, the phrase
that opens a call, and may give its own notices. The phrases a call speaks as written
(domain/fixed_phrases.py) are synthesized once, at the runtime's start, and played from the
phrase cache.

A phrase (a greeting, the frame, a notice, a spoken form) says something, on one line, and holds
no character a reader cannot see but the no-break spaces, the joiners and the direction marks
that pasted text often carries (domain/text/invisible.py). A declaration the library cannot run
with is a ConfigurationError naming the field, with a FIX line (the design's 4.2), and never the
value it refused, however it is built: through a preset, the constructor, `model_validate` or
`model_validate_json` (a text that is not JSON included), and on a subclass of `Language` too;
only assigning to a built agent or language raises pydantic's ValidationError, as for every
frozen model.
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
    ValidationInfo,
    field_validator,
    model_validator,
)
from pydantic.config import ExtraValues

from t2_agentic_voice.core.errors import ConfigurationError
from t2_agentic_voice.core.settings.base import FROZEN, PLAIN
from t2_agentic_voice.core.settings.tts import LanguageTag
from t2_agentic_voice.domain.presets import ECHO_FRAMES, NOTICES
from t2_agentic_voice.domain.text.invisible import holds_refused_character, provider_text

# A notice's kind (the design's 5.5), each told in the call's language: `busy`, a call that
# cannot be taken, which admission control answers at join, before a call has audio (the
# design's 10.5); `error`, a turn or an echo that failed; `ended`, a call the session ends
# itself, at a limit (plan 003, Q4). The session sends `error` and `ended` as `t2v/1`'s
# `notice`, whose text the client shows, and speaks each as a reply (voice/session/call.py).
NoticeKind = Literal["busy", "error", "ended"]
NOTICE_KINDS: tuple[NoticeKind, ...] = get_args(NoticeKind)
# The notices a call speaks, so the phrase cache holds them: `busy` comes before any call.
SPOKEN_NOTICES: tuple[NoticeKind, ...] = ("error", "ended")

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
# How every phrase is given, whatever its failure: a pasted text may hold a character unseen.
_PLAIN = "on one line of plain text (type again a text pasted from a document or a chat)"
_FIXES: dict[str, str] = {
    "Language": _PRESET_FIX,
    "tag": _PRESET_FIX,
    "echo_frame": _PRESET_FIX,
    "greeting": f"give `greeting` the words the agent opens a call with, {_PLAIN}.",
    "VoiceAgent": "declare the agent as VoiceAgent(name=..., languages=[...]).",
    "name": (
        "name it with lowercase letters, digits and hyphens, starting with a letter, as "
        '"branch-helper", and not with a name Windows keeps for a device.'
    ),
    "languages": (
        "give `languages` one preset per language, as [Language.saudi_arabic(greeting=...)]."
    ),
    "pronounce": (
        f"map each written form, as a text holds it, to how `ar` or `en` says it, {_PLAIN}, "
        'as pronounce={"LT-": {"en": "L T"}}.'
    ),
}
# The notices' FIX, by the way the language was built: through its preset, which gives the text
# of each kind it is not given, or without one (`model_validate`), which gives none.
_NOTICES_FIX = {
    True: (
        f"give `notices` a text for `busy`, `error` or `ended`, each {_PLAIN}, as "
        'notices={"ended": ...}; with a preset, a kind it leaves out keeps the preset\'s text.'
    ),
    False: (
        f"give `notices` a text for each of busy, error and ended, each {_PLAIN}, as "
        'notices={"busy": ..., "error": ..., "ended": ...}; or build the language with its '
        "preset, which gives the text of each kind left out."
    ),
}
# A text that is not JSON, given to `model_validate_json`.
_JSON_FIX = (
    "give `model_validate_json` one JSON object of its fields, as `model_dump_json()` writes."
)
_WHO = {"Language": "A language", "VoiceAgent": "The agent"}
# What a phrase may not hold, said whole, since the team cannot see the character it means.
_UNSEEN = (
    "a text in it holds a control or format character, a line or paragraph separator, a lone "
    "surrogate or a space other than U+0020; of these, a phrase may hold only the no-break "
    "spaces U+00A0 and U+202F, the joiners U+200C and U+200D and the direction marks U+200E, "
    "U+200F and U+061C"
)
# The validation context a preset builds its language in, so that a failure's FIX says what the
# preset gives.
_FROM_PRESET = object()


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
    if value not in _CODES:
        raise ValueError("a pronunciation names its language `ar` (both Arabic presets) or `en`")
    return value


def _every_kind[T](value: Mapping[NoticeKind, T]) -> Mapping[NoticeKind, T]:
    """`value` when it has a text for every kind of notice."""
    missing = [kind for kind in NOTICE_KINDS if kind not in value]
    if missing:
        *rest, last = missing
        listed = f"{', '.join(rest)} or {last}" if rest else last
        raise ValueError(f"it has no text for {listed}; each of busy, error and ended needs one")
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
    def _configured(
        cls, data: Any, handler: ModelWrapValidatorHandler[Self], info: ValidationInfo
    ) -> Self:
        """The model `data` declares, or a ConfigurationError for its first failure, raised
        after the handler, so no exception chain leads back to the ValidationError."""
        try:
            return handler(data)
        except ValidationError as error:
            first = error.errors(include_input=False, include_url=False)[0]
        raise _refused(cls, first["loc"], first["msg"], preset=info.context is _FROM_PRESET)

    @classmethod
    def model_validate_json(
        cls,
        json_data: str | bytes | bytearray,
        *,
        strict: bool | None = None,
        extra: ExtraValues | None = None,
        context: Any | None = None,
        by_alias: bool | None = None,
        by_name: bool | None = None,
    ) -> Self:
        """The model the JSON text `json_data` declares, failing as every other way to build
        one does: a text that is not JSON (cut short, not UTF-8, with more after its object) is
        a ConfigurationError naming no field, where pydantic's own error, raised before any
        validator runs, would hold the whole text in its `errors()`."""
        try:
            return super().model_validate_json(
                json_data,
                strict=strict,
                extra=extra,
                context=context,
                by_alias=by_alias,
                by_name=by_name,
            )
        except ValidationError as error:
            first = error.errors(include_input=False, include_url=False)[0]
        raise _refused(cls, (), first["msg"], fix=_JSON_FIX)


def _refused(
    model: type[BaseModel],
    loc: tuple[int | str, ...],
    msg: str,
    *,
    preset: bool = False,
    fix: str | None = None,
) -> ConfigurationError:
    """The ConfigurationError for a failure of `model`'s field at `loc` (none when the value is
    not one at all), from pydantic's message, which holds no value, with `fix` or the field's
    own FIX. `preset` says whether a preset built the language."""
    who = _WHO[_library(model).__name__]
    field = str(loc[0]) if loc else None
    reason = msg.removeprefix("Value error, ")
    reason = reason[:1].lower() + reason[1:]
    where = "" if field is None else f" with its `{field}`"
    fix = fix or _fix(model, field, preset=preset)
    return ConfigurationError(
        f"{who} cannot run{where}: {reason}. FIX: {fix}", details={"field": field}
    )


def _library(model: type[BaseModel]) -> type[_Declared]:
    """The library's own class `model` is: itself, or the `Language` a team's subclass is
    built on, which says who is at fault and how each of its fields is fixed."""
    return Language if issubclass(model, Language) else VoiceAgent


def _fix(model: type[BaseModel], field: str | None, *, preset: bool) -> str:
    """How `field` of `model` is fixed: a field of the library's class by its own FIX (the
    notices' by the way the language was built), a field a team's subclass adds by its type, and
    a key no field has by removing it."""
    base = _library(model)
    if field is None:
        return _FIXES[base.__name__]
    if field in base.model_fields:
        return _NOTICES_FIX[preset] if field == "notices" else _FIXES[field]
    if field in model.model_fields:
        return f"correct `{field}`, the field {model.__name__} adds to {base.__name__}."
    *names, last = (f"`{name}`" for name in model.model_fields)
    return f"remove `{field}`: {_WHO[base.__name__].lower()} takes {', '.join(names)} and {last}."


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
    ) -> Self:
        """Saudi Arabic (`ar-SA`), opening each call with `greeting`; `notices` replaces the
        preset's text of each kind it names."""
        return cls._preset("ar-SA", greeting, notices)

    @classmethod
    def arabic(cls, *, greeting: str, notices: Mapping[NoticeKind, str] | None = None) -> Self:
        """Modern Standard Arabic (`ar`), opening each call with `greeting`; `notices` replaces
        the preset's text of each kind it names."""
        return cls._preset("ar", greeting, notices)

    @classmethod
    def english(cls, *, greeting: str, notices: Mapping[NoticeKind, str] | None = None) -> Self:
        """English (`en`), opening each call with `greeting`; `notices` replaces the preset's
        text of each kind it names."""
        return cls._preset("en", greeting, notices)

    @classmethod
    def _preset(cls, tag: LanguageTag, greeting: str, notices: object) -> Self:
        texts: object = notices if notices is not None else NOTICES[tag]
        if isinstance(notices, Mapping):
            texts = {**NOTICES[tag], **notices}
        fields = {"tag": tag, "greeting": greeting, "echo_frame": ECHO_FRAMES[tag]}
        return cls.model_validate(fields | {"notices": texts}, context=_FROM_PRESET)

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

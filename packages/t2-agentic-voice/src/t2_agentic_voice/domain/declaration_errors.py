"""How the declaration (domain/declaration.py) fails: what its models share (`Declared`:
frozen, a misspelt key an error, and any failure to build one a ConfigurationError naming the
field at fault, with its FIX line, and never the value it refused), each field's FIX, and who is
at fault, a language, the agent's vocabulary (domain/talker_declaration.py) or the agent, read
from the library's own class a team's subclass is built on.
"""

from __future__ import annotations

from typing import Any, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    ModelWrapValidatorHandler,
    ValidationError,
    ValidationInfo,
    model_validator,
)
from pydantic.config import ExtraValues

from t2_agentic_voice.core.errors import ConfigurationError

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
    "phrases": (
        "give `phrases` the presets' words, extended with the team's, as "
        'phrases=Phrases.defaults().extend(stop={"en": ["..."]}).'
    ),
    "progress": (
        f"map each progress line's key, a lowercase word, to its text {_PLAIN}, as "
        'progress={"searching": "..."}.'
    ),
    "instructions": (
        "give `instructions` one text, or a text for each language the agent speaks, keyed by "
        'its tag, as instructions={"ar-SA": ..., "en": ...}.'
    ),
    "tools": (
        "give `tools` the tools built with @tool, Tool.from_function, knowledge_tool or "
        "@action, each with its own name; a progress line a tool names and every text of an "
        "action are given in every language; a tool's reports_on names an action declared here."
    ),
    "vocabulary": 'give `vocabulary` its terms, as vocabulary=Vocabulary(terms=["VPN"]).',
    "Vocabulary": 'declare it as Vocabulary(terms=["VPN", "Outlook"]).',
    "terms": f'give each term {_PLAIN}, as a transcript should write it: terms=["VPN"].',
    "version": (
        'give `version` printable ASCII with no space, up to 64 characters, as "2026-11-06.1".'
    ),
    "time_zone": (
        "give `time_zone` a fixed offset from UTC, as time_zone=timedelta(hours=3) for Riyadh "
        "(UTC+3 all year), or timezone(timedelta(hours=3)); a zone's name is not taken."
    ),
}
# The notices' FIX, by the way the language was built: through its preset, which gives the text
# of each kind it is not given, or without one (`model_validate`), which gives none.
_NOTICES_FIX = {
    True: (
        f"give `notices` a text for `busy`, `error`, `cut_off` or `ended`, each {_PLAIN}, as "
        'notices={"ended": ...}; with a preset, a kind it leaves out keeps the preset\'s text.'
    ),
    False: (
        f"give `notices` a text for each of busy, error, cut_off and ended, each {_PLAIN}, as "
        'notices={"busy": ..., "error": ..., "cut_off": ..., "ended": ...}; or build the '
        "language with its preset, which gives the text of each kind left out."
    ),
}
# A text that is not JSON, given to `model_validate_json`.
_JSON_FIX = (
    "give `model_validate_json` one JSON object of its fields, as `model_dump_json()` writes."
)
_WHO = {"Language": "A language", "VoiceAgent": "The agent", "Vocabulary": "The vocabulary"}
# The validation context a preset builds its language in, so that a failure's FIX says what the
# preset gives.
FROM_PRESET = object()


class Declared(BaseModel):
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
        raise _refused(cls, first["loc"], first["msg"], preset=info.context is FROM_PRESET)

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


def _library(model: type[BaseModel]) -> type[Declared]:
    """The library's own class `model` is: itself, or the `Language` a team's subclass is
    built on, which says who is at fault and how each of its fields is fixed."""
    from t2_agentic_voice.domain.declaration import Language, VoiceAgent  # they build on this
    from t2_agentic_voice.domain.talker_declaration import Vocabulary

    if issubclass(model, Vocabulary):
        return Vocabulary
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
    listed = f"{', '.join(names)} and {last}" if names else last
    return f"remove `{field}`: {_WHO[base.__name__].lower()} takes {listed}."

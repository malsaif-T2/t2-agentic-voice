"""How the environment's names and texts become the settings' data, for `VoiceSettings.from_env`
(core/config.py), which alone reads them (ARCH-ENV): each setting's location by its name, the
setting an error falls in, and the values of several sources merged into nested data, a list
or a map decoded from JSON. Nothing here reads the environment; each function takes the model.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from types import UnionType
from typing import Any, Union, get_args, get_origin

from pydantic import BaseModel

from t2_agentic_voice.core.settings.base import setting_name

Problem = tuple[str, str]  # a setting's name, and why it cannot load


def group(annotation: object) -> type[BaseModel] | None:
    """The group a field's annotation is, or None for a setting."""
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return annotation
    return None


def leaves(model: type[BaseModel], location: tuple[str, ...] = ()) -> Iterable[tuple[str, ...]]:
    """The location of every setting of `model`, through its groups: ("groq", "api_key")."""
    for name, field in model.model_fields.items():
        if (kind := group(field.annotation)) is not None:
            yield from leaves(kind, (*location, name))
        else:
            yield (*location, name)


def locations(model: type[BaseModel]) -> dict[str, tuple[str, ...]]:
    """Every setting's location, by its name after the prefix: ("groq", "api_key") by
    `GROQ__API_KEY`."""
    return {setting_name(*loc, prefix=""): loc for loc in leaves(model)}


def leaf(model: type[BaseModel], location: Iterable[str | int]) -> tuple[str, ...]:
    """The setting an error's `loc` falls in: its groups and field, never a map's key or a list's
    index below it, which is part of the value (a key ID) rather than of its name."""
    found: list[str] = []
    current: type[BaseModel] | None = model
    for part in location:
        if current is None or not isinstance(part, str):
            break
        found.append(part)
        field = current.model_fields.get(part)
        current = None if field is None else group(field.annotation)
    return tuple(found)


def gathered(
    model: type[BaseModel], sources: Iterable[Mapping[str, str | None]], prefix: str
) -> tuple[dict[str, Any], list[str], list[Problem]]:
    """The values `sources` give, a later source winning, as `model`'s nested data, a JSON
    setting decoded; the names under the prefix that match no setting; and the settings that
    cannot load (named, never their values). A blank value counts as unset, under a known name
    or not, so a blank line left from an older `.env.example` changes nothing."""
    found = locations(model)
    strangers: list[str] = []
    problems: list[Problem] = []
    given: dict[tuple[str, ...], str] = {}
    for source in sources:
        named: set[tuple[str, ...]] = set()
        for name, value in source.items():
            location = found.get(name[len(prefix) :].upper())
            if value is None or value == "":
                continue
            if location is None:
                strangers.append(name)
            elif location in named:
                why = "is set twice, under names that differ only in case"
                problems.append((setting_name(*location, prefix=prefix), why))
            else:
                named.add(location)
                given[location] = value
    data: dict[str, Any] = {}
    for location, value in given.items():
        decoded = _decoded(model, location, value)
        if decoded is _NOT_JSON:
            problems.append((setting_name(*location, prefix=prefix), "is not valid JSON"))
            continue
        nested = data
        for part in location[:-1]:
            nested = nested.setdefault(part, {})
        nested[location[-1]] = decoded
    return data, strangers, problems


_NOT_JSON = object()


def _decoded(model: type[BaseModel], location: tuple[str, ...], value: str) -> object:
    """`value` as the setting at `location` takes it: decoded when the setting is a list or a
    map, given as JSON (`_NOT_JSON` when it is not JSON); otherwise the text itself."""
    for part in location[:-1]:
        model = group(model.model_fields[part].annotation) or model
    if not is_json(model.model_fields[location[-1]].annotation):
        return value
    try:
        return json.loads(value)
    except (ValueError, RecursionError):  # or nested deeper than the decoder goes
        return _NOT_JSON  # the decoder's error quotes the text: not chained


def is_json(annotation: object) -> bool:
    """Whether a setting of this annotation is given as JSON: a list, a tuple or a map."""
    kinds = get_args(annotation) if get_origin(annotation) in (Union, UnionType) else ()
    return any(get_origin(kind) in (tuple, list, dict, Mapping) for kind in kinds or (annotation,))

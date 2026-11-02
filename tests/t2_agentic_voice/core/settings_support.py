"""What the settings tests share (test_config.py, test_settings_errors.py, test_settings_checks.py,
test_settings_secrets.py, test_env_example.py, test_settings_ref.py): the prefix, made-up keys,
and one walk of the settings tree, so a new group shape changes one walker."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from pydantic import BaseModel
from pydantic.fields import FieldInfo
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.settings import base

PREFIX = base.PREFIX
MADE_UP_KEY = "gsk_made-up-key-for-tests-0123456789"
# A made-up shared secret of 40 bytes, over the 32 a join key or the TURN secret needs.
LONG_SECRET = "made-up-shared-secret-for-tests-01234567"


def fields(
    model: type[BaseModel] = VoiceSettings, location: tuple[str, ...] = ()
) -> Iterator[tuple[tuple[str, ...], object]]:
    """(location, annotation) of every leaf field, through the groups: ("groq", "api_key")."""
    for name, info in _infos(model, location):
        yield name, info.annotation


def _infos(
    model: type[BaseModel], location: tuple[str, ...]
) -> Iterator[tuple[tuple[str, ...], FieldInfo]]:
    for name, field in model.model_fields.items():
        kind = field.annotation
        if isinstance(kind, type) and issubclass(kind, BaseModel):
            yield from _infos(kind, (*location, name))
        else:
            yield (*location, name), field


def names() -> dict[str, tuple[str, ...]]:
    """Every environment name of the settings' fields, a group's nested with `__`, with the
    field's location."""
    return {PREFIX + "__".join(part.upper() for part in loc): loc for loc, _ in fields()}


def default_of(location: tuple[str, ...]) -> object:
    """The default the settings declare at `location`; None for `env`, which has none."""
    found = dict(_infos(VoiceSettings, ()))[location]
    return None if found.is_required() else found.get_default(call_default_factory=True)


def nested(location: tuple[str, ...], value: Any) -> dict[str, Any]:
    """`value` at `location`, as the settings' nested data: {"stt": {"model": value}}."""
    data: Any = value
    for part in reversed(location):
        data = {part: data}
    result: dict[str, Any] = data
    return result

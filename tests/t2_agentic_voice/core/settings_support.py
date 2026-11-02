"""What the settings tests share (test_config.py, test_env_example.py): the prefix, a made-up
key, and one walk of the settings tree, so a new group shape changes one walker."""

from __future__ import annotations

from collections.abc import Iterator

from pydantic import BaseModel
from t2_agentic_voice.core.config import Settings

PREFIX = Settings.model_config.get("env_prefix", "")
MADE_UP_KEY = "gsk_made-up-key-for-tests-0123456789"


def fields(
    model: type[BaseModel] = Settings, location: tuple[str, ...] = ()
) -> Iterator[tuple[tuple[str, ...], object]]:
    """(location, annotation) of every leaf field, through the groups: ("groq", "api_key")."""
    for name, field in model.model_fields.items():
        kind = field.annotation
        if isinstance(kind, type) and issubclass(kind, BaseModel):
            yield from fields(kind, (*location, name))
        else:
            yield (*location, name), kind


def names() -> dict[str, tuple[str, ...]]:
    """Every environment name of the settings' fields, a group's nested with `__`, with the
    field's location."""
    return {PREFIX + "__".join(part.upper() for part in loc): loc for loc, _ in fields()}

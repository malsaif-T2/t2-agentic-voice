"""`uv run poe settings-ref`: write docs/generated/settings.md and .env.example from the
library's settings model, `VoiceSettings` (core/config.py), so that neither is edited by hand
and neither drifts from the code (the design's 7.7; GP-11).

For each setting: its environment name, its type, its default, its unit (read from the unit
its name ends in, `_ms` or `_s`) and its description, the field's own (`Field(description=...)`);
a group's text is its class docstring. `.env.example` keeps its convention: every key blank,
its default in a `# Default:` line just above it, written as the setting reads it back, so a
copy pins no default (tests/t2_agentic_voice/core/test_env_example.py).

`render_reference()` and `render_env_example()` are the pure renderers that the command and
the freshness tests (tests/t2_agentic_voice/core/test_settings_ref.py) both call.
"""

from __future__ import annotations

import argparse
import inspect
import json
import sys
import textwrap
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import NoneType, UnionType
from typing import Annotated, Literal, Union, get_args, get_origin

from pydantic import BaseModel, SecretStr
from pydantic.fields import FieldInfo
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.settings.base import setting_name

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / "docs" / "generated" / "settings.md"
ENV_EXAMPLE = ROOT / ".env.example"
COMMAND = "uv run poe settings-ref"
# The default of a setting that has none (`env`).
REQUIRED = object()
_UNITS = {"_ms": "milliseconds", "_s": "seconds"}
_KINDS: dict[object, str] = {
    str: "text",
    int: "integer",
    float: "number",
    bool: "true or false",
    Path: "path",
    SecretStr: "secret",
}
_WIDTH = 100
_DESCRIPTION = "Write docs/generated/settings.md and .env.example from the library's settings."
_TABLE_HEAD = "| Variable | Type | Default | Unit | Description |\n| --- | --- | --- | --- | --- |"
_ENV_HEADER = f"""\
# Copy to `.env` and fill in. Never commit `.env`.
# Written by `{COMMAND}` from the library's VoiceSettings
# (packages/t2-agentic-voice/src/t2_agentic_voice/core/config.py): never edit it by hand, since
# tests/t2_agentic_voice/core/test_settings_ref.py fails when it is stale. The library reads a
# `.env` only when it is given one (VoiceSettings.from_env(env_file=...)), and environment
# variables override it. A group's keys nest with `__` (T2V_GROQ__API_KEY is
# settings.groq.api_key), a list or a map is JSON, and a blank value keeps the default. Every
# key below is blank, its default given in the comment just above it: write a value only to
# change one, so a copy follows a default that changes later. docs/generated/settings.md
# describes each setting in a table.
"""
_REFERENCE_HEADER = f"""\
# Settings reference

Written by `{COMMAND}` from the library's `VoiceSettings`
(`packages/t2-agentic-voice/src/t2_agentic_voice/core/config.py`), each description the field's
own; never edit it by hand (`tests/t2_agentic_voice/core/test_settings_ref.py` fails when it is
stale). The same command writes [.env.example](../../.env.example).

`VoiceSettings(env=..., ...)` built in code takes its defaults and the arguments given, and
nothing else. `VoiceSettings.from_env()` reads the environment variables below, under the prefix
`T2V_` unless `prefix=` gives another, and a `.env` file only when `env_file=` names one; the
environment wins over the file. A group's settings nest with `__`, a list or a map is given as
JSON, and a blank value counts as unset. A variable under the prefix that names no setting is
an error, so the prefix belongs to the library's settings alone. Each secret also takes a
`_FILE` setting naming a file that holds it, and never shows in a repr, a log line or an error.
A unit is read from the name: `_ms` is milliseconds, `_s` seconds.
"""


@dataclass(frozen=True)
class Setting:
    """One setting as the reference shows it."""

    location: tuple[str, ...]
    field: FieldInfo

    @property
    def name(self) -> str:
        return setting_name(*self.location)

    @property
    def unit(self) -> str:
        last = self.location[-1]
        return next((unit for end, unit in _UNITS.items() if last.endswith(end)), "")

    @property
    def description(self) -> str:
        return " ".join((self.field.description or "").split())

    def default(self) -> object:
        """The declared default, `REQUIRED` for a setting that has none."""
        if self.field.is_required():
            return REQUIRED
        return self.field.get_default(call_default_factory=True)


def groups() -> Iterator[tuple[str, str, list[Setting]]]:
    """Each group of the settings, the top level first: its name ("" for the top level), its
    text, and its settings."""
    top = [Setting((name,), f) for name, f in VoiceSettings.model_fields.items() if not _model(f)]
    yield "", "", top
    for name, field in VoiceSettings.model_fields.items():
        if (group := _model(field)) is not None:
            text = " ".join((inspect.getdoc(group) or "").split())
            yield name, text, [Setting((name, n), f) for n, f in group.model_fields.items()]


def _model(field: FieldInfo) -> type[BaseModel] | None:
    kind = field.annotation
    return kind if isinstance(kind, type) and issubclass(kind, BaseModel) else None


def type_text(annotation: object) -> str:
    """What a setting of `annotation` takes, in words."""
    origin, args = get_origin(annotation), get_args(annotation)
    if origin in (Union, UnionType):
        kinds = [type_text(arg) for arg in args if arg is not NoneType]
        return " or ".join(kinds) + (", or unset" if NoneType in args else "")
    if origin is Annotated:
        return type_text(args[0])
    if origin is Literal:
        return "one of " + ", ".join(str(arg) for arg in args)
    if origin in (tuple, list):
        return f"JSON list of {type_text(args[0])}"
    if origin is dict:
        return f"JSON object from {type_text(args[0])} to {type_text(args[1])}"
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return "{" + ", ".join(annotation.model_fields) + "}"
    return _KINDS[annotation]


def default_text(value: object) -> str | None:
    """A default as a variable would give it, so a setting reads it back as the same value;
    None for one with nothing to give (unset, an empty list or map, or required)."""
    if value is REQUIRED or value is None or value in ((), {}):
        return None
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, float):
        return f"{value:g}"
    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, dict):
        jsonable = {k: v.model_dump() if isinstance(v, BaseModel) else v for k, v in value.items()}
        return json.dumps(jsonable)
    return str(value)


def render_env_example() -> str:
    """.env.example: every setting, blank, under its description and its default."""
    lines = [_ENV_HEADER.rstrip("\n")]
    for _, text, settings in groups():
        lines.append("")
        lines += _comment(text) if text else []
        for setting in settings:
            lines += _comment(setting.description)
            default = default_text(setting.default())
            lines += [] if default is None else [f"# Default: {default}"]
            lines.append(f"{setting.name}=")
    return "\n".join(lines) + "\n"


def _comment(text: str) -> list[str]:
    return ["# " + line for line in textwrap.wrap(text, _WIDTH - 2, break_on_hyphens=False)]


def render_reference() -> str:
    """docs/generated/settings.md: a table of each group's settings."""
    lines = [_REFERENCE_HEADER.rstrip("\n")]
    for name, text, settings in groups():
        lines += ["", f"## `{name}`" if name else "## The top level", ""]
        lines += [text, ""] if text else []
        lines += [_TABLE_HEAD]
        for setting in settings:
            default = _default_cell(setting.default())
            cells = [f"`{setting.name}`", type_text(setting.field.annotation), default]
            cells += [setting.unit or "—", setting.description]
            lines.append("| " + " | ".join(cell.replace("|", "\\|") for cell in cells) + " |")
    return "\n".join(lines) + "\n"


def _default_cell(value: object) -> str:
    """A default as the reference's table shows it: a value as code, or in words."""
    text = default_text(value)
    if text is not None:
        return f"`{text}`"
    if value is REQUIRED:
        return "required"
    if value is None:
        return "unset"
    return "`[]`" if isinstance(value, tuple) else "`{}`"


def main(argv: Sequence[str] | None = None) -> int:
    """Write both files, with LF line endings."""
    parser = argparse.ArgumentParser(prog="poe settings-ref", description=_DESCRIPTION)
    parser.parse_args(argv)
    REFERENCE.write_bytes(render_reference().encode("utf-8"))
    ENV_EXAMPLE.write_bytes(render_env_example().encode("utf-8"))
    print(f"Wrote {REFERENCE.relative_to(ROOT).as_posix()} and {ENV_EXAMPLE.name}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

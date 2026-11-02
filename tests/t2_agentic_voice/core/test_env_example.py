"""`.env.example` lists every setting, each key blank with its default in the comment above it,
so a `.env` copied from it pins no default (GP-04, GP-18)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from pydantic import SecretStr
from t2_agentic_voice.core.config import Settings

from tests.t2_agentic_voice.core.settings_support import MADE_UP_KEY, PREFIX, names

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_LINE = re.compile(r"# Default: (.+)")


def _example() -> dict[str, tuple[str, str | None]]:
    """Each key `.env.example` sets: its value, and the default the comment line just above it
    gives (`# Default: <value>`), None when that line gives none."""
    lines = (ROOT / ".env.example").read_text(encoding="utf-8").splitlines()
    found: dict[str, tuple[str, str | None]] = {}
    for above, line in zip(["", *lines], lines, strict=False):
        if "=" in line and not line.lstrip().startswith("#"):
            name, _, value = line.partition("=")
            default = DEFAULT_LINE.fullmatch(above)
            found[name.strip()] = (value, default[1] if default else None)
    return found


def _at(settings: Settings, location: tuple[str, ...]) -> object:
    """The value of the setting at `location`."""
    value: object = settings
    for part in location:
        value = getattr(value, part)
    return value


def test_env_example_lists_every_setting() -> None:
    documented, expected = set(_example()), set(names())
    assert documented == expected, (
        "Keep .env.example in sync with Settings in core/config.py: "
        f"missing={sorted(expected - documented)} unknown={sorted(documented - expected)}. "
        "FIX: add each missing key, blank, under a comment saying what it is and its default; "
        "remove each unknown one."
    )


@pytest.mark.parametrize("name", sorted(names()))
def test_env_example_leaves_each_key_blank_and_gives_its_default(
    name: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A copy of `.env.example` pins no default: when one changes on a registered measurement
    (GP-18), a `.env` copied from it follows. The default each comment gives is the one the
    settings declare, read as the settings read the variable; a setting with no default (none,
    or an empty list) gives none."""
    value, default = _example()[name]
    location = names()[name]
    declared = _at(Settings.model_construct(), location)
    assert value == "", (
        f"{name} is set to a value in .env.example, so a copy pins it. FIX: leave it blank, and "
        "give the default in a `# Default: <value>` line just above it."
    )
    if default is None:
        assert declared in (None, ()), f"FIX: give {name}'s default in a `# Default:` line."
        return
    monkeypatch.setenv(name, default)
    assert _at(Settings(_env_file=None), location) == declared, (
        f"{name}'s comment gives the default {default!r}, but the settings declare "
        f"{declared!r}. FIX: correct the `# Default:` line above it."
    )


def test_env_example_as_a_dotenv_holds_the_defaults(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`.env.example` says "Copy to `.env` and fill in": a copy with only the key filled in
    keeps every other setting at its default. Without the session's scratch var dir, so the
    file's own var dir is read too."""
    monkeypatch.delenv(f"{PREFIX}VAR_DIR")
    example = (ROOT / ".env.example").read_text(encoding="utf-8")
    defaults = Settings(_env_file=None).model_dump()
    assert Settings(_env_file=ROOT / ".env.example").model_dump() == defaults
    copy = tmp_path / ".env"
    key_line = f"{PREFIX}GROQ__API_KEY="
    assert key_line + "\n" in example
    copy.write_text(example.replace(key_line, key_line + MADE_UP_KEY), encoding="utf-8")
    filled = Settings(_env_file=copy)
    assert filled.groq.resolved_api_key() == SecretStr(MADE_UP_KEY)
    assert filled.model_dump() | {"groq": defaults["groq"]} == defaults

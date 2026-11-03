"""`uv run poe settings-ref` (scripts/settings_ref.py): docs/generated/settings.md and
.env.example are written from the settings model, and the committed files are what it writes
now (the freshness tests, GP-11), so the code and the reference cannot drift (the design's
7.7)."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal

import pytest
from pydantic import Field, SecretStr
from t2_agentic_voice.core.settings.tts import TtsVoice

from scripts import settings_ref
from scripts.settings_ref import default_text, render_env_example, render_reference, type_text
from tests.t2_agentic_voice.core.settings_support import PREFIX, names

FIX = "FIX: run `uv run poe settings-ref`, then commit both files."


def test_the_committed_settings_reference_is_fresh() -> None:
    assert settings_ref.REFERENCE.parent.name == "generated"
    assert settings_ref.REFERENCE.read_bytes() == render_reference().encode("utf-8"), (
        f"docs/generated/settings.md is stale.\n    {FIX}"
    )


def test_the_committed_env_example_is_fresh() -> None:
    assert settings_ref.ENV_EXAMPLE.read_bytes() == render_env_example().encode("utf-8"), (
        f".env.example is stale.\n    {FIX}"
    )


def test_the_reference_has_a_row_for_every_setting_with_its_unit() -> None:
    page = render_reference()
    rows = [line for line in page.splitlines() if line.startswith(f"| `{PREFIX}")]
    assert [row.split("`")[1] for row in rows] == list(names())
    row = next(r for r in rows if r.startswith(f"| `{PREFIX}TURNS__VAD_STOP_MS`"))
    assert row.split(" | ")[1:4] == ["integer", "`200`", "milliseconds"]
    row = next(r for r in rows if r.startswith(f"| `{PREFIX}ENV`"))
    assert row.split(" | ")[1:4] == ["one of dev, test, staging, prod", "required", "—"]
    row = next(r for r in rows if r.startswith(f"| `{PREFIX}LIMITS__MAX_CALL_S`"))
    assert row.split(" | ")[1:4] == ["number", "`600`", "seconds"]
    assert all(line.count("|") == 6 for line in rows), "a description holds an unescaped |"


@pytest.mark.parametrize(
    ("annotation", "text"),
    [
        (str | None, "text, or unset"),
        (Annotated[str, Field(pattern="x")] | None, "text, or unset"),
        (Literal["a", "b"], "one of a, b"),
        (tuple[str, ...], "JSON list of text"),
        (dict[str, SecretStr], "JSON object from text to secret"),
        (dict[Literal["en"], TtsVoice], "JSON object from one of en to {model, voice}"),
        (bool, "true or false"),
        (Path | None, "path, or unset"),
    ],
)
def test_each_type_is_said_in_words(annotation: object, text: str) -> None:
    assert type_text(annotation) == text


@pytest.mark.parametrize(
    ("value", "text"),
    [
        (settings_ref.REQUIRED, None),
        (None, None),
        ((), None),
        ({}, None),
        (True, "true"),
        (6.0, "6"),
        (0.7, "0.7"),
        (200, "200"),
        (Path("var"), "var"),
        (
            {"en": TtsVoice(model="canopylabs/orpheus-v1-english", voice="troy")},
            '{"en": {"model": "canopylabs/orpheus-v1-english", "voice": "troy"}}',
        ),
    ],
)
def test_a_default_is_written_as_a_variable_gives_it(value: object, text: str | None) -> None:
    """As text a setting reads back as the same value (test_env_example.py checks each); none
    for a setting with nothing to give."""
    assert default_text(value) == text


def test_the_command_writes_both_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    reference, example = tmp_path / "settings.md", tmp_path / ".env.example"
    monkeypatch.setattr(settings_ref, "REFERENCE", reference)
    monkeypatch.setattr(settings_ref, "ENV_EXAMPLE", example)
    monkeypatch.setattr(settings_ref, "ROOT", tmp_path)
    assert settings_ref.main([]) == 0
    assert reference.read_bytes() == render_reference().encode("utf-8")
    assert example.read_bytes() == render_env_example().encode("utf-8")
    assert b"\r\n" not in reference.read_bytes() + example.read_bytes()

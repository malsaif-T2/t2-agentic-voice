"""`.env.example` lists the Ole5 app's own settings after the library's, each blank, with its
default or "Required." just above it, so one file holds every line a developer's `.env` needs
(the owner, 2026-11-16). `uv run poe settings-ref` writes it (scripts/settings_ref.py)."""

from __future__ import annotations

from pathlib import Path

from ole5_voice.settings import AppSettings

from scripts.settings_ref import app_settings, default_text

ROOT = Path(__file__).resolve().parents[2]


def _lines() -> list[str]:
    return (ROOT / ".env.example").read_text(encoding="utf-8").splitlines()


def test_every_app_setting_is_listed_blank_once() -> None:
    lines = _lines()
    for _, rows in app_settings():
        for name, _field in rows:
            assert lines.count(f"{name}=") == 1, f"FIX: run `uv run poe settings-ref` ({name})"
    (ole5,) = [rows for text, rows in app_settings() if text.startswith("The Ole5 app's")]
    assert len({name for name, _ in ole5}) == len(AppSettings.model_fields)


def test_each_app_setting_gives_its_default_or_says_it_is_required() -> None:
    lines = _lines()
    for _, rows in app_settings():
        for name, field in rows:
            above = lines[lines.index(f"{name}=") - 1]
            if field.is_required():
                assert above == "# Required.", name
                continue
            default = default_text(field.get_default(call_default_factory=True))
            if default is None:
                assert not above.startswith("# Default:"), name
            else:
                assert above == f"# Default: {default}", name

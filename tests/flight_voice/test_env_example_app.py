"""`.env.example` lists the flight agent's own settings after the library's and Ole5's, each
blank, with its default or "Required." just above it, so one file holds every line a developer's
`.env` needs. `uv run poe settings-ref` writes it (scripts/settings_ref.py)."""

from __future__ import annotations

from pathlib import Path

from flight_voice.settings import PREFIX, AppSettings
from pydantic.fields import FieldInfo

from scripts.settings_ref import app_settings, default_text

ROOT = Path(__file__).resolve().parents[2]


def _rows() -> list[tuple[str, FieldInfo]]:
    (rows,) = [rows for text, rows in app_settings() if "FLIGHT_VOICE_" in text]
    return rows


def test_every_flight_setting_is_listed_blank_once_under_its_prefix() -> None:
    lines = (ROOT / ".env.example").read_text(encoding="utf-8").splitlines()
    rows = _rows()
    assert [name for name, _ in rows] == [PREFIX + f.upper() for f in AppSettings.model_fields]
    for name, field in rows:
        assert lines.count(f"{name}=") == 1, f"FIX: run `uv run poe settings-ref` ({name})"
        above = lines[lines.index(f"{name}=") - 1]
        if field.is_required():
            assert above == "# Required.", name
            continue
        default = default_text(field.get_default(call_default_factory=True))
        if default is None:
            assert not above.startswith("# Default:"), name
        else:
            assert above == f"# Default: {default}", name

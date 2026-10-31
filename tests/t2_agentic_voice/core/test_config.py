"""Settings: typed, prefixed, and listed in .env.example."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError
from t2_agentic_voice.core.config import Settings, get_settings

ROOT = Path(__file__).resolve().parents[3]
PREFIX = Settings.model_config.get("env_prefix", "")


def test_defaults_boot_without_a_dotenv() -> None:
    settings = Settings(_env_file=None)
    assert (settings.env, settings.log_level, settings.log_format) == ("dev", "INFO", "console")


def test_reads_prefixed_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(f"{PREFIX}LOG_LEVEL", "DEBUG")
    assert Settings(_env_file=None).log_level == "DEBUG"


def test_rejects_invalid_values(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(f"{PREFIX}LOG_LEVEL", "LOUD")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_get_settings_is_loaded_once() -> None:
    """Under tests/conftest.py, it reads no `.env` and no variable from the shell."""
    assert get_settings() is get_settings()


def test_env_example_lists_every_setting() -> None:
    lines = (ROOT / ".env.example").read_text(encoding="utf-8").splitlines()
    documented = {
        line.split("=", 1)[0].strip()
        for line in lines
        if "=" in line and not line.lstrip().startswith("#")
    }
    expected = {f"{PREFIX}{name.upper()}" for name in Settings.model_fields}
    assert documented == expected, (
        "Keep .env.example in sync with Settings in core/config.py: "
        f"missing={sorted(expected - documented)} unknown={sorted(documented - expected)}. "
        "FIX: add each missing key with a comment saying what it is; remove each unknown one."
    )

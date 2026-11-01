"""Fixtures for the whole suite. No test reads the developer's `.env`, inherits this project's
settings or a provider's variables from their shell, or writes their `var/`
(tests/harness/test_isolation.py checks each)."""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from t2_agentic_voice.core.config import Settings, get_settings

# This project's environment variables, and the one that moves every runtime path.
PREFIX = Settings.model_config.get("env_prefix", "")
VAR_DIR_VARIABLE = f"{PREFIX}VAR_DIR"
# The variables of the providers' SDKs and of the tracing tools, which the library never reads
# (the design's 7.3) but their SDKs would: a real key, an exporter's headers, Phoenix's own.
FOREIGN_PREFIXES = ("GROQ_", "OTEL_", "PHOENIX_")


@pytest.fixture(scope="session", autouse=True)
def _isolated_settings(tmp_path_factory: pytest.TempPathFactory) -> Iterator[None]:
    """Every Settings a test builds starts from the defaults, whatever the developer's machine
    holds:
    - no `.env`: the env file is switched off, for `Settings()` and `get_settings()` alike (a
      test of `.env` parsing passes its own file as `_env_file=`);
    - no variable with this project's prefix from the shell (a debug level, `prod`);
    - no `GROQ_*`, `OTEL_*` or `PHOENIX_*` variable from the shell, so a real key or exporter
      setting never reaches a test (a test sets made-up ones with monkeypatch);
    - a scratch var_dir, so no test opens the developer's var/.
    Add here any other variable a test must never inherit."""
    with pytest.MonkeyPatch.context() as patch:
        patch.setitem(Settings.model_config, "env_file", None)
        if PREFIX:  # with no prefix, every variable would be a setting
            for name in [n for n in os.environ if n.upper().startswith(PREFIX.upper())]:
                patch.delenv(name)
        for name in [n for n in os.environ if n.upper().startswith(FOREIGN_PREFIXES)]:
            patch.delenv(name)
        patch.setenv(VAR_DIR_VARIABLE, str(tmp_path_factory.mktemp("default-var")))
        get_settings.cache_clear()
        yield
        get_settings.cache_clear()


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    """Isolated settings: never reads the developer's .env file or var/."""
    return Settings(_env_file=None, env="test", var_dir=tmp_path / "var")

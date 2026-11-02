"""Fixtures for the whole suite. No test reads the developer's `.env`, inherits this project's
settings or a provider's variables from their shell, or writes their `var/`
(tests/harness/test_isolation.py checks each); and every test starts with the default logging.
The variables dropped are listed in tests/isolation.py."""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from t2_agentic_voice.core.config import Settings, get_settings
from t2_agentic_voice.core.logging import configure_logging

from tests.isolation import VAR_DIR_VARIABLE, dropped


def pytest_configure(config: pytest.Config) -> None:
    """Drop the shell's variables before any test module is imported. The session fixture below
    runs only after collection, and some are read when a package is imported: `GROQ_LOG` by
    `groq` (it then sets the `groq` and `httpx` loggers to DEBUG and adds a root handler) and
    `OTEL_PYTHON_CONTEXT` by `opentelemetry.context` (it loads an entry point by that name), as
    plan 002's step 2 read them (tests/harness/test_import_isolation.py checks it)."""
    for name in [n for n in os.environ if dropped(n)]:
        del os.environ[name]


@pytest.fixture(scope="session", autouse=True)
def _isolated_settings(tmp_path_factory: pytest.TempPathFactory) -> Iterator[None]:
    """Every Settings a test builds starts from the defaults, whatever the developer's machine
    holds:
    - no `.env`: the env file is switched off, for `Settings()` and `get_settings()` alike (a
      test of `.env` parsing passes its own file as `_env_file=`);
    - no variable with this project's prefix from the shell (a debug level, `prod`);
    - no `GROQ_*`, `OTEL_*` or `PHOENIX_*` variable from the shell, so a real key or exporter
      setting never reaches a test (a test sets made-up ones with monkeypatch);
    - no CA bundle of requests' from the shell, and `NETRC` naming an empty file, so requests
      never opens the developer's `~/.netrc`;
    - a scratch var_dir, so no test opens the developer's var/.
    `pytest_configure` above drops the same variables before collection; one set after it is
    dropped here. Add any other variable a test must never inherit to tests/isolation.py."""
    with pytest.MonkeyPatch.context() as patch:
        patch.setitem(Settings.model_config, "env_file", None)
        for name in [n for n in os.environ if dropped(n)]:
            patch.delenv(name)
        netrc = tmp_path_factory.mktemp("netrc") / "netrc"
        netrc.write_text("", encoding="utf-8")
        patch.setenv("NETRC", str(netrc))
        patch.setenv(VAR_DIR_VARIABLE, str(tmp_path_factory.mktemp("default-var")))
        get_settings.cache_clear()
        yield
        get_settings.cache_clear()


@pytest.fixture(autouse=True)
def _default_logging() -> None:
    """structlog's configuration is process-wide: each test starts from `configure_logging()`'s
    defaults (INFO, plain console lines), whatever an earlier test or command configured."""
    configure_logging()


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    """Isolated settings: never reads the developer's .env file or var/."""
    return Settings(_env_file=None, env="test", var_dir=tmp_path / "var")

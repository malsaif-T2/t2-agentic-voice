"""Fixtures for the whole suite. No test reads the developer's `.env`, inherits this project's
settings or a provider's variables from their shell, writes their `var/`, or lets aiortc ask a
STUN server beyond this machine (tests/harness/test_isolation.py checks each); and every test
starts with the default logging. The variables dropped are listed in tests/isolation.py.

This module imports nothing of the library at its top, so the variables are dropped before the
library, or any package under it, is imported; its fixtures import what they need."""

from __future__ import annotations

import logging
import os
from collections.abc import Callable, Iterator, Mapping
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from tests.isolation import (
    DEFAULT_ICE_SERVERS,
    IMPORTED_BEFORE_DROP,
    SET,
    VAR_DIR_VARIABLE,
    drop_shell,
    dropped,
    refuse_default_ice_servers,
)

if TYPE_CHECKING:
    from t2_agentic_voice.core.config import VoiceSettings


def pytest_configure(config: pytest.Config) -> None:
    """Drop the shell's variables before any test module is imported, and before anything this
    module imports reads one. The session fixture below runs only after collection, and some
    are read when a package is imported: `GROQ_LOG` by `groq` (it then sets the `groq` and
    `httpx` loggers to DEBUG and adds a root handler) and `OTEL_PYTHON_CONTEXT` by
    `opentelemetry.context` (it loads an entry point by that name), as plan 002's step 2 read
    them; Pipecat's, loguru's and websockets' own, and `OTEL_PROPAGATORS` by fastapi, as plan
    003's reading of step 4 found (tests/harness/test_import_isolation.py checks it). It keeps
    what was imported before it for tests/harness/test_isolation.py."""
    config.stash[IMPORTED_BEFORE_DROP] = drop_shell(os.environ)


@pytest.fixture(scope="session", autouse=True)
def _isolated_settings(tmp_path_factory: pytest.TempPathFactory) -> Iterator[None]:
    """Every VoiceSettings a test loads starts from the defaults, whatever the developer's
    machine holds:
    - no `.env`: the library reads one only when `from_env(env_file=...)` names it, and the
      Ole5 app's eval commands, which read the working folder's when `--env-file` names none,
      read none here (a test of `.env` parsing passes its own file);
    - no variable with this project's prefixes from the shell, the library's or the Ole5
      app's (a debug level, `prod`, an access code);
    - no `GROQ_*`, `OTEL_*` or `PHOENIX_*` variable from the shell, so a real key or exporter
      setting never reaches a test (a test sets made-up ones with monkeypatch), and none that
      changes what a call's packages do (Pipecat's, loguru's, uvicorn's, FastAPI's and the
      rest of tests/isolation.py);
    - `.env` loading off in python-dotenv's `load_dotenv`, a second guard on Pipecat's runner;
    - no CA bundle of requests' from the shell, and `NETRC` naming an empty file, so requests
      never opens the developer's `~/.netrc`;
    - a scratch var_dir for `from_env`, so no test opens the developer's var/ (settings built
      in code take the `settings` fixture's, or their own), which a child process given
      `child_shell()` takes too.
    `pytest_configure` above drops the same variables before collection; one set after it is
    dropped here. Add any other variable a test must never inherit to tests/isolation.py."""
    # Imported here, after `pytest_configure`: it imports `groq` and OpenTelemetry, which read
    # their variables on import.
    from ole5_voice.evals import run_settings

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(run_settings, "DOTENV", None)
        for name in [n for n in os.environ if dropped(n)]:
            patch.delenv(name)
        for name, value in SET.items():
            patch.setenv(name, value)
        netrc = tmp_path_factory.mktemp("netrc") / "netrc"
        netrc.write_text("", encoding="utf-8")
        patch.setenv("NETRC", str(netrc))
        patch.setenv(VAR_DIR_VARIABLE, str(tmp_path_factory.mktemp("default-var")))
        yield


@pytest.fixture(scope="session", autouse=True)
def _no_default_ice_servers() -> Iterator[None]:
    """aiortc asks Google's STUN server when a peer is given no ICE servers of its own (plan
    003's reading of step 4), while the library contacts nothing beyond its outbound hosts (the
    design's 11). So for the whole session that default list raises, and a peer built without
    `RTCConfiguration(iceServers=[])` fails its test instead of sending a packet. This module
    imports nothing of aiortc at its top, which would come before the shell is dropped, so it is
    patched by name; importing it, and PyAV under it, adds under a second to the session's
    start."""
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(DEFAULT_ICE_SERVERS, classmethod(refuse_default_ice_servers))
        yield


@pytest.fixture(autouse=True)
def _default_logging() -> Iterator[Callable[[], None]]:
    """Each test starts with the logging an app's `configure_logging` call gives (INFO, plain
    console lines on standard output) for the library's loggers and each app's (`APP_LOGGERS`:
    its package's and `__main__`, which its commands configure with the library's), and what
    the test or a command it ran did to any logger is undone after: its handlers, its level,
    whether it propagates. The root logger is pytest's and is left alone. It gives what undoes
    the call itself (`unconfigured_logging`)."""
    from ole5_voice import LOGGERS as APP_LOGGERS
    from t2_agentic_voice.core.logging import configure_logging

    before = _logger_states()
    configure_logging(loggers=APP_LOGGERS)
    yield partial(_restore, before)
    _restore(before)


@pytest.fixture
def unconfigured_logging(_default_logging: Callable[[], None]) -> None:
    """Logging as a new process finds it, before any app configured it: nothing on the
    library's or an app's loggers but the library's `NullHandler`, and no level of their own."""
    _default_logging()


_State = tuple[int, list[logging.Handler], bool, bool]


def _logger_states() -> dict[str, _State]:
    """Each logger made so far, the root logger aside, by name: its level, handlers, whether it
    propagates and whether it is disabled."""
    made = logging.Logger.manager.loggerDict.items()
    return {
        name: (one.level, list(one.handlers), one.propagate, one.disabled)
        for name, one in list(made)
        if isinstance(one, logging.Logger)
    }


def _restore(states: Mapping[str, _State]) -> None:
    """Each logger as `states` holds it; one made since takes a new logger's state, keeping only
    the `NullHandler` a library adds to its own when it is imported."""
    for name, (level, handlers, propagate, disabled) in _logger_states().items():
        if name not in states:
            level, propagate, disabled = logging.NOTSET, True, False
            handlers = [h for h in handlers if isinstance(h, logging.NullHandler)]
        else:
            level, handlers, propagate, disabled = states[name]
        logger = logging.getLogger(name)
        logger.setLevel(level)
        logger.handlers[:] = handlers
        logger.propagate, logger.disabled = propagate, disabled


@pytest.fixture
def settings(tmp_path: Path) -> VoiceSettings:
    """Settings for a test, built in code: `env=test`, and a var_dir of the test's own, never
    the developer's var/."""
    from t2_agentic_voice.core.config import VoiceSettings
    from t2_agentic_voice.core.settings.storage import StorageSettings

    return VoiceSettings(env="test", storage=StorageSettings(var_dir=tmp_path / "var"))

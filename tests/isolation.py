"""What the suite keeps from the developer's machine, in one place: tests/conftest.py drops the
shell's variables listed here before the library or any package under it is imported, and makes
aiortc's default ICE servers refuse; a test that starts a child process gives it the same shell
(`child_shell`). tests/harness/test_isolation.py and test_import_isolation.py keep lists of their
own, as checks of these that do not rest on them.

This module imports nothing of the library, so that conftest can import it before anything reads
a variable; tests/harness/test_isolation.py ties its names to the library's.
"""

from __future__ import annotations

import os
import sys
from collections.abc import MutableMapping

import pytest

# This project's prefix (the library's `PREFIX`), and the variable that moves every runtime path
# among this project's (`setting_name("storage", "var_dir")`).
PREFIX = "T2V_"
VAR_DIR_VARIABLE = f"{PREFIX}STORAGE__VAR_DIR"
# The variables of the providers' SDKs and of the tracing tools, which the library never reads
# (the design's 7.3) but their SDKs would: a real key, an exporter's headers, Phoenix's own.
# FastAPI reads `OTEL_*` too: `OTEL_PROPAGATORS` when it is imported (it loads the entry points
# the variable names), and the exporters' variables when its own telemetry configures itself.
FOREIGN_PREFIXES = ("GROQ_", "OTEL_", "PHOENIX_")
# Variables of the HTTP clients under the SDKs, which change what a request to 127.0.0.1 trusts:
# requests replaces `verify=True` with either CA bundle (TD-004).
FOREIGN_NAMES = ("REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE")
# The variables of a call's packages that change what they do whatever the code passes (plan
# 003's reading of the installed packages, item 17 of its changes), by package:
# - Pipecat reads its own when a module is imported or a worker is set up, with no argument that
#   overrides them: a script run inside every call (`PIPECAT_SETUP_FILES`), every turn's audio
#   written under the working folder (`PIPECAT_SMART_TURN_LOG_DATA`), the data channel's chunk
#   size for the whole process (a bad value fails the import), and the defaults of its model
#   services and its WebSocket transports;
# - loguru reads its own when it is imported: its default sink's level, format and diagnosis, a
#   level's number for the whole process, and a value of the wrong kind fails the import;
# - websockets reads its limits and its headers when it is imported (Pipecat's service bases
#   import it), and a limit that is not a number fails the import;
# - uvicorn's command line takes every option from `UVICORN_*`, and its `Config` takes the
#   trusted proxies and the number of workers from the two names below when the code passes
#   none;
# - FastAPI adds exporters at lifespan start unless the app's own telemetry setting says
#   otherwise, and reads its frontend's folder;
# - onnxruntime takes a session's options from the model's file, an override neither Silero nor
#   Smart Turn passes;
# - numba and llvmlite read theirs when they are imported, and openai its log level when it is
#   imported and its organisation's and project's headers when a client is built: only parts of
#   Pipecat the library does not import reach them (its resampy resampler, its provider
#   services), so they are dropped in case one is imported anyway.
CALL_PREFIXES = ("PIPECAT_", "LOGURU_", "WEBSOCKETS_", "UVICORN_", "NUMBA_", "LLVMLITE_", "OPENAI_")
CALL_NAMES = (
    "FORWARDED_ALLOW_IPS",
    "WEB_CONCURRENCY",
    "FASTAPI_OTEL_AUTO_CONFIGURE",
    "FASTAPI_ENV",
    "ORT_LOAD_CONFIG_FROM_MODEL",
)
# Every prefix and name dropped from the shell: the providers', the tracing tools', the call's
# packages' and this project's own.
DROPPED_PREFIXES = (*FOREIGN_PREFIXES, *CALL_PREFIXES, PREFIX)
DROPPED_NAMES = (*FOREIGN_NAMES, *CALL_NAMES)
# Set for the session, a second guard on Pipecat's runner, which the library never imports:
# python-dotenv's `load_dotenv` loads nothing while it is set. `pipecat.runner.run` calls it
# when imported, with override, and finds a `.env` by walking up from the working folder, a walk
# that passes the main checkout's root from a worktree. It does not stop `dotenv_values`, which
# `from_env(env_file=...)` reads with.
SET = {"PYTHON_DOTENV_DISABLED": "1"}
# The packages that read a dropped variable when they are imported, and the repository's own,
# which import them: none of them is imported yet when conftest drops the variables.
READERS = (
    "t2_agentic_voice",
    "ole5_voice",
    "minimal_example",
    "groq",
    "opentelemetry",
    "fastapi",
    "uvicorn",
    "pipecat",
    "loguru",
    "websockets",
    "aiortc",
    "onnxruntime",
    "numba",
    "llvmlite",
    "openai",
)
# What `pytest_configure` saw of READERS before it dropped the variables.
IMPORTED_BEFORE_DROP = pytest.StashKey[list[str]]()
# aiortc's default ICE servers, Google's STUN server, which it asks when a peer is given no list
# of its own (plan 003's reading of step 4): conftest makes this raise for the whole session.
DEFAULT_ICE_SERVERS = "aiortc.rtcicetransport.RTCIceGatherer.getDefaultIceServers"


def dropped(name: str) -> bool:
    """Whether the suite drops the variable `name` from the shell, in any case."""
    return name.upper().startswith(DROPPED_PREFIXES) or name.upper() in DROPPED_NAMES


def drop_shell(environ: MutableMapping[str, str]) -> list[str]:
    """Drop every variable the suite drops from `environ` and set `SET` there; the packages of
    READERS imported before it, which may have read them already."""
    for name in [n for n in environ if dropped(n)]:
        del environ[name]
    environ.update(SET)
    return sorted(name for name in READERS if name in sys.modules)


def child_shell() -> dict[str, str]:
    """The shell of a child process: this one's, which the suite has cleaned, without any
    `PYTHON*` variable (a warnings filter, say), and with `SET`."""
    shell = {k: v for k, v in os.environ.items() if not dropped(k) and not k.startswith("PYTHON")}
    return shell | SET


def refuse_default_ice_servers(cls: type) -> list[object]:
    """aiortc's default ICE servers, refused: the peer was built with no list of its own."""
    raise RuntimeError(
        f"{cls.__name__}.getDefaultIceServers was called: a peer with no ICE servers of its own "
        "asks a STUN server beyond this machine. FIX: build it with "
        "RTCConfiguration(iceServers=[])."
    )

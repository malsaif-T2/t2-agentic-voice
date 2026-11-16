"""Tests never touch the developer's machine state: their .env, this project's variables in
their shell (the library's and the Ole5 app's), a provider's or a tracing tool's variables
(GROQ_*, OTEL_*, PHOENIX_*), the variables that change what a call's packages do (Pipecat's,
loguru's, uvicorn's and the rest), requests' CA bundles and .netrc, and their var/ data; and no
aiortc peer reaches a STUN server beyond this machine. And no command writes to var/ when the
var-dir setting names another folder, a child process's included."""

from __future__ import annotations

import argparse
import asyncio
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
from aiortc import RTCConfiguration, RTCPeerConnection
from ole5_voice.evals import run_settings
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.settings.base import PREFIX, setting_name

from tests import isolation

ROOT = Path(__file__).resolve().parents[2]
REPO_VAR = ROOT / "var"
VAR_DIR_VARIABLE = setting_name("storage", "var_dir")
# The Ole5 app's own prefix (the design's 7.3): its env and its access code; and the
# flight-booking agent's (D-101): its access code, its pinned today, its modes.
APP_PREFIX = "OLE5_VOICE_"
APP_PREFIXES = (APP_PREFIX, "FLIGHT_VOICE_")
FOREIGN_PREFIXES = ("GROQ_", "OTEL_", "PHOENIX_")
FOREIGN_NAMES = ("REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE")
# T2's knowledge-base service's general names, which the Ole5 app reads with no prefix.
KB_PREFIXES = ("QDRANT_",)
KB_NAMES = ("EMBEDDING_URL",)
# The variables plan 003's reading of the installed packages found that change what a call's
# packages do whatever the code passes (item 17 of its changes).
CALL_PREFIXES = ("PIPECAT_", "LOGURU_", "WEBSOCKETS_", "UVICORN_", "NUMBA_", "LLVMLITE_", "OPENAI_")
CALL_NAMES = (
    "FORWARDED_ALLOW_IPS",
    "WEB_CONCURRENCY",
    "FASTAPI_OTEL_AUTO_CONFIGURE",
    "FASTAPI_ENV",
    "ORT_LOAD_CONFIG_FROM_MODEL",
)
_HARD_CODED_VAR = re.compile(r"""ROOT\s*/\s*["']var["']""")
FIX = "FIX: make the session fixture in tests/conftest.py isolate it again."


def test_loaded_settings_never_point_at_the_developers_var(
    monkeypatch: pytest.MonkeyPatch, settings: VoiceSettings
) -> None:
    """`from_env` takes the session's scratch var dir, and the `settings` fixture the test's
    own. Settings built in code with no var dir take `var` as their default: a test gives one."""
    monkeypatch.setenv(f"{PREFIX}ENV", "test")
    for var_dir in (VoiceSettings.from_env().storage.var_dir, settings.storage.var_dir):
        assert not var_dir.resolve().is_relative_to(REPO_VAR), (
            f"Tests resolved var_dir to {var_dir}. FIX: build VoiceSettings with a var_dir under "
            "tmp_path (the `settings` fixture), or rely on the scratch var dir that "
            "tests/conftest.py sets for the session."
        )


def test_settings_never_read_a_dotenv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Not `VoiceSettings(...)`, nor `from_env()`, nor the Ole5 app's eval settings (which read
    the working folder's `.env` outside the tests), run from a folder whose .env is invalid."""
    dotenv = f"{PREFIX}LOGGING__LEVEL=NOPE\n{PREFIX}ENV=prod\n{PREFIX}GROQ__API_KEY=made-up\n"
    (tmp_path / ".env").write_text(dotenv, encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    args = argparse.Namespace(
        env_file=None,
        tracing_endpoint=None,
        base_url=None,
        model=None,
        timeout_s=None,
        var_dir=None,
    )
    monkeypatch.setenv(f"{PREFIX}ENV", "test")
    read = (VoiceSettings(env="dev").logging.level, VoiceSettings.from_env().env)
    eval_key = run_settings.load_settings(args).groq.resolved_api_key()
    assert (read, eval_key) == (("INFO", "test"), None), (
        f"A test read the .env in its working folder. {FIX}"
    )
    assert run_settings.DOTENV is None, f"The app's eval settings would read it. {FIX}"


def test_no_setting_comes_from_the_shell() -> None:
    inherited = sorted(n for n in os.environ if n.upper().startswith(PREFIX.upper()))
    assert inherited == [VAR_DIR_VARIABLE], f"Tests inherit {inherited}. {FIX}"


def test_no_app_setting_comes_from_the_shell() -> None:
    """The apps' own settings (an access code, an env, a pinned today) never reach a test."""
    inherited = sorted(n for n in os.environ if n.upper().startswith(APP_PREFIXES))
    assert inherited == [], f"Tests inherit {inherited}. {FIX}"


def test_no_knowledge_base_access_comes_from_the_shell() -> None:
    """The owner's account for T2's knowledge base (its Qdrant's address, email and password)
    never reaches a test."""
    inherited = sorted(
        n for n in os.environ if n.upper().startswith(KB_PREFIXES) or n.upper() in KB_NAMES
    )
    assert inherited == [], f"Tests inherit {inherited}. {FIX}"


def test_no_provider_or_tracing_variable_comes_from_the_shell() -> None:
    """A real Groq key, an exporter's headers or Phoenix's settings never reach a test."""
    inherited = sorted(n for n in os.environ if n.upper().startswith(FOREIGN_PREFIXES))
    assert inherited == [], f"Tests inherit {inherited}. {FIX}"


def test_no_variable_a_calls_packages_read_comes_from_the_shell() -> None:
    """A script run inside every call, every turn's audio written to the working folder, a
    trusted proxy, an exporter added by FastAPI: none reaches a test."""
    inherited = sorted(
        n for n in os.environ if n.upper().startswith(CALL_PREFIXES) or n.upper() in CALL_NAMES
    )
    assert inherited == [], f"Tests inherit {inherited}. {FIX}"


def test_dotenv_loading_is_off_for_the_session() -> None:
    """python-dotenv's `load_dotenv`, which Pipecat's runner calls when imported, loads nothing:
    a guard besides keeping that runner out of the library, whatever the shell said."""
    assert os.environ.get("PYTHON_DOTENV_DISABLED") == "1", FIX


def test_the_shell_is_dropped_before_the_packages_that_read_it_are_imported(
    pytestconfig: pytest.Config,
) -> None:
    """conftest imports nothing of the library at its top, so when `pytest_configure` drops the
    variables, neither the library nor a package that reads one when imported is loaded yet."""
    assert pytestconfig.stash[isolation.IMPORTED_BEFORE_DROP] == [], (
        "These were imported before the shell was dropped. FIX: import them inside the "
        "fixtures of tests/conftest.py, not at its top, and keep tests/isolation.py free of them."
    )


def test_the_isolation_lists_name_the_librarys_variables() -> None:
    """tests/isolation.py imports nothing of the library, so its names are checked here."""
    assert (isolation.PREFIX, isolation.VAR_DIR_VARIABLE) == (PREFIX, VAR_DIR_VARIABLE)
    assert isolation.APP_PREFIX == APP_PREFIX
    assert isolation.APP_PREFIXES == APP_PREFIXES
    names = {"T2V_ENV", "GROQ_LOG", "pipecat_setup_files", "WEB_CONCURRENCY", "LOGURU_LEVEL"}
    names |= {"OLE5_VOICE_ACCESS_CODE", "ole5_voice_env"}
    names |= {"FLIGHT_VOICE_ACCESS_CODE", "FLIGHT_VOICE_TODAY", "flight_voice_booking_mode"}
    names |= {"QDRANT_URL", "qdrant_login_password", "EMBEDDING_URL"}
    assert (isolation.KB_PREFIXES, isolation.KB_NAMES) == (KB_PREFIXES, KB_NAMES)
    assert {n for n in names if isolation.dropped(n)} == names
    assert not isolation.dropped("WEB_CONCURRENCY_X") and not isolation.dropped("PATH")
    assert not isolation.dropped("EMBEDDING_URL_X")


def test_a_child_shell_carries_the_scratch_var_dir_and_no_other_dropped_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A child that loads its settings keeps its runtime files in the session's scratch var
    dir, never the developer's var/; and no other variable the suite drops, the app's access
    code among them, reaches it, nor any other of this project's that a test set (prod, a key),
    so the var dir alone is carried, not its prefix."""
    monkeypatch.setenv(f"{APP_PREFIX}ACCESS_CODE", "made-up-access-code-for-tests")
    monkeypatch.setenv("GROQ_API_KEY", "made-up-key-for-tests")
    monkeypatch.setenv(f"{PREFIX}ENV", "prod")
    monkeypatch.setenv(f"{PREFIX}GROQ__API_KEY", "made-up-key-for-tests")
    shell = isolation.child_shell()
    assert shell["PYTHON_DOTENV_DISABLED"] == "1"
    assert shell[VAR_DIR_VARIABLE] == os.environ[VAR_DIR_VARIABLE]
    assert [n for n in shell if n.upper().startswith(PREFIX)] == [VAR_DIR_VARIABLE]
    unwanted = {"PYTHONPATH", "PYTHONWARNINGS"}
    assert [n for n in shell if isolation.dropped(n) or n in unwanted] == [VAR_DIR_VARIABLE]


def test_a_child_shell_built_before_the_session_set_its_var_dir_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Built at collection (a module's constant), a shell would send its child to the
    developer's var/, with no NETRC of the session's; so it raises, saying where to build it."""
    monkeypatch.delenv(VAR_DIR_VARIABLE)
    with pytest.raises(RuntimeError, match="FIX: call it inside a test or a fixture"):
        isolation.child_shell()


def test_a_peer_with_no_ice_servers_of_its_own_fails_its_test() -> None:
    """aiortc's default list is Google's STUN server; conftest makes it raise, so a peer built
    with no configuration, or with `RTCConfiguration()`, fails at once, and one given its own
    empty list does not. This module imports aiortc at its top, after conftest's
    `pytest_configure` dropped the shell's variables, as every test module is."""

    async def build() -> list[str]:
        outcomes = []
        for configuration, step in (
            (None, "addTransceiver"),
            (RTCConfiguration(), "createDataChannel"),
            (RTCConfiguration(iceServers=[]), "addTransceiver"),
            (RTCConfiguration(iceServers=[]), "createDataChannel"),
        ):
            peer = RTCPeerConnection(configuration)
            try:
                getattr(peer, step)("audio")
                outcomes.append("built")
            except RuntimeError as refused:
                outcomes.append("refused" if "FIX: " in str(refused) else str(refused))
            finally:
                await peer.close()
        return outcomes

    assert asyncio.run(build()) == ["refused", "refused", "built", "built"]


def test_no_ca_bundle_or_netrc_of_the_developers_reaches_requests() -> None:
    """requests would trust another CA bundle on a test's request to 127.0.0.1, and open
    ~/.netrc for its login, whatever the exporter's session then drops."""
    inherited = sorted(n for n in os.environ if n.upper() in FOREIGN_NAMES)
    netrc = Path(os.environ["NETRC"])
    assert (inherited, netrc.read_text(encoding="utf-8")) == ([], ""), f"Tests inherit. {FIX}"


def test_a_shell_that_sets_this_projects_variables_changes_no_test() -> None:
    """The checks above and the import-time one (test_import_isolation.py), in a child run
    whose shell sets a debug level, prod, a bad value, a provider's, an exporter's and Phoenix's
    own variables, two of them read when their package is imported, and those of a call's
    packages, several of them with a value that would fail their package's import."""
    shell = {
        **os.environ,
        f"{PREFIX}ENV": "prod",
        f"{PREFIX}LOGGING__LEVEL": "NOPE",
        f"{PREFIX}LOGGING__FORMAT": "json",
        f"{PREFIX}GROQ__API_KEY": "made-up-key-from-the-shell",
        "GROQ_API_KEY": "made-up-key-from-the-shell",
        "GROQ_LOG": "debug",
        "OTEL_EXPORTER_OTLP_HEADERS": "authorization=made-up",
        "OTEL_PYTHON_CONTEXT": "made_up_context",
        "PHOENIX_WORKING_DIR": "made-up-folder",
        "REQUESTS_CA_BUNDLE": "made-up-ca-bundle.pem",
        "CURL_CA_BUNDLE": "made-up-ca-bundle.pem",
        "NETRC": "made-up-netrc",
        "PIPECAT_SETUP_FILES": "made-up-setup.py",
        "PIPECAT_SMART_TURN_LOG_DATA": "made-up",
        "PIPECAT_SCTP_MAX_CHUNK_SIZE": "not-a-number",
        "LOGURU_LEVEL": "TRACE",
        "LOGURU_DIAGNOSE": "not-a-boolean",
        "WEBSOCKETS_MAX_LINE_LENGTH": "not-a-number",
        "UVICORN_ENV_FILE": ".env",
        "FORWARDED_ALLOW_IPS": "*",
        "WEB_CONCURRENCY": "4",
        "FASTAPI_OTEL_AUTO_CONFIGURE": "true",
        "FASTAPI_ENV": "made-up",
        "ORT_LOAD_CONFIG_FROM_MODEL": "1",
        "NUMBA_DISABLE_JIT": "1",
        "LLVMLITE_ENABLE_IR_LAYER_TYPED_POINTERS": "1",
        "OPENAI_LOG": "debug",
        "PYTHON_DOTENV_DISABLED": "0",
        f"{APP_PREFIX}ENV": "prod",
        f"{APP_PREFIX}ACCESS_CODE": "made-up-access-code-from-the-shell",
        "FLIGHT_VOICE_ACCESS_CODE": "made-up-access-code-from-the-shell",
        "FLIGHT_VOICE_SEARCH_MODE": "fail",
        "QDRANT_URL": "https://made-up.example/qdrant",
        "QDRANT_LOGIN_PASSWORD": "made-up-password-from-the-shell",
        "EMBEDDING_URL": "https://made-up.example/embed",
    }
    here = Path(__file__).relative_to(ROOT).as_posix()
    targets = [
        f"{here}::{test.__name__}"
        for test in (
            test_no_setting_comes_from_the_shell,
            test_no_app_setting_comes_from_the_shell,
            test_no_knowledge_base_access_comes_from_the_shell,
            test_no_provider_or_tracing_variable_comes_from_the_shell,
            test_no_variable_a_calls_packages_read_comes_from_the_shell,
            test_dotenv_loading_is_off_for_the_session,
            test_the_shell_is_dropped_before_the_packages_that_read_it_are_imported,
            test_no_ca_bundle_or_netrc_of_the_developers_reaches_requests,
        )
    ] + [f"{Path(here).parent.as_posix()}/test_import_isolation.py"]
    done = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *targets],
        cwd=ROOT,
        env=shell,
        capture_output=True,
        check=False,
    )
    assert done.returncode == 0, done.stdout.decode("utf-8", errors="replace")


def test_no_script_hard_codes_var() -> None:
    """A command that builds its own path to var/ ignores the setting, and so writes the
    developer's data during a run meant for a scratch folder."""
    offenders = [
        path.relative_to(ROOT).as_posix()
        for path in sorted((ROOT / "scripts").rglob("*.py"))
        if _HARD_CODED_VAR.search(path.read_text(encoding="utf-8"))
    ]
    assert offenders == [], (
        f"{offenders} build a path to var/ from the repository root. FIX: use "
        "the `storage.var_dir` of an injected VoiceSettings instead."
    )

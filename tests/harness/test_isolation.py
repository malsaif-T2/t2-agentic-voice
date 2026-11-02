"""Tests never touch the developer's machine state: their .env, this project's variables in
their shell, a provider's or a tracing tool's variables (GROQ_*, OTEL_*, PHOENIX_*), requests'
CA bundles and .netrc, and their var/ data. And no command writes to var/ when the var-dir
setting names another folder."""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
from ole5_voice.evals import run_settings
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.settings.base import PREFIX, setting_name

ROOT = Path(__file__).resolve().parents[2]
REPO_VAR = ROOT / "var"
VAR_DIR_VARIABLE = setting_name("storage", "var_dir")
FOREIGN_PREFIXES = ("GROQ_", "OTEL_", "PHOENIX_")
FOREIGN_NAMES = ("REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE")
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


def test_no_provider_or_tracing_variable_comes_from_the_shell() -> None:
    """A real Groq key, an exporter's headers or Phoenix's settings never reach a test."""
    inherited = sorted(n for n in os.environ if n.upper().startswith(FOREIGN_PREFIXES))
    assert inherited == [], f"Tests inherit {inherited}. {FIX}"


def test_no_ca_bundle_or_netrc_of_the_developers_reaches_requests() -> None:
    """requests would trust another CA bundle on a test's request to 127.0.0.1, and open
    ~/.netrc for its login, whatever the exporter's session then drops."""
    inherited = sorted(n for n in os.environ if n.upper() in FOREIGN_NAMES)
    netrc = Path(os.environ["NETRC"])
    assert (inherited, netrc.read_text(encoding="utf-8")) == ([], ""), f"Tests inherit. {FIX}"


def test_a_shell_that_sets_this_projects_variables_changes_no_test() -> None:
    """The two checks above and the import-time one (test_import_isolation.py), in a child run
    whose shell sets a debug level, prod, a bad value, and a provider's, an exporter's and
    Phoenix's own variables, two of them read when their package is imported."""
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
    }
    here = Path(__file__).relative_to(ROOT).as_posix()
    targets = [
        f"{here}::{test.__name__}"
        for test in (
            test_no_setting_comes_from_the_shell,
            test_no_provider_or_tracing_variable_comes_from_the_shell,
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

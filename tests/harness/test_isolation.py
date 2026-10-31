"""Tests never touch the developer's machine state: their .env, this project's variables in
their shell, and their var/ data. And no command writes to var/ when the var-dir setting names
another folder."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
from t2_agentic_voice.core.config import Settings, get_settings

ROOT = Path(__file__).resolve().parents[2]
REPO_VAR = ROOT / "var"
PREFIX = Settings.model_config.get("env_prefix", "")
_HARD_CODED_VAR = re.compile(r"""ROOT\s*/\s*["']var["']""")
FIX = "FIX: make the session fixture in tests/conftest.py isolate it again."


def test_default_settings_never_point_at_the_developers_var() -> None:
    var_dir = Settings(_env_file=None).var_dir.resolve()
    assert not var_dir.is_relative_to(REPO_VAR), (
        f"Tests resolved var_dir to {var_dir}. FIX: build Settings with var_dir=tmp_path, or "
        "rely on the scratch var dir that tests/conftest.py sets for the session."
    )


def test_settings_never_read_a_dotenv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Not even `Settings()` or `get_settings()`, run from a folder whose .env is invalid."""
    dotenv = f"{PREFIX}LOG_LEVEL=NOPE\n{PREFIX}ENV=prod\n"
    (tmp_path / ".env").write_text(dotenv, encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    get_settings.cache_clear()
    try:
        read = (Settings().log_level, get_settings().env)
    finally:
        get_settings.cache_clear()
    assert read == ("INFO", "dev"), f"A test read the .env in its working folder. {FIX}"


def test_no_setting_comes_from_the_shell() -> None:
    inherited = sorted(n for n in os.environ if n.upper().startswith(PREFIX.upper()))
    assert inherited == [f"{PREFIX}VAR_DIR"], f"Tests inherit {inherited}. {FIX}"


def test_a_shell_that_sets_this_projects_variables_changes_no_test() -> None:
    """The check above, in a child run whose shell sets a debug level, prod, and a bad value."""
    shell = {
        **os.environ,
        f"{PREFIX}ENV": "prod",
        f"{PREFIX}LOG_LEVEL": "NOPE",
        f"{PREFIX}LOG_FORMAT": "json",
    }
    here = Path(__file__).relative_to(ROOT).as_posix()
    target = f"{here}::{test_no_setting_comes_from_the_shell.__name__}"
    done = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", target],
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
        "`get_settings().var_dir`, or an injected Settings, instead."
    )

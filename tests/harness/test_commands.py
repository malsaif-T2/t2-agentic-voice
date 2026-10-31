"""The commands (`uv run poe <task>`, scripts/), as a caller meets them:
- every task writes UTF-8 (`[tool.poe.env]` in pyproject.toml), so non-ASCII text reads the
  same in a console, a pipe, or a file. Piped, Python otherwise writes in the machine's legacy
  code page on Windows, or fails on a character it cannot encode;
- every command parses its arguments, so `--help` only prints help. One that ignores them runs
  instead, and some write files or start servers."""

from __future__ import annotations

import ast
import os
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SAMPLE = "東京, Grüße, café"


def _poe_env() -> dict[str, str]:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    env: dict[str, str] = pyproject["tool"]["poe"].get("env", {})
    return env


def test_every_command_writes_utf8_even_when_piped() -> None:
    inherited = {k: v for k, v in os.environ.items() if k not in ("PYTHONIOENCODING", "PYTHONUTF8")}
    printed = subprocess.run(
        [sys.executable, "-X", "utf8=0", "-c", f"print({SAMPLE!r})"],
        env={**inherited, **_poe_env()},
        capture_output=True,
        check=True,
    )
    assert printed.stdout.decode("utf-8").strip() == SAMPLE


def test_every_command_parses_its_arguments() -> None:
    ignoring = []
    for path in sorted((ROOT / "scripts").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for main in (n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "main"):
            parses = any(
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "parse_args"
                and node.args
                for node in ast.walk(main)
            )
            if not parses:
                ignoring.append(path.relative_to(ROOT).as_posix())
    assert ignoring == [], (
        f"{ignoring}: `--help` would run these. FIX: give `main` an `argv` parameter and parse "
        "it with argparse (`ArgumentParser(description=...).parse_args(argv)`)."
    )


def test_each_check_runs_as_a_command_and_says_how_it_went() -> None:
    """The gate's own checks, as `poe arch` and `poe docs` run them: an exit code and a last
    line that either says OK or asks for every item to be fixed."""
    for module in ("scripts.check_architecture", "scripts.check_docs"):
        done = subprocess.run(
            [sys.executable, "-m", module],
            cwd=ROOT,
            env={**os.environ, **_poe_env()},
            capture_output=True,
            check=False,
        )
        last = done.stdout.decode("utf-8").strip().splitlines()[-1]
        assert (": OK (" in last) == (done.returncode == 0), last
        assert done.returncode == 0 or last.endswith("Fix every item above, then re-run.")

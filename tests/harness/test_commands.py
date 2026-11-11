"""The commands (`uv run poe <task>`, scripts/), as a caller meets them:
- every task writes UTF-8 (`[tool.poe.env]` in pyproject.toml), so non-ASCII text reads the
  same in a console, a pipe, or a file. Piped, Python otherwise writes in the machine's legacy
  code page on Windows, or fails on a character it cannot encode;
- every command parses its arguments, so `--help` only prints help. One that ignores them runs
  instead, and some write files or start servers. "Every command" is each script under
  scripts/ and each module a poe task runs with `python -m`, the apps' included."""

from __future__ import annotations

import ast
import importlib.util
import os
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

from tests.harness.support import ARCHITECTURE, SYNTHETIC, write

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


def _task_modules() -> dict[str, Path]:
    """Every module a poe task runs with `python -m`, and its file."""
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    commands = []
    for task in pyproject["tool"]["poe"]["tasks"].values():
        steps = task.get("sequence", [task])
        commands += [step["cmd"] for step in steps if isinstance(step, dict) and "cmd" in step]
    modules = {c.split()[2] for c in commands if c.startswith("python -m ")}
    found = {}
    for module in sorted(modules):
        spec = importlib.util.find_spec(module)
        assert spec is not None and spec.origin, f"poe runs `python -m {module}`, not a module"
        found[module] = Path(spec.origin)
    return found


def test_every_command_parses_its_arguments() -> None:
    """The scripts, and every module a poe task runs with `python -m` (the apps' too)."""
    tasks = _task_modules()
    assert {"scripts.check_docs", "ole5_voice.evals.run"} <= tasks.keys()
    ignoring = []
    paths = sorted({*(ROOT / "scripts").rglob("*.py"), *tasks.values()})
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        mains = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "main"]
        if path in tasks.values() and not mains:
            ignoring.append(path.as_posix())  # a poe task's module runs its `main`
        for main in mains:
            parses = any(
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "parse_args"
                and node.args
                for node in ast.walk(main)
            )
            if not parses:
                ignoring.append(path.as_posix())
    assert ignoring == [], (
        f"{ignoring}: `--help` would run these. FIX: give `main` an `argv` parameter and parse "
        "it with argparse (`ArgumentParser(description=...).parse_args(argv)`)."
    )


CHECKS = ("scripts.check_architecture", "scripts.check_docs")
# The synthetic project of support.py, with this repository's scripts/ copied in to run it: the
# copy is read by neither check (its own rules are the gate's `arch` and `docs` steps').
_PROJECT = SYNTHETIC.replace('support_dirs = ["scripts", "tests"]', 'support_dirs = ["tests"]')
_PROJECT = _PROJECT.replace('code_dirs = ["src", "scripts", "tests"]', 'code_dirs = ["src"]')
# The projects' files beside the copy: none more, and a violation of each check, an upward
# import (ARCH-LAYER) and a broken link (DOC-LINK).
_BROKEN = {"src/app/core/x.py": "from app.api import routes\n", "CLAUDE.md": "[a](docs/no.md)\n"}
_FILES: dict[str, dict[str, str]] = {"clean": {}, "broken": _BROKEN}


def _project(root: Path, files: dict[str, str]) -> Path:
    """A small project at `root` that the checks pass, with `files` added: this repository's
    scripts/, found by `python -m` from the project's root as poe finds them from this one."""
    skipped = shutil.ignore_patterns("__pycache__")
    shutil.copytree(ROOT / "scripts", root / "scripts", ignore=skipped)
    base = {"harness.toml": _PROJECT, "ARCHITECTURE.md": ARCHITECTURE, "CLAUDE.md": "A map.\n"}
    return write(root, base | {"src/app/__init__.py": ""} | files)


def test_each_check_runs_as_a_command_and_says_how_it_went(tmp_path: Path) -> None:
    """The gate's own checks, as `poe arch` and `poe docs` run them from a project's root: an
    exit code and a last line that either says OK or asks for every item to be fixed. On a
    small project, clean and then with a violation of each, the four runs side by side; the
    gate's own `arch` and `docs` steps run them on this repository."""
    assert "scripts" not in _PROJECT  # the copy sits in no folder the checks read
    roots = {kind: _project(tmp_path / kind, files) for kind, files in _FILES.items()}
    children = {
        (kind, module): subprocess.Popen(
            [sys.executable, "-m", module],
            cwd=root,
            env={**os.environ, **_poe_env()},
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        for kind, root in roots.items()
        for module in CHECKS
    }
    done = {}
    try:
        for key, child in children.items():
            out, _ = child.communicate(timeout=300)
            done[key] = (child.returncode, out.decode("utf-8").strip().splitlines()[-1])
    finally:
        for child in children.values():
            child.kill()
            child.wait()
    fix = "violation(s). Fix every item above, then re-run."
    assert done == {
        ("clean", "scripts.check_architecture"): (0, "check_architecture: OK (1 files checked)"),
        ("clean", "scripts.check_docs"): (0, "check_docs: OK (2 files checked)"),
        ("broken", "scripts.check_architecture"): (1, f"check_architecture: 1 {fix}"),
        ("broken", "scripts.check_docs"): (1, f"check_docs: 1 {fix}"),
    }

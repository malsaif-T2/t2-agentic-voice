"""What CI would check of the library's install, run inside `poe check` while CI waits for a
remote (TD-001): the torch check, that the resolved install holds no torch (the design's 9.8 and
12.4), and an import of every public module, each alone in a new process (the design's 5.3), the
workspace's environment standing in for an install of the base package."""

from __future__ import annotations

import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

from scripts.harness_config import load_config
from tests.isolation import child_shell

ROOT = Path(__file__).resolve().parents[2]
PUBLIC = sorted(load_config(ROOT).arch.public)
# The child: import the one module named on its command line, and nothing else.
_IMPORT = "import importlib, sys; importlib.import_module(sys.argv[1])"


def locked(text: str) -> list[str]:
    """The name of every package a uv.lock's text resolves."""
    return [package["name"] for package in tomllib.loads(text).get("package", [])]


def torch(names: list[str]) -> list[str]:
    """The names that are torch or one of its own packages (`torchaudio`, `torchvision`)."""
    return sorted(name for name in names if name.startswith("torch"))


def test_the_lock_holds_no_torch() -> None:
    """Smart Turn v3 and Silero run on onnxruntime, so nothing the library installs needs torch:
    a package that brings it would add gigabytes to every team's install."""
    names = locked((ROOT / "uv.lock").read_text(encoding="utf-8"))
    assert len(names) > 50  # the lock was read: the library, its apps and their packages
    assert torch(names) == [], (
        f"uv.lock resolves {torch(names)}. FIX: find the package that brought it "
        "(`uv tree --invert --package torch`) and remove it, or use one of its parts that needs "
        "no torch; ARCH-BAN lists the Pipecat modules that do."
    )


def test_the_torch_check_finds_torch_in_a_lock() -> None:
    lock = (
        'version = 1\n\n[[package]]\nname = "numpy"\nversion = "2.5.4"\n\n'
        '[[package]]\nname = "torch"\nversion = "2.9.0"\n\n'
        '[[package]]\nname = "torchaudio"\nversion = "2.9.0"\n'
    )
    assert torch(locked(lock)) == ["torch", "torchaudio"]
    assert locked("version = 1\n") == []


@pytest.fixture(scope="module")
def imports() -> dict[str, tuple[int | None, bytes, bytes]]:
    """Each public module's import, each in a new process of its own with the suite's clean
    shell, side by side: (its exit code, its standard output, its standard error)."""
    children = {
        module: subprocess.Popen(
            [sys.executable, "-I", "-X", "utf8", "-c", _IMPORT, module],
            cwd=ROOT,
            env=child_shell(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        for module in PUBLIC
    }
    done: dict[str, tuple[int | None, bytes, bytes]] = {}
    try:
        for module, child in children.items():
            out, err = child.communicate(timeout=300)
            done[module] = (child.returncode, out, err)
    finally:
        for child in children.values():
            child.kill()
            child.wait()
    return done


def test_every_public_module_is_imported_here() -> None:
    assert "t2_agentic_voice" in PUBLIC and len(PUBLIC) > 1


@pytest.mark.parametrize("module", PUBLIC)
def test_a_public_module_imports_alone_and_prints_nothing(
    module: str, imports: dict[str, tuple[int | None, bytes, bytes]]
) -> None:
    """Alone, so a module that works only after another was imported shows; with nothing on
    either output, so an import neither warns nor logs (invariant 8)."""
    code, out, err = imports[module]
    assert (code, out, err) == (0, b"", b""), err.decode("utf-8", errors="replace")

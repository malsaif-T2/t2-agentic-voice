"""What CI would check of the library's install, run inside `poe check` while CI waits for a
remote (TD-001): the torch check (the design's 9.8 and 12.4, amended by plan 007's Q15), and an
import of every public module, each alone in a new process (the design's 5.3), the workspace's
environment standing in for an install of the base package.

The torch check walks `uv.lock`, so it gives one answer whether or not the `language-id` group is
installed: from each workspace member's base dependencies (no extra, no group), no package is
torch or one of its own (`torchaudio`, `torchvision`), a CUDA package (`nvidia-*`, `cuda-*`) or
`triton`, so no team's install of the library or of an app gains gigabytes; torch is reached
only through the library's `ecapa` extra (`t2-agentic-voice[ecapa]`, which the root's
`language-id` group installs here and no app asks for); and the lock holds no CUDA package nor
`triton` at all, since on Linux torch comes from PyTorch's CPU index (the root's
`[tool.uv.sources]`)."""

from __future__ import annotations

import subprocess
import sys
import tomllib
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

import pytest

from scripts.harness_config import load_config
from tests.isolation import child_shell

ROOT = Path(__file__).resolve().parents[2]
PUBLIC = sorted(load_config(ROOT).arch.public)
# The child: import the one module named on its command line, and nothing else; a test's
# stand-in module is found in the folders named after it.
_IMPORT = "import importlib, sys; sys.path[:0] = sys.argv[2:]; importlib.import_module(sys.argv[1])"
# The one way torch may come: the library's extra.
EXTRA = ("t2-agentic-voice", "ecapa")
# A dependency in the lock: a package's name, and the extras asked of it.
Need = tuple[str, tuple[str, ...]]


def importing(module: str, *path: str) -> list[str]:
    """The command that imports `module` alone in a new process: isolated from the shell's
    Python settings, and showing every warning, which Python's default filters hide outside
    `__main__` (a DeprecationWarning, an ImportWarning, a ResourceWarning)."""
    return [sys.executable, "-I", "-X", "utf8", "-W", "default", "-c", _IMPORT, module, *path]


def locked(text: str) -> list[str]:
    """The name of every package a uv.lock's text resolves."""
    return [package["name"] for package in tomllib.loads(text).get("package", [])]


def heavy(names: Iterable[str]) -> list[str]:
    """The names that are torch or one of its own packages, a CUDA package or triton."""
    return sorted({n for n in names if n.startswith("torch")} | set(cuda(names)))


def cuda(names: Iterable[str]) -> list[str]:
    """The names that are a CUDA package or triton."""
    return sorted({n for n in names if n.startswith(("nvidia-", "cuda-")) or n == "triton"})


class Lock:
    """A uv.lock read as a graph: each package's base dependencies, its extras' and its groups'
    (a name the lock holds twice, one version for some platforms, is one node)."""

    def __init__(self, text: str) -> None:
        self.packages: dict[str, list[dict[str, Any]]] = {}
        for package in tomllib.loads(text).get("package", []):
            self.packages.setdefault(package["name"], []).append(package)

    @property
    def members(self) -> list[str]:
        """The workspace's own packages: each member, and the root."""
        own = ("editable", "virtual")
        found = self.packages.items()
        return sorted(name for name, ps in found if any(k in ps[0]["source"] for k in own))

    def _tables(self, name: str, key: str) -> dict[str, list[Need]]:
        found: dict[str, list[Need]] = {}
        for package in self.packages.get(name, []):
            for part, entries in package.get(key, {}).items():
                found.setdefault(part, []).extend(_needs(entries))
        return found

    def base(self, name: str) -> list[Need]:
        return [n for p in self.packages.get(name, []) for n in _needs(p.get("dependencies", []))]

    def extras(self, name: str) -> dict[str, list[Need]]:
        return self._tables(name, "optional-dependencies")

    def groups(self, name: str) -> dict[str, list[Need]]:
        return self._tables(name, "dev-dependencies")

    def reached(self, needs: Iterable[Need], *, skip: tuple[str, str] | None = None) -> set[str]:
        """Every package `needs` install, each extra asked followed but `skip`."""
        seen: set[str] = set()
        waiting = list(needs)
        while waiting:
            name, asked = waiting.pop()
            extras = self.extras(name)
            waiting += [
                n for extra in asked if (name, extra) != skip for n in extras.get(extra, [])
            ]
            if name not in seen:
                seen.add(name)
                waiting += self.base(name)
        return seen

    def everything_but(self, skip: tuple[str, str]) -> set[str]:
        """What every member's base, every extra and every group installs, `skip` left out."""
        needs: list[Need] = []
        for member in self.members:
            needs.append((member, tuple(e for e in self.extras(member) if (member, e) != skip)))
            for entries in self.groups(member).values():
                needs += entries
        return self.reached(needs, skip=skip)


def _needs(entries: Iterable[Mapping[str, Any]]) -> list[Need]:
    return [(entry["name"], tuple(entry.get("extra", ()))) for entry in entries]


LOCK = (ROOT / "uv.lock").read_text(encoding="utf-8")


def test_no_members_base_install_holds_torch_a_cuda_package_or_triton() -> None:
    """Smart Turn v3 and Silero run on onnxruntime: no team's install of the library or of an
    app needs torch, which would add gigabytes to it."""
    lock = Lock(LOCK)
    assert len(lock.packages) > 50  # the lock was read: the library, its apps and their packages
    own = {"t2-agentic-voice", "ole5-voice-agent", "t2-agentic-voice-workspace"}
    assert own <= set(lock.members)
    for member in lock.members:
        found = heavy(lock.reached([(member, ())]))
        assert found == [], (
            f"{member}'s base install resolves {found}. FIX: find the package that brought it "
            "(`uv tree --invert --package <name>`) and remove it, or use one of its parts that "
            "needs no torch; ARCH-BAN lists the Pipecat modules that do. torch may come only "
            "through the library's `ecapa` extra."
        )


def test_torch_comes_only_through_the_librarys_ecapa_extra() -> None:
    lock = Lock(LOCK)
    other = heavy(lock.everything_but(EXTRA))
    assert other == [], f"{other} come through more than t2-agentic-voice[ecapa]"
    assert cuda(lock.packages) == [], (
        f"uv.lock resolves {cuda(lock.packages)}. FIX: take torch and torchaudio from PyTorch's "
        "CPU index on Linux (the root's [tool.uv.sources]), never from PyPI's CUDA wheels."
    )
    if "torch" in lock.packages:  # once the extra is locked
        through = lock.reached([(EXTRA[0], (EXTRA[1],))])
        assert {"torch", "torchaudio", "speechbrain"} <= through
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert pyproject["dependency-groups"]["language-id"] == ["t2-agentic-voice[ecapa]"]


# A made-up lock: a library whose `heavy` extra brings torch and a CUDA package, an app on it,
# and a root whose group asks for the extra.
MADE_UP = """
version = 1

[[package]]
name = "lib"
version = "1.0"
source = { editable = "lib" }
dependencies = [{ name = "numpy" }]

[package.optional-dependencies]
heavy = [{ name = "torch" }]

[[package]]
name = "app"
version = "1.0"
source = { editable = "app" }
dependencies = [{ name = "lib" }]

[[package]]
name = "root"
version = "1.0"
source = { virtual = "." }
dependencies = [{ name = "app" }]

[package.dev-dependencies]
models = [{ name = "lib", extra = ["heavy"] }]

[[package]]
name = "numpy"
version = "2.5.4"
source = { registry = "https://pypi.org/simple" }

[[package]]
name = "torch"
version = "2.15.0"
source = { registry = "https://pypi.org/simple" }
dependencies = [{ name = "nvidia-cudnn-cu13", marker = "sys_platform == 'linux'" }]

[[package]]
name = "nvidia-cudnn-cu13"
version = "9.26.0.51"
source = { registry = "https://pypi.org/simple" }
"""


def test_the_torch_check_reads_a_made_up_lock() -> None:
    lock = Lock(MADE_UP)
    assert lock.members == ["app", "lib", "root"]
    assert all(heavy(lock.reached([(member, ())])) == [] for member in lock.members)
    assert heavy(lock.everything_but(("lib", "heavy"))) == []
    assert heavy(lock.reached([("lib", ("heavy",))])) == ["nvidia-cudnn-cu13", "torch"]
    assert cuda(lock.packages) == ["nvidia-cudnn-cu13"]
    app = 'dependencies = [{ name = "lib" }]'
    leaky = Lock(MADE_UP.replace(app, 'dependencies = [{ name = "lib", extra = ["heavy"] }]'))
    assert heavy(leaky.reached([("app", ())])) == ["nvidia-cudnn-cu13", "torch"]
    assert heavy(leaky.everything_but(("lib", "heavy"))) == []  # the extra, asked by its name
    grouped = Lock(
        MADE_UP.replace(
            'models = [{ name = "lib", extra = ["heavy"] }]', 'models = [{ name = "torch" }]'
        )
    )
    assert heavy(grouped.everything_but(("lib", "heavy"))) == ["nvidia-cudnn-cu13", "torch"]
    assert heavy(["torchvision", "triton", "cuda-toolkit", "numpy"]) == [
        "cuda-toolkit",
        "torchvision",
        "triton",
    ]
    assert locked("version = 1\n") == []


@pytest.fixture(scope="module")
def imports() -> dict[str, tuple[int | None, bytes, bytes]]:
    """Each public module's import, each in a new process of its own with the suite's clean
    shell, side by side: (its exit code, its standard output, its standard error)."""
    children = {
        module: subprocess.Popen(
            importing(module),
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


def test_a_warning_on_import_shows_in_the_child(tmp_path: Path) -> None:
    """A module's DeprecationWarning at import, which Python's default filters would hide."""
    (tmp_path / "stand_in_old.py").write_text(
        "import warnings\nwarnings.warn('stand_in_old is old', DeprecationWarning)\n",
        encoding="utf-8",
    )
    (tmp_path / "stand_in_quiet.py").write_text("QUIET = True\n", encoding="utf-8")
    done = {
        name: subprocess.run(
            importing(name, str(tmp_path)),
            cwd=tmp_path,
            env=child_shell(),
            capture_output=True,
            timeout=60,
            check=False,
        )
        for name in ("stand_in_old", "stand_in_quiet")
    }
    assert b"DeprecationWarning: stand_in_old is old" in done["stand_in_old"].stderr
    assert (done["stand_in_quiet"].returncode, done["stand_in_quiet"].stderr) == (0, b"")

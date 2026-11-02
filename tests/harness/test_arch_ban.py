"""ARCH-BAN (scripts/arch_ban.py): the code a [[bans]] table covers never imports a module it
bans, in any form, its allowed modules aside. The rule's tests run on the synthetic project of
support.py; then this repository's bans are checked against what plan 003 asks and against the
installed Pipecat, and importing `voice` is shown to leave Pipecat's runner out."""

from __future__ import annotations

import ast
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.arch_ban import imported
from scripts.check_architecture import check_repo
from scripts.harness_arch import ArchConfig
from scripts.harness_config import load_config
from tests.harness.support import ARCHITECTURE, SYNTHETIC, config, write
from tests.isolation import child_shell

ROOT = Path(__file__).resolve().parents[2]
# Three bans on the synthetic library `app` and two apps: a vendor's services in the whole
# library but its base ones; all of the vendor in one subpackage; the vendor and an RTC stack in
# the apps.
BANS = """
[[bans]]
modules = ["vendor.services"]
allowed = ["vendor.services.base", "vendor.services.settings"]
within = ["app"]
fix = "Subclass the vendor's base service only."

[[bans]]
modules = ["vendor"]
allowed = []
within = ["app.services.reports"]
fix = "Reports never touch the vendor."

[[bans]]
modules = ["vendor", "rtc"]
allowed = []
within = ["shop", "demo"]
fix = "An app uses only the library."

[[apps]]
name = "shop"
root = "apps/shop/src"

[[apps]]
name = "demo"
root = "examples/demo/src"
"""
PACKAGES = {
    "ARCHITECTURE.md": ARCHITECTURE,
    "src/app/__init__.py": "",
    "apps/shop/src/shop/__init__.py": "",
    "examples/demo/src/demo/__init__.py": "",
}


def _bans(tmp_path: Path, files: dict[str, str]) -> list[tuple[str, int, str]]:
    """(path, line, the banned module's prefix) of each ARCH-BAN violation in the project."""
    loaded = config(tmp_path, SYNTHETIC + BANS)
    violations, _ = check_repo(write(tmp_path, PACKAGES | files), loaded)
    found = [v for v in violations if v.rule == "ARCH-BAN"]
    return sorted((v.path, v.line, v.problem.rsplit("'", 2)[1]) for v in found)


def test_a_banned_module_is_refused_in_every_form_of_import(tmp_path: Path) -> None:
    files = {
        "src/app/__init__.py": "from vendor.services.acme import Speech\n",
        "src/app/services/a.py": (
            "import vendor.services.acme.tts\nfrom vendor.services import acme, base\n"
            "from vendor import services\nfrom vendor.services import *\n"
        ),
        "src/app/core/b.py": (
            "import importlib as il\nil.import_module('vendor.services.acme')\n"
            "__import__('vendor.services')\n"
            "from importlib import import_module as load\nload('vendor.services.x.y')\n"
        ),
    }
    services = "vendor.services"
    assert _bans(tmp_path, files) == [
        ("src/app/__init__.py", 1, services),
        ("src/app/core/b.py", 2, services),
        ("src/app/core/b.py", 3, services),
        ("src/app/core/b.py", 5, services),
        ("src/app/services/a.py", 1, services),
        ("src/app/services/a.py", 2, services),
        ("src/app/services/a.py", 3, services),
        ("src/app/services/a.py", 4, services),
    ]


def test_allowed_modules_and_other_imports_pass(tmp_path: Path) -> None:
    files = {
        "src/app/services/ok.py": (
            "from vendor.services.base import Base\nfrom vendor.services import base, settings\n"
            "import vendor.services.base.sub\nimport vendor.servicesx\nimport vendor.pipeline\n"
            "from . import ok\nfrom ..core import x\nimport importlib\n"
            "importlib.import_module(name)\nimportlib.import_module('.acme', 'vendor.services')\n"
            "other.import_module('vendor.services.acme')\n__import__('')\n"
        ),
        "src/app/adapters/rtc_user.py": "import rtc\n",  # the apps' ban does not cover the library
    }
    assert _bans(tmp_path, files) == []


def test_a_ban_on_a_part_of_the_library_covers_only_that_part(tmp_path: Path) -> None:
    """The subpackage's ban also refuses a module the library-wide ban allows."""
    files = {
        "src/app/services/reports/__init__.py": "import vendor\n",
        "src/app/services/reports/pdf.py": "from vendor.services.base import Base\n",
        "src/app/services/report.py": "import vendor.pipeline\n",
    }
    assert _bans(tmp_path, files) == [
        ("src/app/services/reports/__init__.py", 1, "vendor"),
        ("src/app/services/reports/pdf.py", 1, "vendor"),
    ]


def test_apps_and_examples_are_covered_by_their_ban(tmp_path: Path) -> None:
    files = {
        "apps/shop/src/shop/call.py": "import rtc.peer\nfrom app import Settings\n",
        "examples/demo/src/demo/main.py": "from vendor import pipeline\n",
    }
    assert _bans(tmp_path, files) == [
        ("apps/shop/src/shop/call.py", 1, "rtc"),
        ("examples/demo/src/demo/main.py", 1, "vendor"),
    ]


def test_each_violation_names_the_ban_and_prints_its_fix(tmp_path: Path) -> None:
    loaded = config(tmp_path, SYNTHETIC + BANS)
    files = PACKAGES | {"src/app/services/reports/x.py": "from vendor.services import acme\n"}
    violations = [v for v in check_repo(write(tmp_path, files), loaded)[0] if v.rule == "ARCH-BAN"]
    assert [str(v) for v in violations] == [
        "src/app/services/reports/x.py:1: [ARCH-BAN] 'vendor.services.acme' is banned in 'app' "
        "([[bans]]: 'vendor.services')\n    FIX: Subclass the vendor's base service only.",
        "src/app/services/reports/x.py:1: [ARCH-BAN] 'vendor.services.acme' is banned in "
        "'app.services.reports' ([[bans]]: 'vendor')\n    FIX: Reports never touch the vendor.",
    ]


def test_a_module_that_does_not_parse_is_left_to_arch_parse(tmp_path: Path) -> None:
    loaded = config(tmp_path, SYNTHETIC + BANS)
    files = PACKAGES | {"src/app/core/broken.py": "import vendor.services.acme\ndef (:\n"}
    violations, _ = check_repo(write(tmp_path, files), loaded)
    assert [v.rule for v in violations] == ["ARCH-PARSE"]


# ------------------------------------------------------------------ this repository's bans


def _banned(arch: ArchConfig, importer: str, name: str) -> bool:
    """Whether a ban covering the module `importer` refuses its import of `name`."""
    return any(b.scope(importer) and b.banned(name) for b in arch.bans)


def test_this_repositorys_bans_say_what_plan_003_asks() -> None:
    """Step 6 and item 18 of the changes its reading of the installed packages made."""
    arch = load_config(ROOT).arch
    voice = "t2_agentic_voice.voice.pipeline"
    for name in (
        "pipecat.services.groq.stt",
        "pipecat.services.openai",
        "pipecat.services.llm_service",
        "pipecat.adapters.services.open_ai_adapter",
        "pipecat.processors.aggregators.llm_context",
        "pipecat.processors.aggregators.llm_response_universal",
        "pipecat.runner.run",
        "pipecat.cli",
        "pipecat.evals",
        "pipecat.bus.serializers.json",
        "pipecat.audio.turn.smart_turn.local_smart_turn_v2",
        "pipecat.audio.resamplers.resampy_resampler",
        "pipecat.processors.logger",
        "pipecat.observers.loggers.debug_log_observer",
        "pipecat.processors.aggregators.dtmf_aggregator",
    ):
        assert _banned(arch, voice, name), name
        assert _banned(arch, "t2_agentic_voice", name), name  # the package root too
    for name in (
        "pipecat.services.stt_service",
        "pipecat.services.tts_service",
        "pipecat.services.ai_service",
        "pipecat.services.settings",
        "pipecat.audio.turn.smart_turn.local_smart_turn_v3",
        "pipecat.audio.vad.silero",
        "pipecat.transports.smallwebrtc.connection",
        "pipecat.pipeline.worker",
    ):
        assert not _banned(arch, voice, name), name
    assert _banned(arch, "t2_agentic_voice.voice.session.io", "pipecat.frames.frames")
    assert _banned(arch, "t2_agentic_voice.voice.session", "pipecat.services.stt_service")
    for app in arch.apps:
        for name in ("pipecat.pipeline.worker", "aiortc", "aiortc.rtcpeerconnection"):
            assert _banned(arch, f"{app.name}.server", name), (app.name, name)


def _source(module: str) -> Path:
    """The installed file or folder of a dotted module name, found without importing it."""
    top, *parts = module.split(".")
    spec = importlib.util.find_spec(top)
    assert spec is not None and spec.submodule_search_locations, top
    path = Path(next(iter(spec.submodule_search_locations)), *parts)
    return path if path.is_dir() else path.with_suffix(".py")


def test_every_module_a_ban_names_is_in_the_installed_package() -> None:
    """A module renamed or moved by a new version would leave its ban guarding nothing."""
    names = {n for ban in load_config(ROOT).arch.bans for n in (*ban.modules, *ban.allowed)}
    assert [n for n in sorted(names) if not _source(n).exists()] == []


def test_the_allowed_services_are_what_the_speech_bases_import() -> None:
    """The services ban allows the base classes voice's bridges subclass and every module of
    `pipecat.services` they import, read from the installed source, and nothing else."""
    (ban,) = [b for b in load_config(ROOT).arch.bans if "pipecat.services" in b.modules]
    needed: set[str] = set()
    todo = ["pipecat.services.stt_service", "pipecat.services.tts_service"]
    while todo:
        module = todo.pop()
        needed.add(module)
        tree = ast.parse(_source(module).read_text(encoding="utf-8"))
        for name, _ in imported(tree):
            found = ".".join(name.split(".")[:3])
            if name.startswith("pipecat.services.") and found not in needed:
                todo.append(found)
    assert set(ban.allowed) == needed
    assert "pipecat.services.ai_service" in needed


# The child: import `voice` and every module under it, then report which of Pipecat's runner's
# modules are loaded. It writes its report to the file it is given.
_CHILD = """
import importlib, json, pkgutil, sys

import t2_agentic_voice.voice as voice

for found in pkgutil.walk_packages(voice.__path__, "t2_agentic_voice.voice."):
    importlib.import_module(found.name)
loaded = sorted(n for n in sys.modules if n.startswith("pipecat.runner.run"))
with open(sys.argv[1], "w", encoding="utf-8") as out:
    json.dump(loaded, out)
"""


def test_importing_voice_leaves_pipecats_runner_out(tmp_path: Path) -> None:
    """`pipecat.runner.run` loads a `.env` with override when it is imported (plan 003's reading
    of step 4); ARCH-BAN keeps it out of the library's own imports, and this, in a new process,
    out of everything `voice` imports."""
    report = tmp_path / "report.json"
    done = subprocess.run(
        [sys.executable, "-I", "-X", "utf8", "-c", _CHILD, str(report)],
        cwd=ROOT,
        env=child_shell(),
        capture_output=True,
        timeout=300,
        check=False,
    )
    assert done.returncode == 0, done.stderr.decode("utf-8", errors="replace")
    assert json.loads(report.read_text(encoding="utf-8")) == []


@pytest.mark.parametrize(
    ("source", "found"),
    [
        ("from a.b import c as d, e\n", ["a.b.c", "a.b.e"]),
        ("import a.b as c, d\n", ["a.b", "d"]),
        ("from . import a\nfrom .b import c\n", []),
        ("import importlib\nimportlib.import_module(f'{x}')\n", ["importlib"]),
    ],
)
def test_imports_are_read_as_modules(source: str, found: list[str]) -> None:
    assert [name for name, _ in imported(ast.parse(source))] == found

"""ARCH-BAN (scripts/arch_ban.py): the code a [[bans]] table covers never imports a module it
bans, in any form, wherever the import sits, nor reaches one through its own package's other
modules, its allowed modules aside. The rule's tests run on the synthetic project of support.py;
then this repository's bans are checked against what plan 003 asks (and, in
test_installed_pipecat.py, against the installed Pipecat), and importing `voice` is shown to
leave Pipecat's runner out."""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from scripts._common import Violation
from scripts.arch_ban import imported
from scripts.check_architecture import check_repo
from scripts.harness_arch import ArchConfig, missing_scopes
from scripts.harness_config import load_config
from scripts.harness_toml import Lines
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
    "src/app/services/reports/__init__.py": "",
    "apps/shop/src/shop/__init__.py": "",
    "examples/demo/src/demo/__init__.py": "",
}


def _violations(tmp_path: Path, files: dict[str, str]) -> list[Violation]:
    """The ARCH-BAN violations in the project holding `files`, under the bans above."""
    write(tmp_path, PACKAGES | files)
    violations, _ = check_repo(tmp_path, config(tmp_path, SYNTHETIC + BANS))
    return [v for v in violations if v.rule == "ARCH-BAN"]


def _bans(tmp_path: Path, files: dict[str, str]) -> list[tuple[str, int, str]]:
    """(path, line, the banned module's prefix) of each ARCH-BAN violation in the project."""
    found = _violations(tmp_path, files)
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
            "il.import_module('.acme', 'vendor.services')\n"
            "il.import_module(name='vendor.services.acme')\n"
            "il.__import__('vendor.services.acme')\n"
            "from importlib import __import__ as imp\nimp('vendor.services.acme', None, None, ())\n"
            "il.import_module(package='vendor.x', name='..services.acme')\n"
        ),
    }
    services = "vendor.services"
    assert _bans(tmp_path, files) == [
        ("src/app/__init__.py", 1, services),
        *[("src/app/core/b.py", line, services) for line in (2, 3, 5, 6, 7, 8, 10, 11)],
        *[("src/app/services/a.py", line, services) for line in (1, 2, 3, 4)],
    ]


def test_an_import_counts_wherever_it_sits(tmp_path: Path) -> None:
    """In a function, under `if TYPE_CHECKING:`, in a `try` and in a class body."""
    files = {
        "src/app/core/c.py": (
            "from typing import TYPE_CHECKING\n"
            "if TYPE_CHECKING:\n    from vendor.services.acme import Speech\n"
            "def make():\n    import vendor.services.acme\n"
            "try:\n    import vendor.services.acme\nexcept ImportError:\n    pass\n"
            "class Holder:\n    from vendor.services import acme\n"
        ),
    }
    assert _bans(tmp_path, files) == [
        ("src/app/core/c.py", n, "vendor.services") for n in (3, 5, 7, 11)
    ]


def test_allowed_modules_and_other_imports_pass(tmp_path: Path) -> None:
    files = {
        "src/app/services/ok.py": (
            "from vendor.services.base import Base\nfrom vendor.services import base, settings\n"
            "import vendor.services.base.sub\nimport vendor.servicesx\nimport vendor.pipeline\n"
            "from . import ok\nfrom ..core import x\nimport importlib\n"
            "importlib.import_module(name)\nimportlib.import_module('.base', 'vendor.services')\n"
            "importlib.import_module('.acme')\nimportlib.import_module('.acme', anchor)\n"
            "other.import_module('vendor.services.acme')\n__import__('')\n"
            "__import__('acme', None, None, (), level)\nimportlib.import_module('...acme', 'a')\n"
        ),
        "src/app/adapters/rtc_user.py": "import rtc\n",  # the apps' ban does not cover the library
    }
    assert _bans(tmp_path, files) == []


def test_a_ban_on_a_part_of_the_library_covers_only_that_part(tmp_path: Path) -> None:
    """The subpackage's ban also refuses a module the library-wide ban allows; a sibling whose
    name starts with the same letters is not inside it."""
    files = {
        "src/app/services/reports/__init__.py": "import vendor\n",
        "src/app/services/reports/pdf.py": "from vendor.services.base import Base\n",
        "src/app/services/report.py": "import vendor.pipeline\n",
        "src/app/services/reportsx.py": "import vendor\n",
    }
    assert _bans(tmp_path, files) == [
        ("src/app/services/reports/__init__.py", 1, "vendor"),
        ("src/app/services/reports/pdf.py", 1, "vendor"),
    ]


def test_a_ban_on_a_part_of_the_library_follows_the_librarys_imports(tmp_path: Path) -> None:
    """A covered module may not reach a banned module through the library's own modules outside
    the ban, however it imports them; a covered module that imports one itself is refused there
    alone."""
    files = {
        "src/app/services/bridge.py": "import vendor\n",
        "src/app/services/hub.py": "from app.core import loop\nfrom . import bridge\n",
        "src/app/core/__init__.py": "from . import loop\n",
        "src/app/core/loop.py": "import app.services.hub\n",  # a cycle
        "src/app/core/clean.py": "from app.services.reports import pdf\n",
        "src/app/services/reports/x.py": "from app.services.bridge import Y\n",
        "src/app/services/reports/y.py": "from ..hub import Z\nfrom app.core import clean\n",
        "src/app/services/reports/z.py": "import importlib\nimportlib.import_module('app.core')\n",
        "src/app/services/reports/pdf.py": "from . import x\nimport vendor.pipeline\n",
    }
    assert [(v.path, v.line, v.problem) for v in _violations(tmp_path, files)] == [
        (
            "src/app/services/reports/pdf.py",
            2,
            "'vendor.pipeline' is banned in 'app.services.reports' ([[bans]]: 'vendor')",
        ),
        (
            "src/app/services/reports/x.py",
            1,
            "'app.services.bridge.Y' leads to 'vendor' (app.services.bridge -> vendor), banned in "
            "'app.services.reports' ([[bans]]: 'vendor')",
        ),
        (
            "src/app/services/reports/y.py",
            1,
            "'app.services.hub.Z' leads to 'vendor' (app.services.hub -> app.services.bridge -> "
            "vendor), banned in 'app.services.reports' ([[bans]]: 'vendor')",
        ),
        (
            "src/app/services/reports/z.py",
            2,
            "'app.core' leads to 'vendor' (app.core -> app.core.loop -> app.services.hub -> "
            "app.services.bridge -> vendor), banned in 'app.services.reports' ([[bans]]: 'vendor')",
        ),
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
    files = {"src/app/services/reports/x.py": "from vendor.services import acme\n"}
    assert [str(v) for v in _violations(tmp_path, files)] == [
        "src/app/services/reports/x.py:1: [ARCH-BAN] 'vendor.services.acme' is banned in 'app' "
        "([[bans]]: 'vendor.services')\n    FIX: Subclass the vendor's base service only.",
        "src/app/services/reports/x.py:1: [ARCH-BAN] 'vendor.services.acme' is banned in "
        "'app.services.reports' ([[bans]]: 'vendor')\n    FIX: Reports never touch the vendor.",
    ]


def test_a_module_that_does_not_parse_is_left_to_arch_parse(tmp_path: Path) -> None:
    """Neither its own imports nor a covered module's import of it are read."""
    files = PACKAGES | {
        "src/app/core/broken.py": "import vendor.services.acme\ndef (:\n",
        "src/app/services/reports/x.py": "from app.core import broken\n",
    }
    write(tmp_path, files)
    violations, _ = check_repo(tmp_path, config(tmp_path, SYNTHETIC + BANS))
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
        # Pipecat's other LLM machinery
        "pipecat.flows.manager",
        "pipecat.pipeline.llm_switcher",
        "pipecat.pipeline.llm_with_backend.llm_with_backend",
        "pipecat.workers.llm.backend_llm_worker",
        "pipecat.processors.frameworks.langchain",
        "pipecat.processors.frameworks.strands_agents",
        # what reaches a host outside the design's 11, and RTVI
        "pipecat.classifiers.openai.decisions.client",
        "pipecat.classifiers.cloudflare.clef.client",
        "pipecat.audio.turn.smart_turn.http_smart_turn",
        "pipecat.serializers.twilio",
        "pipecat.transports.daily.transport",
        "pipecat.transports.livekit.transport",
        "pipecat.transports.websocket.server",
        "pipecat.processors.frameworks.rtvi.processor",
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
        "pipecat.transports.base_output",
        "pipecat.pipeline.worker",
        "pipecat.workers.runner",
        "pipecat.turns.user_turn_strategies",
        "pipecat.turns.user_stop.turn_analyzer_user_turn_stop_strategy",
        "pipecat.frames.frames",
    ):
        assert not _banned(arch, voice, name), name
    assert _banned(arch, "t2_agentic_voice.voice.session.io", "pipecat.frames.frames")
    assert _banned(arch, "t2_agentic_voice.voice.session", "pipecat.services.stt_service")
    for app in arch.apps:
        for name in ("pipecat.pipeline.worker", "aiortc", "aiortc.rtcpeerconnection"):
            assert _banned(arch, f"{app.name}.server", name), (app.name, name)


def test_a_ban_whose_code_was_renamed_fails_the_config() -> None:
    """The session's ban, its `within` renamed to code that does not exist, would guard
    nothing: harness.toml is refused instead (HARNESS-CONFIG)."""
    loaded = load_config(ROOT).arch
    lines = Lines((ROOT / "harness.toml").read_text(encoding="utf-8"))
    session, renamed = "t2_agentic_voice.voice.session", "t2_agentic_voice.voice.calls_session"
    bans = tuple(
        replace(b, within=(renamed,)) if b.within == (session,) else b for b in loaded.bans
    )
    assert bans != loaded.bans and missing_scopes(ROOT, loaded, lines) == []
    folder = f"{loaded.package_dir}/voice/calls_session"
    assert [v.problem for v in missing_scopes(ROOT, replace(loaded, bans=bans), lines)] == [
        f"[[bans]] within '{renamed}' names no package or module: neither "
        f"{folder}/__init__.py nor {folder}.py exists"
    ]


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
    ("source", "package", "found"),
    [
        ("from a.b import c as d, e\n", None, ["a.b.c", "a.b.e"]),
        ("import a.b as c, d\n", None, ["a.b", "d"]),
        ("from . import a\nfrom .b import c\n", None, []),
        ("from . import a\nfrom ..b import c\nfrom ... import d\n", "p.q", ["p.q.a", "p.b.c"]),
        (
            "__import__('b', globals(), None, (), 2)\n__import__('c', level=1)\n",
            "p.q",
            ["p.b", "p.q.c"],
        ),
        ("__import__('b', globals(), None, (), 1)\n", None, []),
        ("import importlib\nimportlib.import_module(f'{x}')\n", None, ["importlib"]),
    ],
)
def test_imports_are_read_as_modules(source: str, package: str | None, found: list[str]) -> None:
    """Relative imports are resolved against the module's package, when it is given."""
    assert [name for name, _ in imported(ast.parse(source), package)] == found

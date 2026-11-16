"""The flight-booking agent is an app like a teammate's (D-101): registered in harness.toml, it
imports the library only through its public modules, and no other app, Pipecat or aiortc. The
gate's `arch` step checks every app so; this holds the flight app's own registration to it."""

from __future__ import annotations

import ast
from pathlib import Path

from scripts.harness_config import load_config

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "apps" / "flight-voice-agent" / "src"
FORBIDDEN = ("ole5_voice", "minimal_example", "pipecat", "aiortc")


def _imports(path: Path) -> list[str]:
    names = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names += [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            names.append(node.module)
    return names


def test_the_app_is_registered_with_the_harness() -> None:
    config = load_config(ROOT)
    apps = {app.name: app.dir for app in config.arch.apps}
    assert apps["flight_voice"] == "apps/flight-voice-agent/src/flight_voice"


def test_the_app_imports_only_the_librarys_public_modules_and_no_other_app() -> None:
    public = load_config(ROOT).arch.public
    modules = sorted(SOURCE.rglob("*.py"))
    assert modules, "the app's package holds no module"
    for path in modules:
        for name in _imports(path):
            where = path.relative_to(ROOT).as_posix()
            assert not name.startswith(FORBIDDEN), f"{where} imports {name}"
            if name.split(".")[0] == "t2_agentic_voice":
                assert name in public, f"{where} imports {name}, not a public module"

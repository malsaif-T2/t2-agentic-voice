"""This repository's [[bans]] against the installed Pipecat, read without importing it
(scripts/arch_ban.py; plan 003's reading of Pipecat 1.15.0): every module a ban names exists; the
services and the transports the library's bans allow are what the speech base classes and the
Small WebRTC transport import; and every Pipecat module that imports an HTTP or websocket client,
or a module the library's bans refuse, is banned in the library or reviewed below, with the reason
voice may import it. So a new Pipecat that adds such a module fails here until someone reads it."""

from __future__ import annotations

import ast
import importlib.util
from collections.abc import Iterator
from pathlib import Path

from scripts.arch_ban import imported
from scripts.harness_arch import Ban, under
from scripts.harness_config import load_config

ROOT = Path(__file__).resolve().parents[2]
# The clients a module reaches another host with.
CLIENTS = ("aiohttp", "httpx", "requests", "websockets")
# The Pipecat modules voice may import although they import a client or a banned module: each
# with why that reaches no host and runs none of what the bans keep out.
REVIEWED = {
    "pipecat.frames.frames": (
        "Every pipeline's frame types. It imports the LLM tool schemas and context types for the "
        "LLM frames, which voice never builds."
    ),
    "pipecat.pipeline.worker": (
        "PipelineWorker runs each call. Its bus stays in the process, with no bridge added, and "
        "voice passes `enable_rtvi=False`, so RTVI is never built."
    ),
    "pipecat.workers.base_worker": "PipelineWorker's base; its bus stays in the process.",
    "pipecat.workers.runner": "WorkerRunner runs the calls' workers; its bus stays in the process.",
    "pipecat.services.stt_service": (
        "The base class of voice's speech-to-text bridge, which calls the port. The websocket "
        "import serves its websocket subclasses, which the services ban keeps out."
    ),
    "pipecat.services.tts_service": (
        "The base class of voice's text-to-speech bridge, which calls the port. The websocket "
        "import serves its websocket subclasses, which the services ban keeps out."
    ),
    "pipecat.services.websocket_service": (
        "A base the two speech base classes import; only a provider's service, banned, connects."
    ),
    "pipecat.transports.smallwebrtc.request_handler": (
        "The WebRTC signalling voice serves. It imports the runner's SDP munging only in ESP32 "
        "mode, which the library never turns on."
    ),
    "pipecat.turns.user_stop": (
        "The package voice imports Smart Turn's stop strategy from. It also re-exports the "
        "strategies a classifier or an LLM runs, whose own modules are banned; a `from` import "
        "of those names from the package is not seen (review keeps voice to Smart Turn's)."
    ),
    "pipecat.turns.user_turn_strategies": (
        "Configures how VAD and Smart Turn v3 open and close a turn. It imports the classifier "
        "and LLM context types for the strategies a classifier or an LLM runs, which are banned."
    ),
    "pipecat.utils.tracing.service_decorators": (
        "The speech base classes' span decorators; it imports one constant of the LLM context, "
        "and Pipecat's own tracing stays off."
    ),
}


def _source(module: str) -> Path:
    """The installed file or folder of a dotted module name, found without importing it."""
    top, *parts = module.split(".")
    spec = importlib.util.find_spec(top)
    assert spec is not None and spec.submodule_search_locations, top
    path = Path(next(iter(spec.submodule_search_locations)), *parts)
    return path if path.is_dir() else path.with_suffix(".py")


def _library_bans() -> list[Ban]:
    """The bans on the whole library: what no module of it may import."""
    arch = load_config(ROOT).arch
    return [ban for ban in arch.bans if arch.package in ban.within]


def _banned(bans: list[Ban], name: str) -> str | None:
    """The prefix under which one of `bans` refuses `name`, if one does."""
    return next((prefix for ban in bans if (prefix := ban.banned(name)) is not None), None)


def _modules(package: str) -> Iterator[tuple[str, Path, str]]:
    """Each installed module of `package`, with its file and the package it sits in."""
    folder = _source(package)
    for path in sorted(folder.rglob("*.py")):
        parts = path.relative_to(folder.parent).with_suffix("").parts
        if "__pycache__" not in parts:
            name = ".".join(parts[:-1] if parts[-1] == "__init__" else parts)
            yield name, path, name if parts[-1] == "__init__" else name.rpartition(".")[0]


def _imports(path: Path, package: str) -> list[str]:
    """What the module at `path`, in `package`, imports, as ARCH-BAN reads it."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [name for name, _ in imported(tree, package)]


def _reaches(path: Path, package: str, bans: list[Ban]) -> list[str]:
    """The clients, and the prefixes of `bans`, that the module at `path` imports."""
    names = _imports(path, package)
    clients = {name.split(".")[0] for name in names} & set(CLIENTS)
    return sorted(clients | {prefix for name in names if (prefix := _banned(bans, name))})


def reaching(bans: list[Ban]) -> dict[str, list[str]]:
    """Each installed Pipecat module that imports a client or a module `bans` refuse, with the
    clients and the bans' prefixes it imports."""
    found = {}
    for module, path, package in _modules("pipecat"):
        if what := _reaches(path, package, bans):
            found[module] = what
    return found


def test_every_pipecat_module_that_reaches_out_is_banned_or_reviewed() -> None:
    bans = _library_bans()
    found = reaching(bans)
    allowed = {module: what for module, what in found.items() if _banned(bans, module) is None}
    assert {module: allowed[module] for module in sorted(allowed.keys() - REVIEWED.keys())} == {}, (
        "FIX: read what each of these modules sends, and where: ban it in a [[bans]] table of "
        "harness.toml whose fix says what to do instead, or, if voice needs it and it reaches "
        "no host by itself, add it to REVIEWED with why."
    )
    assert sorted(REVIEWED.keys() - allowed.keys()) == [], "FIX: remove it from REVIEWED."
    assert all(REVIEWED.values())
    assert "pipecat.services.groq.stt" in found and _banned(bans, "pipecat.services.groq.stt")


def test_the_walk_finds_a_client_or_a_banned_import(tmp_path: Path) -> None:
    """On made-up modules: a client in any form, a banned module, a relative import resolved."""
    bans = [Ban(("pipecat.bus",), (), ("t2_agentic_voice",), "fix")]
    sources = {
        "a.py": "import httpx.x\n",
        "b.py": "def f():\n    from websockets.asyncio import client\n",
        "c.py": "from .bus import queue\n",
        "d.py": "import json\nimport requestsx\n",
    }
    found = {}
    for name, text in sources.items():
        (tmp_path / name).write_text(text, encoding="utf-8")
        found[name] = _reaches(tmp_path / name, "pipecat", bans)
    assert found == {"a.py": ["httpx"], "b.py": ["websockets"], "c.py": ["pipecat.bus"], "d.py": []}


def test_every_module_a_ban_names_is_in_the_installed_package() -> None:
    """A module renamed or moved by a new version would leave its ban guarding nothing."""
    names = {n for ban in load_config(ROOT).arch.bans for n in (*ban.modules, *ban.allowed)}
    assert [n for n in sorted(names) if not _source(n).exists()] == []


def _closure(start: list[str], inside: str) -> set[str]:
    """`start`, and every module of `inside` they import, by its name under `inside` (one part
    more), read from the installed source, and those modules' own, and so on."""
    needed: set[str] = set()
    todo = list(start)
    while todo:
        module = todo.pop()
        needed.add(module)
        folder = _source(module)
        files = sorted(folder.rglob("*.py")) if folder.is_dir() else [folder]
        package = module if folder.is_dir() else module.rpartition(".")[0]
        for path in files:
            for name in _imports(path, package):
                found = ".".join(name.split(".")[: inside.count(".") + 2])
                if under(name, inside) and name != inside and found not in needed | set(todo):
                    todo.append(found)
    return needed


def test_the_allowed_services_are_what_the_speech_bases_import() -> None:
    """The services ban allows the base classes voice's bridges subclass and every module of
    `pipecat.services` they import, read from the installed source, and nothing else."""
    (ban,) = [b for b in load_config(ROOT).arch.bans if "pipecat.services" in b.modules]
    bases = ["pipecat.services.stt_service", "pipecat.services.tts_service"]
    assert set(ban.allowed) == _closure(bases, "pipecat.services")
    assert "pipecat.services.ai_service" in ban.allowed


def test_the_allowed_transports_are_what_small_webrtc_imports() -> None:
    """Every transport but Small WebRTC is banned; the modules of `pipecat.transports` it imports
    stay allowed, and nothing else."""
    (ban,) = [b for b in _library_bans() if "pipecat.transports" in b.modules]
    small = "pipecat.transports.smallwebrtc"
    assert set(ban.allowed) == _closure([small], "pipecat.transports")
    assert {"pipecat.transports.base_input", "pipecat.transports.base_output"} < set(ban.allowed)

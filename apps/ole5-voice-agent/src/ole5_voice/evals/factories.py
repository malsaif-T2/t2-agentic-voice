"""How runs K, S and T build the agent they measure and its knowledge base: from two factories
named on the command line as `module:name` inside `ole5_voice` (`load_factory`), so a run
measures the app's own declaration through the library's public API, each run the same way.

- `--knowledge` names the knowledge base's factory, given the run's env file (`env_file_of`):
  Ole5's is `ole5_voice.knowledge_base:knowledge_base`, which reads the knowledge base's access
  alone, so a run needs no access code or widget setting.
- `--agent` names the agent's factory, given that knowledge base: Ole5's is
  `ole5_voice.agent:talker_agent`. Run T's pass with no search (Tn, `--no-tools`) gives it
  None and builds no knowledge base, so its agent is the same talker with no tool.

`Closing` holds what a run built that keeps connections open (the knowledge base, the chat
model, the speech adapters) and closes each once, whenever the run ends: after its last
variant, an interrupt, an error, or a refusal that comes once they are built.
"""

from __future__ import annotations

import argparse
import asyncio
import importlib
from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

from t2_agentic_voice import VoiceAgent
from t2_agentic_voice.ports import KnowledgeBase

from ole5_voice.evals import run_settings
from ole5_voice.evals.worktree import refused

AgentFactory = Callable[[KnowledgeBase | None], VoiceAgent]
KnowledgeFactory = Callable[[Path | None], KnowledgeBase]
Loader = Callable[[str], Callable[..., object]]
_T = TypeVar("_T")


def load_factory(spec: str) -> Callable[..., object]:
    """The callable `spec` names as `module:name`, inside `ole5_voice`; refused otherwise."""
    module, colon, name = spec.partition(":")
    fix = "name a callable of the Ole5 app as ole5_voice.<module>:<name>"
    if not colon or not module.startswith("ole5_voice.") or not name.isidentifier():
        raise refused(f"{spec} is not a module:name inside ole5_voice", fix)
    found: object
    try:
        found = getattr(importlib.import_module(module), name)
    except (ImportError, AttributeError):
        found = None
    if not callable(found):
        raise refused(f"{spec} names no callable", fix)
    return found


def env_file_of(args: argparse.Namespace) -> Path | None:
    """The env file a run's settings and knowledge base load from: `--env-file`, or the working
    folder's `.env` when it names none (`run_settings.DOTENV`)."""
    env_file: Path | None = args.env_file
    dotenv = run_settings.DOTENV
    if env_file is None and dotenv is not None and dotenv.is_file():
        env_file = dotenv
    return env_file


def knowledge_of(load: Loader, spec: str, env_file: Path | None) -> KnowledgeBase:
    """The knowledge base the factory `spec` builds from `env_file`; refused when it gives
    none."""
    kb = load(spec)(env_file)
    if not callable(getattr(kb, "search", None)):
        raise refused(f"--knowledge {spec} gave no knowledge base", "name its factory")
    return kb  # type: ignore[return-value]  # its `search` is checked above


def agent_of(load: Loader, spec: str, kb: KnowledgeBase | None) -> VoiceAgent:
    """The agent the factory `spec` builds on `kb` (None: no knowledge base); refused when it
    gives no `VoiceAgent`."""
    agent = load(spec)(kb)
    if not isinstance(agent, VoiceAgent):
        raise refused(f"--agent {spec} gave no VoiceAgent", "name the agent's factory")
    return agent


class Closing:
    """What a run built that keeps connections open, each closed once (the module's
    docstring)."""

    def __init__(self) -> None:
        self._open: list[object] = []

    def add(self, built: _T) -> _T:
        """`built`, to be closed when the run ends (when it has an `aclose`)."""
        self._open.append(built)
        return built

    async def aclose(self) -> None:
        """Close each, the last built first; a second call closes nothing more."""
        while self._open:
            close = getattr(self._open.pop(), "aclose", None)
            if close is not None:
                await close()

    def close_now(self) -> None:
        """Close what is still open, outside any event loop (a refusal before a run starts,
        or after its loop has ended)."""
        if self._open:
            asyncio.run(self.aclose())

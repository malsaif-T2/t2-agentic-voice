"""The minimal example, an echo agent on the public API alone (the design's 4.2 and 9.8): its
runtime is made with no IO, from the settings given or the environment's; `python -m
minimal_example` sends the example's loggers and `__main__`'s to the output with the library's
and serves it; and a call joins it and offers. No key and no network: the providers, voice's
entry point and the identity source are the library's test fakes."""

from __future__ import annotations

import asyncio
import logging
import runpy
import sys
from collections.abc import Callable
from pathlib import Path

import pytest
from minimal_example import LOGGERS
from minimal_example import __main__ as started
from minimal_example.app import agent, make_runtime
from t2_agentic_voice import VoiceRuntime, VoiceSettings
from t2_agentic_voice import server as serving_facade
from t2_agentic_voice.identity import DevIdentity

from tests.t2_agentic_voice.api.runtime_support import (
    Harness,
    dev_settings,
    joined,
    offered,
    patch_stores,
    serving,
)


def test_the_agent_echoes_in_english_and_saudi_arabic() -> None:
    assert agent.name == "minimal-echo"
    assert [language.tag for language in agent.languages] == ["en", "ar-SA"]


def test_its_runtime_is_made_with_no_io(tmp_path: Path) -> None:
    settings = dev_settings(tmp_path)
    runtime = make_runtime(settings)
    assert isinstance(runtime, VoiceRuntime)
    assert isinstance(runtime._identity, DevIdentity) and runtime._settings is settings
    assert not settings.storage.var_dir.exists()


def test_its_runtime_loads_the_settings_from_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("T2V_ENV", "dev")
    assert make_runtime()._settings.env == "dev"


def test_it_starts_with_its_loggers_and_serves_the_echo_agent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("T2V_ENV", "dev")
    factories: list[Callable[[], VoiceRuntime]] = []
    monkeypatch.setattr(started, "serve", factories.append)
    started.main()
    assert LOGGERS == ("minimal_example", "__main__")
    for name in (*LOGGERS, "uvicorn", "t2_agentic_voice"):
        assert logging.getLogger(name).handlers, name
    [factory] = factories
    assert factory()._settings.env == "dev"


def test_python_m_minimal_example_starts_it(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("T2V_ENV", "dev")
    factories: list[Callable[[], VoiceRuntime]] = []
    monkeypatch.setattr(serving_facade, "serve", factories.append)
    monkeypatch.delitem(sys.modules, "minimal_example.__main__")
    runpy.run_module("minimal_example", run_name="__main__")
    assert len(factories) == 1


def test_a_call_joins_the_echo_agent_and_offers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    patch_stores(monkeypatch)
    harness = Harness(dev_settings(tmp_path), agent=agent)  # the example's agent, on the fakes

    async def scene() -> None:
        async with serving(harness.app()) as http:
            call_id, secret = await joined(http, language="ar-SA")
            assert (await offered(http, call_id, secret)).status_code == 200
        assert harness.calls.offers[call_id][3] == agent.languages[1]

    asyncio.run(scene())


def test_settings_built_in_code_reach_the_runtime(settings: VoiceSettings) -> None:
    assert make_runtime(settings)._settings is settings

"""The runtime hands its calls the agent's action runner (api/runtime.py; plan 007's integration):
voice's entry point is built with `action_jobs`, the runtime's one runner, or None for an agent
with no actions; and a served call's confirmed action reaches the runtime's observers once.

The served call is one call as a browser makes it (loopback_support.py): a local aiortc peer
joins and offers through the runtime's router, then speaks twice into the real pipeline and
session, each call's speech detector the fakes' tone detector and its turn analyzer one that
ends each turn at its first pause. The library's `ChatTalker` writes on a `ScriptedLLM` that
calls the action; the session reads the draft back and confirms it; the real yes rule takes the
caller's yes with a send word; the runtime's own runner writes once, on its SQLite outbox under
the test's folder; and its observers hear one `ActionCompleted`."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from t2_agentic_voice.actions.action_runner import ActionRunner
from t2_agentic_voice.actions.memory_outbox import MemoryOutbox
from t2_agentic_voice.adapters.outbox import SqliteOutbox
from t2_agentic_voice.api.actions import outbox_path
from t2_agentic_voice.api.runtime import Providers, VoiceRuntime
from t2_agentic_voice.core.events import (
    ActionCompleted,
    ActionUnconfirmed,
    ConfirmationAnswered,
    Event,
)
from t2_agentic_voice.domain.yes_words import PRESET_CONSENT
from t2_agentic_voice.evals import ScriptedLLM
from t2_agentic_voice.identity import DevIdentity
from t2_agentic_voice.voice.calls import Calls

from tests.t2_agentic_voice.actions.action_support import DONE, SUMMARY, Backend, an_action
from tests.t2_agentic_voice.api.runtime_support import Harness, dev_settings, serving
from tests.t2_agentic_voice.api.test_runtime_actions import _agent, _Runtime
from tests.t2_agentic_voice.fakes import FakeClock, FakeSpeechToText, FakeTextToSpeech
from tests.t2_agentic_voice.loopback_support import FAKE_DETECTORS, WAIT_S, Browser, run_call
from tests.t2_agentic_voice.voice.kit import until

REQUEST = f"please open a software request, {SUMMARY}"
# A yes with a send word, the English preset's own.
YES_SEND = f"{PRESET_CONSENT['en'].yes[0]} {PRESET_CONSENT['en'].send[1]}"
SPEECH_S = 0.6
# How long the caller waits once the read-back has played before saying yes: past the 300 ms
# after a reply that would make the turn an overlap.
AFTER_READ_BACK_S = 0.6
# How the outcome's caption opens: the action's done line, up to its number.
DONE_OPENING = DONE.for_language("en").split("{")[0]


@pytest.mark.usefixtures("patched_stores")
def test_the_calls_are_built_with_the_runtimes_action_runner(tmp_path: Path) -> None:
    rig = _Runtime(dev_settings(tmp_path))

    async def scene() -> None:
        async with serving(rig.app):
            (given,) = rig.given
            assert isinstance(rig.runtime._actions, ActionRunner)
            assert given["action_jobs"] is rig.runtime._actions

    asyncio.run(scene())


@pytest.mark.usefixtures("patched_stores")
def test_the_calls_of_an_agent_with_no_actions_get_no_action_jobs(tmp_path: Path) -> None:
    rig = Harness(dev_settings(tmp_path))

    async def scene() -> None:
        async with serving(rig.app()):
            (given,) = rig.built
            assert rig.runtime._actions is None and given["action_jobs"] is None

    asyncio.run(scene())


class _Served:
    """A runtime of the acting agent on the fakes, its calls voice's own with the fakes'
    detectors, and every action event its observers heard."""

    def __init__(self, tmp_path: Path) -> None:
        self.settings = dev_settings(tmp_path)
        self.backend = Backend(outbox=MemoryOutbox(), clock=FakeClock())
        self.agent = _agent(an_action(self.backend))
        self.stt = FakeSpeechToText([REQUEST, YES_SEND])
        chat = ScriptedLLM(
            [ScriptedLLM.call_tool("open_request", category="software", summary=SUMMARY)]
        )
        self.given: list[dict[str, Any]] = []
        self.heard: list[Event] = []

        def calls(**given: Any) -> Calls:
            self.given.append(given)
            return FAKE_DETECTORS(**given)

        self.runtime = VoiceRuntime(
            self.agent,
            settings=self.settings,
            identity=DevIdentity(),
            providers=Providers(
                stt=self.stt, tts=FakeTextToSpeech(seconds_per_char=0.02), chat=chat
            ),
            _calls=calls,
        )

        async def observe(event: Event) -> None:
            self.heard.append(event)

        for kind in (ActionCompleted, ActionUnconfirmed, ConfirmationAnswered):
            self.runtime.on(kind)(observe)
        self.app = FastAPI()
        self.app.include_router(self.runtime.router(), prefix="/voice")


def _states_since(browser: Browser, count: int) -> list[str]:
    """The states the session showed after its first `count` messages."""
    later = browser.messages[count:]
    return [m["state"] for m in later if m.get("v") == 1 and m["type"] == "state"]


def _outcome_at(browser: Browser) -> int | None:
    """The index of the message that captioned the outcome, None before it came."""
    for index, message in enumerate(browser.messages):
        caption = message.get("type") == "caption" and message.get("speaker") == "agent"
        if caption and str(message["text"]).startswith(DONE_OPENING):
            return index
    return None


async def _says_yes_once_read_back(browser: Browser) -> None:
    """Ask for the request, wait until the read-back has played and the session confirms, say a
    yes with a send word, and hang up once the outcome has played."""
    await browser.greeted()
    asked = len(browser.messages)
    browser.signal.say(SPEECH_S)
    await until(lambda: "speaking" in _states_since(browser, asked), timeout=WAIT_S)
    await until(lambda: _states_since(browser, asked)[-1] == "confirming", timeout=WAIT_S)
    await asyncio.sleep(AFTER_READ_BACK_S)
    browser.signal.say(SPEECH_S)
    await until(lambda: _outcome_at(browser) is not None, timeout=WAIT_S)
    said = _outcome_at(browser) or 0
    await until(lambda: _states_since(browser, said)[-1:] == ["listening"], timeout=WAIT_S)
    await browser.hang_up()


def test_a_served_calls_confirmed_action_reaches_the_observers_once(tmp_path: Path) -> None:
    rig = _Served(tmp_path)

    async def steps(browser: Browser, http: httpx.AsyncClient) -> None:
        await browser.connect(http)
        await _says_yes_once_read_back(browser)
        (given,) = rig.given
        assert isinstance(rig.runtime._actions, ActionRunner)
        assert given["action_jobs"] is rig.runtime._actions

    browser, left = run_call(rig.app, steps)
    assert not left, left
    assert [m["reason"] for m in browser.of("ended")] == ["hangup"]
    assert rig.stt.script == [] and len(rig.stt.calls) == 2  # one request for each turn
    completed = [e for e in rig.heard if isinstance(e, ActionCompleted)]
    assert [(type(e).__name__, getattr(e, "decision", None)) for e in rig.heard] == [
        ("ConfirmationAnswered", "yes"),
        ("ActionCompleted", None),
    ]
    (done,) = completed
    assert done.action == "open_request"
    (written,) = rig.backend.writes
    assert written[0].request_id == done.request_id
    assert written[1].summary == SUMMARY

    async def rows() -> list[tuple[str, str]]:
        outbox = await SqliteOutbox.open(outbox_path(rig.settings, rig.agent))
        try:
            return [(row.request_id, row.state) for row in await outbox.entries()]
        finally:
            await outbox.aclose()

    assert asyncio.run(rows()) == [(done.request_id, "done")]
    assert outbox_path(rig.settings, rig.agent).is_relative_to(tmp_path)

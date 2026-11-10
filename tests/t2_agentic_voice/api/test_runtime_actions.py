"""The composition of an agent's actions (api/actions.py, api/providers.py, api/runtime.py; plan
007, Track B): one action runner for every call of the runtime, on the SQLite outbox under
`storage.var_dir/<agent>/outbox.sqlite3`, the per-caller cap from the settings, emitting no
event of its own (the session reports each outcome); the rows an earlier process left `sending`
reconciled as the runtime starts, before any call, never sent again (invariant 6); each call's
talker given the runner and its own call's record; a call's record let go as it ends; the
outbox closed as the runtime stops; and an agent with no actions opening no outbox."""

from __future__ import annotations

import asyncio
import sqlite3
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from pydantic import BaseModel
from t2_agentic_voice.actions.action import Action
from t2_agentic_voice.actions.action_runner import ActionRunner
from t2_agentic_voice.actions.memory_outbox import MemoryOutbox
from t2_agentic_voice.actions.tools import Tool
from t2_agentic_voice.adapters.outbox import SqliteOutbox
from t2_agentic_voice.agent.talker import ChatTalker, TalkerCall
from t2_agentic_voice.api.actions import OUTBOX_NAME, outbox_path
from t2_agentic_voice.api.providers import Providers, actions_of, talkers, tools_of
from t2_agentic_voice.api.runtime import VoiceRuntime
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.events import (
    ActionCompleted,
    ActionUnconfirmed,
    CallEnded,
    CallReport,
    Event,
)
from t2_agentic_voice.core.identity import Caller
from t2_agentic_voice.core.settings.limits import LimitSettings
from t2_agentic_voice.domain.action_lines import ReadBackPlan
from t2_agentic_voice.domain.declaration import Language, VoiceAgent
from t2_agentic_voice.domain.ports.outbox import OutboxEntry
from t2_agentic_voice.testing.llm_fakes import FAKE_DATA_FLOW

from tests.t2_agentic_voice.actions.action_support import (
    CALL_ID,
    CALLER,
    Backend,
    RequestOpened,
    an_action,
    confirmed_of,
    context,
    request,
)
from tests.t2_agentic_voice.api.runtime_support import FakeIdentity, dev_settings, serving
from tests.t2_agentic_voice.fakes import FakeCalls, FakeClock, FakeSpeechToText, FakeTextToSpeech

pytestmark = pytest.mark.usefixtures("patched_stores")
NOW = datetime(2026, 11, 10, 9, 0, tzinfo=UTC)


class _Query(BaseModel):
    query: str


SEARCH = Tool(
    name="search_help", description="Search the help pages.", parameters=_Query, function=print
)


class _Chat:
    """A chat model no test asks."""

    name = "fake-chat"
    data_flow = FAKE_DATA_FLOW

    def stream(self, request: object) -> AsyncIterator[Any]:
        raise AssertionError("no request")

    async def aclose(self) -> None:
        """Nothing to close."""


def _agent(action: Action) -> VoiceAgent:
    return VoiceAgent(
        name="acting",
        languages=[Language.english(greeting="Hello.")],
        instructions="Answer briefly.",
        tools=[SEARCH, action],
    )


def _left_sending(path: Path, request_id: str) -> None:
    async def write() -> None:
        store = await SqliteOutbox.open(path)
        values: dict[str, Any] = {
            "request_id": request_id,
            "call_id": "call-0",
            "subject": "made-up-subject",
            "action": "open_request",
            "draft_json": '{"category": "software", "summary": "made up"}',
            "created_at": NOW,
            "updated_at": NOW,
        }
        await store.add(OutboxEntry.model_validate(values))
        await store.aclose()

    asyncio.run(write())


class _Runtime:
    """A runtime of the acting agent on the fakes, with what it handed its calls."""

    def __init__(self, settings: VoiceSettings, *, held: tuple[str, ...] = ()) -> None:
        self.backend = Backend(outbox=MemoryOutbox(), clock=FakeClock())
        for request_id in held:
            self.backend.held[request_id] = RequestOpened(number="2026111082000123")
        self.agent = _agent(an_action(self.backend))
        self.given: list[dict[str, Any]] = []
        self.chat = _Chat()

        def calls(**given: Any) -> FakeCalls:
            self.given.append(given)
            return FakeCalls()

        self.runtime = VoiceRuntime(
            self.agent,
            settings=settings,
            identity=FakeIdentity(),
            providers=Providers(stt=FakeSpeechToText(), tts=FakeTextToSpeech(), chat=self.chat),
            _calls=calls,
            _clock=FakeClock(),
        )
        self.app = FastAPI()
        self.app.include_router(self.runtime.router(), prefix="/voice")


def test_the_actions_are_left_to_their_runner_and_the_tools_to_theirs() -> None:
    agent = _agent(an_action(Backend(outbox=MemoryOutbox(), clock=FakeClock())))
    assert tools_of(agent) == (SEARCH,)
    assert [action.name for action in actions_of(agent)] == ["open_request"]


def test_each_calls_talker_is_given_the_one_runner_and_its_own_calls_record(
    settings: VoiceSettings,
) -> None:
    action = an_action(Backend(outbox=MemoryOutbox(), clock=FakeClock()))
    runner = ActionRunner([action], outbox=MemoryOutbox())
    factory = talkers(_agent(action), settings, _Chat(), runner)
    assert factory is not None
    first = factory(
        TalkerCall(call_id="c-1", caller=Caller(subject="s"), language="en"), FakeClock()
    )
    second = factory(
        TalkerCall(call_id="c-2", caller=Caller(subject="s"), language="en"), FakeClock()
    )
    assert isinstance(first, ChatTalker) and isinstance(second, ChatTalker)
    assert first.actions is runner and second.actions is runner
    assert first.record is runner.record("c-1") and second.record is runner.record("c-2")
    assert first.record is not second.record  # call A's entries never reach call B


def test_the_runtime_opens_the_runner_on_its_outbox_and_reconciles_before_any_call(
    tmp_path: Path,
) -> None:
    settings = dev_settings(tmp_path, limits=LimitSettings(actions_per_caller_per_day=3))
    rig = _Runtime(settings, held=("r-found",))
    path = outbox_path(settings, rig.agent)
    assert path == settings.storage.var_dir / "acting" / OUTBOX_NAME
    _left_sending(path, "r-found")
    _left_sending(path, "r-lost")
    seen: dict[str, Any] = {}

    async def scene() -> None:
        async with serving(rig.app):
            runner = rig.runtime._actions
            assert isinstance(runner, ActionRunner)
            seen["runner"] = runner
            outbox = runner._outbox
            seen["rows"] = {r.request_id: r.state for r in await outbox.entries()}
            (given,) = rig.given
            talker = given["talker"](
                TalkerCall(call_id="c-1", caller=Caller(subject="s"), language="en"), FakeClock()
            )
            seen["talker"] = talker

    asyncio.run(scene())
    runner: ActionRunner = seen["runner"]
    assert seen["rows"] == {"r-found": "done", "r-lost": "flagged"}
    assert rig.backend.writes == []  # never sent again
    assert runner._per_day == 3 and runner._writes._emit is None
    assert isinstance(seen["talker"], ChatTalker) and seen["talker"].actions is runner
    with pytest.raises(sqlite3.ProgrammingError):  # closed as the runtime stopped
        asyncio.run(runner._outbox.entries())


def test_the_runtimes_runner_leaves_each_outcomes_event_to_the_session(tmp_path: Path) -> None:
    """core/events.py: `voice` builds the events, so the session alone reports an outcome, from
    the `ActionOutcome` the runner returns; the runner the runtime opens emits none."""
    rig = _Runtime(dev_settings(tmp_path))
    observed: list[Event] = []

    async def heard(event: Event) -> None:
        observed.append(event)

    rig.runtime.on(ActionCompleted)(heard)
    rig.runtime.on(ActionUnconfirmed)(heard)

    async def scene() -> str:
        async with serving(rig.app):
            runner = rig.runtime._actions
            assert runner is not None
            clock = FakeClock()
            plan = await runner.propose(request(), context(), clock=clock)
            assert isinstance(plan, ReadBackPlan)
            outcome = await runner.run(
                confirmed_of(plan),
                caller=CALLER,
                call_id=CALL_ID,
                language="en",
                turn_id=9,
                conversation=(),
                clock=clock,
            )
            return outcome.kind

    assert asyncio.run(scene()) == "done" and len(rig.backend.writes) == 1
    assert observed == []  # the observers' queue drained as the runtime stopped


def test_a_calls_record_is_let_go_as_the_call_ends(tmp_path: Path) -> None:
    rig = _Runtime(dev_settings(tmp_path))

    async def scene() -> tuple[bool, bool]:
        async with serving(rig.app):
            runner = rig.runtime._actions
            assert runner is not None
            kept = runner.record("c-1")
            report = CallReport(
                call_id="c-1", agent="acting", started_at=NOW, ended_at=NOW, ended_by="hangup"
            )
            rig.runtime._emit(CallEnded(call_id="c-1", at=NOW, report=report))
            return runner.record("c-1") is not kept, runner.record("c-2") is runner.record("c-2")

    assert asyncio.run(scene()) == (True, True)


def test_an_agent_with_no_actions_opens_no_outbox(tmp_path: Path) -> None:
    settings = dev_settings(tmp_path)
    agent = VoiceAgent(
        name="reader",
        languages=[Language.english(greeting="Hello.")],
        instructions="Answer briefly.",
        tools=[SEARCH],
    )
    runtime = VoiceRuntime(
        agent,
        settings=settings,
        identity=FakeIdentity(),
        providers=Providers(stt=FakeSpeechToText(), tts=FakeTextToSpeech(), chat=_Chat()),
        _calls=lambda **given: FakeCalls(),
    )
    app = FastAPI()
    app.include_router(runtime.router(), prefix="/voice")

    async def scene() -> None:
        async with serving(app):
            assert runtime._actions is None

    asyncio.run(scene())
    assert not outbox_path(settings, agent).exists()

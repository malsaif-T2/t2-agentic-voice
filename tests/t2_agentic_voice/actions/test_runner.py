"""The tool runner (actions/runner.py; the design's 6.4): a declared tool that is not a `Tool`
refused at construction; the model's argument text parsed before the function runs, an invalid
one answered with its field named and the function never called; the bound parameters filled
from the caller, never from the model; a sync function in a worker thread; the timeout on the
call's clock; a `ToolError`'s message to the talker, any other failure a generic one, logged by
its type and frames alone; and a cancel stopping the call at once."""

from __future__ import annotations

import asyncio
import logging
import threading
from collections.abc import Callable, Coroutine
from typing import Any

import pytest
from t2_agentic_voice.actions.runner import FAILED, ToolRunner
from t2_agentic_voice.actions.tools import CallContext, ToolResult, from_caller, tool
from t2_agentic_voice.core.errors import ConfigurationError, ToolError
from t2_agentic_voice.core.identity import Caller
from t2_agentic_voice.domain.cards import Card
from t2_agentic_voice.domain.declaration import Language, VoiceAgent
from t2_agentic_voice.domain.ports.chat_model import ToolCallRequest

from tests.leaks import holding, shown
from tests.t2_agentic_voice.fakes import FakeClock

CALLER = Caller(subject="made-up-subject", attributes={"team": "it"})
CTX = CallContext(caller=CALLER, call_id="call-1", language="en")
SECRET = "made-up-argument-4521"


def _request(name: str, arguments: str = "{}") -> ToolCallRequest:
    return ToolCallRequest(id="c-1", name=name, arguments=arguments)


def _run(
    runner: ToolRunner, request: ToolCallRequest, clock: FakeClock | None = None
) -> ToolResult:
    return asyncio.run(runner.run(request, CTX, clock=clock or FakeClock()))


seen: list[dict[str, Any]] = []


@tool(description="Find a device.", bind={"owner": from_caller("subject")})
async def find_device(ctx: CallContext, tag: str, owner: str) -> dict[str, str]:
    seen.append({"tag": tag, "owner": owner, "call": ctx.call_id})
    return {"tag": tag, "owner": owner}


@tool(description="Count the open requests.", bind={"team": from_caller("attributes.team")})
def count_requests(team: str) -> int:
    seen.append({"team": team, "thread": threading.current_thread() is threading.main_thread()})
    return 3


def test_a_declared_tool_that_is_not_a_tool_is_refused_at_construction() -> None:
    class Shaped:
        name, description, progress = "search_help", "Search.", None

    with pytest.raises(ConfigurationError, match=r"not a Tool\. FIX: ") as raised:
        ToolRunner([find_device, Shaped()])  # what `VoiceAgent.tools` may hold
    assert raised.value.details == {"field": "tools"}
    with pytest.raises(ConfigurationError, match=r"share a name\. FIX: "):
        ToolRunner([find_device, find_device])


def test_the_runner_takes_an_agents_declared_tools() -> None:
    declared = VoiceAgent(
        name="helper", languages=[Language.english(greeting="Hi")], tools=[find_device]
    )
    assert ToolRunner(declared.tools).tools == (find_device,)


def test_the_runner_tells_the_schemas_and_finds_a_tool_by_name() -> None:
    runner = ToolRunner([find_device, count_requests])
    assert [schema.name for schema in runner.schemas()] == ["find_device", "count_requests"]
    assert runner.tool("count_requests") is count_requests and runner.tool("other") is None


def test_an_async_tool_runs_with_its_arguments_the_callers_bound_value_and_the_context() -> None:
    seen.clear()
    result = _run(ToolRunner([find_device]), _request("find_device", '{"tag": "LT-00423"}'))
    assert result == ToolResult(data={"tag": "LT-00423", "owner": "made-up-subject"})
    assert seen == [{"tag": "LT-00423", "owner": "made-up-subject", "call": "call-1"}]


def test_a_bound_parameter_the_model_gives_is_refused_and_never_used() -> None:
    """Invariant 3: identity comes from the session, never from a tool argument."""
    seen.clear()
    arguments = '{"tag": "LT-00423", "owner": "someone-else"}'
    result = _run(ToolRunner([find_device]), _request("find_device", arguments))
    assert not result.ok and seen == []
    assert result.data == {"error": "invalid arguments: `owner`: Extra inputs are not permitted"}


def test_a_sync_tool_runs_in_a_worker_thread() -> None:
    seen.clear()
    result = _run(ToolRunner([count_requests]), _request("count_requests"))
    assert result == ToolResult(data=3)
    assert seen == [{"team": "it", "thread": False}]


@pytest.mark.parametrize(
    ("arguments", "told"),
    [
        ("{not json", "the arguments are not JSON: give a JSON object of the tool's parameters"),
        ("[1, 2]", "the arguments are a JSON object of the tool's parameters"),
        ("{}", "invalid arguments: `tag`: Field required"),
        ('{"tag": 5}', "invalid arguments: `tag`: Input should be a valid string"),
    ],
)
def test_an_invalid_argument_goes_back_to_the_talker_with_its_field_named(
    arguments: str, told: str
) -> None:
    seen.clear()
    result = _run(ToolRunner([find_device]), _request("find_device", arguments))
    assert result == ToolResult(data={"error": told}, ok=False)
    assert seen == []  # the function never ran


def test_an_invalid_argument_never_repeats_its_value() -> None:
    @tool(description="Made up.")
    async def pick(choice: int) -> int:
        return choice

    result = _run(ToolRunner([pick]), _request("pick", f'{{"choice": "{SECRET}"}}'))
    assert not result.ok and SECRET not in str(result.data)


def test_a_tool_the_agent_does_not_have_is_answered_with_the_tools_it_has() -> None:
    result = _run(ToolRunner([find_device]), _request("delete_everything"))
    assert result == ToolResult(
        data={"error": "there is no tool named `delete_everything`; the tools are: find_device"},
        ok=False,
    )


def test_a_tool_error_gives_the_talker_its_message() -> None:
    @tool(description="Made up.")
    async def strict(tag: str) -> str:
        raise ToolError("No device with that tag is assigned to you.")

    result = _run(ToolRunner([strict]), _request("strict", '{"tag": "x"}'))
    assert result == ToolResult(
        data={"error": "No device with that tag is assigned to you."}, ok=False
    )


def test_any_other_failure_is_generic_and_logged_by_its_type_never_its_text(
    caplog: pytest.LogCaptureFixture,
) -> None:
    @tool(description="Made up.")
    def broken(tag: str) -> str:
        raise KeyError(f"{SECRET} {tag}")

    caplog.set_level(logging.DEBUG, logger="t2_agentic_voice")
    result = _run(ToolRunner([broken]), _request("broken", f'{{"tag": "{SECRET}"}}'))
    assert result == ToolResult(data={"error": FAILED}, ok=False)
    [record] = [r for r in caplog.records if r.getMessage() == "tool_failed"]
    assert record.levelno == logging.ERROR
    fields = record.fields  # type: ignore[attr-defined]
    assert (fields["tool"], fields["failure"]) == ("broken", "KeyError")
    assert "test_runner.py" in fields["at"] and "broken" in fields["at"]
    assert holding(SECRET, shown(caplog=caplog)) == []


def test_a_bound_value_the_caller_does_not_hold_fails_and_is_logged() -> None:
    @tool(description="Made up.", bind={"room": from_caller("attributes.room")})
    async def room_of(room: str) -> str:
        return room

    result = _run(ToolRunner([room_of]), _request("room_of"))
    assert result == ToolResult(data={"error": FAILED}, ok=False)


def test_a_value_that_is_no_json_is_a_failure() -> None:
    @tool(description="Made up.")
    async def odd() -> object:
        return object()

    assert _run(ToolRunner([odd]), _request("odd")) == ToolResult(data={"error": FAILED}, ok=False)


def test_a_tool_result_returned_whole_is_kept_as_it_is() -> None:
    whole = ToolResult(data={"a": 1}, card=Card(title="Laptop"), evidence=("LT-00423",))

    @tool(description="Made up.")
    async def carded() -> ToolResult:
        return whole

    assert _run(ToolRunner([carded]), _request("carded")) == whole


async def _on_clock(step: Callable[[FakeClock], Coroutine[Any, Any, None]]) -> None:
    await asyncio.wait_for(step(FakeClock()), timeout=10)  # a hang fails, never blocks the run


async def _settle() -> None:
    for _ in range(5):
        await asyncio.sleep(0)


def test_the_timeout_is_timed_on_the_calls_clock(caplog: pytest.LogCaptureFixture) -> None:
    release = asyncio.Event()

    @tool(description="Made up.", timeout_s=2.0)
    async def slow() -> str:
        await release.wait()
        return "late"

    runner = ToolRunner([slow])

    async def steps(clock: FakeClock) -> None:
        task = asyncio.create_task(runner.run(_request("slow"), CTX, clock=clock))
        await _settle()
        await clock.advance(1.9)
        assert not task.done()  # only the call's clock times it out, never asyncio's
        await clock.advance(0.1)
        assert await task == ToolResult(data={"error": FAILED}, ok=False)

    caplog.set_level(logging.WARNING, logger="t2_agentic_voice")
    asyncio.run(_on_clock(steps))
    assert [r.getMessage() for r in caplog.records] == ["tool_timed_out"]


def test_a_cancel_stops_the_call_at_once() -> None:
    stopped: list[str] = []

    @tool(description="Made up.", timeout_s=30.0)
    async def endless() -> str:
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            stopped.append("cancelled")
            raise
        return "never"

    runner = ToolRunner([endless])

    async def steps(clock: FakeClock) -> None:
        task = asyncio.create_task(runner.run(_request("endless"), CTX, clock=clock))
        await _settle()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        await _settle()
        assert stopped == ["cancelled"]
        assert clock.sleeps == [30.0]

    asyncio.run(_on_clock(steps))

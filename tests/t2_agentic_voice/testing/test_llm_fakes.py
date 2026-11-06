"""The fake chat models (testing/llm_fakes.py; plan 006, Track A): `ScriptedLLM` plays one entry
per request, each a reply in a stream's pieces or tool calls, with its usage, its pauses on the
fake's clock and its errors, keeps every request, and fails clearly once its script has run out;
`FunctionLLM` answers each request as its function decides. Both keep the port's rules: one
`Done` last, a cancel that stops at once and leaves no task, and an id of their own for each tool
call. All on a clock that moves only when the test moves it."""

from __future__ import annotations

import asyncio
import contextlib
import json
from collections.abc import AsyncGenerator, AsyncIterator, Sequence
from typing import Any, cast

import pytest
from t2_agentic_voice.core.errors import ProviderError
from t2_agentic_voice.domain.ports.chat_model import (
    ChatEvent,
    ChatMessage,
    ChatModel,
    ChatRequest,
    Done,
    TextDelta,
    ToolCallRequest,
    ToolSchema,
    Usage,
)
from t2_agentic_voice.testing.llm_fakes import (
    AUTO_ID,
    FunctionLLM,
    Pause,
    ScriptedLLM,
    ScriptExhaustedError,
    ScriptStep,
)

from tests.t2_agentic_voice.fakes import FakeClock

SEARCH = ToolSchema(name="search_help", description="Search the help articles.")
ASKED = ChatRequest(
    messages=(ChatMessage.system("Be brief."), ChatMessage.user("How do I reset my password?")),
    tools=(SEARCH,),
    model="openai/gpt-oss-120b",
)
USAGE = Usage(input_tokens=900, output_tokens=12, cached_tokens=768)


def _answered(model: ChatModel, request: ChatRequest = ASKED) -> list[ChatEvent]:
    async def read() -> list[ChatEvent]:
        return [event async for event in model.stream(request)]

    return asyncio.run(read())


def test_a_reply_streams_in_a_models_pieces_its_usage_then_done() -> None:
    events = ScriptedLLM.reply("Open Settings, then Security. ", usage=USAGE)
    assert events == (
        TextDelta(text="Open"),
        TextDelta(text=" Settings,"),
        TextDelta(text=" then"),
        TextDelta(text=" Security."),
        TextDelta(text=" "),
        USAGE,
        Done(finish_reason="stop"),
    )
    arabic = ScriptedLLM.reply("افتح الإعدادات ثم الأمان")
    assert "".join(e.text for e in arabic if isinstance(e, TextDelta)) == "افتح الإعدادات ثم الأمان"
    assert ScriptedLLM.reply("") == (Done(finish_reason="stop"),)


def test_tool_calls_carry_their_arguments_as_the_model_writes_them() -> None:
    (call, done) = ScriptedLLM.call_tool("search_help", query="كلمة المرور", limit=3)
    assert isinstance(call, ToolCallRequest) and done == Done(finish_reason="tool_calls")
    assert (call.id, call.name) == (AUTO_ID, "search_help")
    assert call.arguments == '{"query": "كلمة المرور", "limit": 3}'
    assert json.loads(call.arguments) == {"query": "كلمة المرور", "limit": 3}
    both = ScriptedLLM.call_tools(("search_help", {"query": "x"}), ("open_card", {}), usage=USAGE)
    assert [type(event).__name__ for event in both] == [
        "ToolCallRequest",
        "ToolCallRequest",
        "Usage",
        "Done",
    ]


def test_the_script_plays_one_entry_per_request_and_keeps_every_request() -> None:
    llm = ScriptedLLM(
        [
            ScriptedLLM.call_tool("search_help", query="password"),
            ScriptedLLM.reply("Open Settings."),
        ]
    )
    port: ChatModel = llm  # mypy checks the port's shape
    after = ASKED.model_copy(update={"messages": (*ASKED.messages, ChatMessage.user("And?"))})
    first, second = _answered(port), _answered(port, after)
    assert first == [
        ToolCallRequest(id="call_1", name="search_help", arguments='{"query": "password"}'),
        Done(finish_reason="tool_calls"),
    ]
    assert second == [
        TextDelta(text="Open"),
        TextDelta(text=" Settings."),
        Done(finish_reason="stop"),
    ]
    assert llm.requests == [ASKED, after]
    assert llm.requests[0].tools == (SEARCH,)
    asyncio.run(llm.aclose())


def test_each_tool_call_of_a_conversation_gets_its_own_id_and_a_tests_own_is_kept() -> None:
    mine = ToolCallRequest(id="mine", name="search_help", arguments="{}")
    script: list[Sequence[ScriptStep]] = [
        ScriptedLLM.call_tools(("search_help", {"query": "a"}), ("search_help", {"query": "b"})),
        [mine, Done(finish_reason="tool_calls")],
        ScriptedLLM.call_tool("search_help", query="c"),
    ]
    runs = []
    for _ in range(2):  # the same ids in every run of a script
        llm = ScriptedLLM(script)
        ids = [e.id for _ in script for e in _answered(llm) if isinstance(e, ToolCallRequest)]
        runs.append(ids)
    assert runs == [["call_1", "call_2", "mine", "call_3"]] * 2


def test_an_entry_with_no_end_ends_with_one_done() -> None:
    call = ToolCallRequest(id="c", name="search_help", arguments="{}")
    llm = ScriptedLLM([[], [TextDelta(text="Hi")], [call]])
    assert llm.script == ((), (TextDelta(text="Hi"),), (call,))  # as the test gave it
    assert [_answered(llm)[-1] for _ in range(3)] == [
        Done(finish_reason="stop"),
        Done(finish_reason="stop"),
        Done(finish_reason="tool_calls"),
    ]


@pytest.mark.parametrize("pause", [Pause(0.4), 0.4])
def test_a_pause_waits_on_the_clock_the_fake_was_given(pause: float) -> None:
    clock = FakeClock()
    llm = ScriptedLLM([[pause, *ScriptedLLM.reply("Open Settings.")]])
    llm.clock = clock  # as a call that runs the fake on its own clock sets it

    async def scene() -> tuple[list[ChatEvent], list[ChatEvent]]:
        seen: list[ChatEvent] = []

        async def read() -> None:
            seen.extend([event async for event in llm.stream(ASKED)])

        task = asyncio.create_task(read())
        await clock.advance(0)  # the stream starts, and waits in its pause
        await clock.advance(0.39)
        before = list(seen)
        await clock.advance(0.01)
        await task
        return before, seen

    before, seen = asyncio.run(scene())
    assert before == [] and seen[0] == TextDelta(text="Open")
    assert clock.sleeps == [0.4]


@pytest.mark.parametrize("seconds", [-0.1, float("inf"), float("nan")])
def test_a_pause_lasts_a_finite_time(seconds: float) -> None:
    with pytest.raises(ValueError, match="a pause lasts a finite number of seconds"):
        Pause(seconds)
    with pytest.raises(ValueError, match="entry 1 of the script: step 1, a pause, lasts a finite"):
        ScriptedLLM([[seconds]])


async def _collect(stream: AsyncIterator[ChatEvent]) -> list[ChatEvent]:
    return [event async for event in stream]


@pytest.mark.parametrize("before", [0, 2])
def test_an_error_is_raised_from_the_stream_where_it_stands(before: int) -> None:
    error = ProviderError("rate_limited", True, 1.0)
    pieces = list(ScriptedLLM.reply("Open Settings now")[:before])
    llm = ScriptedLLM([[*pieces, error]])
    seen: list[ChatEvent] = []

    async def read() -> None:
        async for event in llm.stream(ASKED):
            seen.append(event)

    with pytest.raises(ProviderError) as raised:
        asyncio.run(read())
    assert raised.value is error and seen == pieces


WRONG: list[tuple[list[Any], str]] = [
    ([Done(finish_reason="stop"), TextDelta(text="late")], "step 1 ends the stream"),
    ([ProviderError("timeout", True), Done(finish_reason="stop")], "step 1 ends the stream"),
    ([USAGE, USAGE], "a stream reports its usage once"),
    (["Open Settings."], "step 1 is a str"),
    ([True], "step 1 is a bool"),
    ([TextDelta(text="Hi"), {"text": "x"}], "step 2 is a dict"),
]


@pytest.mark.parametrize(("entry", "says"), WRONG)
def test_a_wrong_entry_is_refused_when_the_fake_is_built(entry: list[Any], says: str) -> None:
    with pytest.raises(ValueError, match=f"entry 2 of the script: {says}"):
        ScriptedLLM([ScriptedLLM.reply("Hi"), entry])


def test_a_request_past_the_script_fails_clearly_with_the_requests_so_far() -> None:
    llm = ScriptedLLM([ScriptedLLM.call_tool("search_help", query="password")])
    _answered(llm)
    later = ASKED.model_copy(
        update={
            "messages": (*ASKED.messages, ChatMessage.tool_result("call_1", "Open Settings.")),
        }
    )
    with pytest.raises(ScriptExhaustedError) as raised:
        _answered(llm, later)
    message = str(raised.value)
    assert isinstance(raised.value, AssertionError)
    assert "script has 1 entries, and request 2 came after its last" in message
    assert message.count("last user text 'How do I reset my password?'") == 2
    assert "ending with a tool message, tools ['search_help']" in message
    assert len(llm.requests) == 2


def test_a_function_answers_each_request_by_what_it_holds() -> None:
    def answer(request: ChatRequest) -> list[ScriptStep]:
        last = request.messages[-1]
        if last.role == "tool":
            return list(ScriptedLLM.reply(f"From the result: {last.content}"))
        return [*ScriptedLLM.call_tool("search_help", query=last.content)]

    llm = FunctionLLM(answer)
    port: ChatModel = llm  # mypy checks the port's shape
    first = _answered(port)
    result = ASKED.model_copy(
        update={"messages": (*ASKED.messages, ChatMessage.tool_result("call_1", "Settings."))}
    )
    second = _answered(port, result)
    assert first[0] == ToolCallRequest(
        id="call_1", name="search_help", arguments='{"query": "How do I reset my password?"}'
    )
    assert (
        "".join(e.text for e in second if isinstance(e, TextDelta)) == "From the result: Settings."
    )
    assert llm.requests == [ASKED, result]
    asyncio.run(llm.aclose())


def test_a_functions_error_comes_from_the_stream_and_its_answer_ends_with_done() -> None:
    def failing(request: ChatRequest) -> list[ScriptStep]:
        raise ProviderError("connection_lost", True)

    llm = FunctionLLM(failing)
    stream = llm.stream(ASKED)  # nothing raised yet: the function runs when the stream starts
    assert len(llm.requests) == 1
    with pytest.raises(ProviderError) as raised:
        asyncio.run(_collect(stream))
    assert raised.value.kind == "connection_lost"
    plain = FunctionLLM(lambda request: [TextDelta(text="Hi")])
    assert _answered(plain) == [TextDelta(text="Hi"), Done(finish_reason="stop")]
    wrong = FunctionLLM(lambda request: cast("list[ScriptStep]", ["Hi"]))
    with pytest.raises(ValueError, match="the answer to request 1: step 1 is a str"):
        _answered(wrong)


@pytest.mark.parametrize("kind", ["scripted", "function"])
@pytest.mark.parametrize("how", ["cancel", "close"])
def test_a_stopped_stream_ends_at_once_and_leaves_no_task(kind: str, how: str) -> None:
    clock = FakeClock()
    steps: list[ScriptStep] = [TextDelta(text="Open"), Pause(5.0), *ScriptedLLM.reply("Settings")]
    fake = ScriptedLLM([steps]) if kind == "scripted" else FunctionLLM(lambda request: steps)
    fake.clock = clock
    llm: ChatModel = fake

    async def scene() -> tuple[list[ChatEvent], bool, set[asyncio.Task[Any]]]:
        stream = cast("AsyncGenerator[ChatEvent, None]", llm.stream(ASKED))
        seen = [await anext(stream)]
        if how == "close":
            await stream.aclose()
            stopped = True
        else:
            waiting = asyncio.create_task(anext(stream))
            await clock.advance(1.0)  # the stream waits in its pause
            waiting.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await waiting
            stopped = waiting.cancelled()
        await clock.advance(10.0)  # nothing more comes once it is stopped
        return seen, stopped, asyncio.all_tasks() - {asyncio.current_task()}

    seen, stopped, left = asyncio.run(scene())
    assert (seen, stopped, left) == ([TextDelta(text="Open")], True, set())

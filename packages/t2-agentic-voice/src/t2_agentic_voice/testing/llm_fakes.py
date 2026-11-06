"""The fake chat models (the design's 9.1; plan 006), for a team's tests and the library's: each
a `ChatModel` (domain/ports/chat_model.py) that sends nothing anywhere and keeps every request it
was given (`requests`), so a test reads the messages and tools the talker sent.

- **`ScriptedLLM`**: a script with one entry per model request, each the steps that request
  streams. A caller's turn that uses a read tool makes two requests: one that calls the tool,
  one that answers from its result. When the script runs out, the next request fails clearly
  (`ScriptExhaustedError`, an AssertionError), with the requests so far and the last user text of
  each, so a test that asked once too often says where. `reply(text)`, `call_tool(name,
  **arguments)` and `call_tools(...)` build an entry's events.
- **`FunctionLLM(fn)`**: a custom fake, `fn` taking each request and giving its steps, so a test
  need not count requests (one that answers by the last user text, or by a tool result).

**The steps** of an entry or of `fn`'s answer: the port's events (`TextDelta`, `ToolCallRequest`,
`Usage`, `Done`), played in order; a pause, a number of seconds (0 or more; `Pause(0.4)` names
one) the fake waits on its clock (a model's time to its first token, or between two pieces of its
text); and a `ProviderError`,
raised from the stream where it stands, the steps before it played (a failure before the first
token, or mid-reply). Nothing follows a `Done` or an error, and an answer reports its usage at
most once; an answer with no `Done` and no error ends with one, `tool_calls` when it called a
tool, else `stop`, so every stream keeps the port's rule.

**Tool call ids.** `call_tool` and `call_tools` give each call `AUTO_ID`, which the fake replaces
as it streams the call with the next of its own, `call_1`, `call_2` and so on, in the order of
its calls: each call of a conversation has its own id, the same in every run of a script. An id
a test writes itself is kept as it is.

**The clock.** A pause waits on the fake's `clock`, which whoever runs the fake sets before the
call starts: the call's (a virtual clock in a test, as `TextCall` runs on); while it is None,
the system's. It is an attribute, not a constructor's parameter, so no public signature names
the library's `Clock`, which no public module exports yet (D-032). A cancel stops a stream at
once, during a pause too, and leaves no task, as the port's rule says: the fake starts none.
"""

from __future__ import annotations

import asyncio
import itertools
import json
import math
import re
from collections.abc import AsyncIterator, Callable, Iterable, Iterator, Mapping, Sequence

from pydantic import JsonValue

from t2_agentic_voice.core.clock import SYSTEM_CLOCK, Clock
from t2_agentic_voice.core.errors import ProviderError
from t2_agentic_voice.domain.ports.chat_model import (
    ChatEvent,
    ChatRequest,
    Done,
    TextDelta,
    ToolCallRequest,
    Usage,
)
from t2_agentic_voice.domain.ports.speech_to_text import DataFlow

# Where a fake sends what it is given: nowhere.
FAKE_DATA_FLOW = DataFlow(
    provider="none (a fake in the test's process)",
    processed_in="the test's process",
    stored_in="nowhere",
    retention="none",
)
# The id `call_tool` gives a call, replaced by the fake's own as it streams it (above).
AUTO_ID = "call_auto"
# A piece of a reply's text as a model's stream gives it: a word, with the space before it (and
# a text's trailing space, so the pieces join into the text).
_PIECE = re.compile(r"\s*\S+|\s+$")


class Pause(float):
    """A step of a fake's answer that names itself: wait this many seconds (0 or more) on the
    fake's clock before the next step. Any number is a pause; this one says so where it stands,
    and refuses a wrong one at once."""

    def __new__(cls, seconds: float) -> Pause:
        return super().__new__(cls, _pause(seconds, "a pause"))


# A step of a fake's answer: an event, a pause (a number of seconds), or an error.
type ScriptStep = ChatEvent | float | ProviderError


class ScriptExhaustedError(AssertionError):
    """A request came after the last entry of a `ScriptedLLM`'s script: its message lists the
    requests so far, each with its last user text and the tools it offered."""


class ScriptedLLM:
    """A chat model that plays `script`, one entry per request, in order (the module's
    docstring); a `ChatModel`. Each entry is checked when the fake is built, a wrong one refused
    with its number. A pause waits on `clock`, set before the call starts (None: the
    system's)."""

    name: str = "scripted"
    data_flow: DataFlow = FAKE_DATA_FLOW

    def __init__(self, script: Sequence[Sequence[ScriptStep]]) -> None:
        self.script = tuple(tuple(entry) for entry in script)
        for number, entry in enumerate(self.script, 1):
            _checked(entry, f"entry {number} of the script")
        self.requests: list[ChatRequest] = []
        self.clock: Clock | None = None
        self._ids = itertools.count(1)

    @staticmethod
    def reply(text: str, *, usage: Usage | None = None) -> tuple[ChatEvent, ...]:
        """An entry that answers with `text`, in the pieces a model's stream gives (a word each,
        with the space before it), then its `usage` if given, then ends (`Done` of `stop`)."""
        pieces = [TextDelta(text=piece) for piece in _PIECE.findall(text)]
        return (*pieces, *_reported(usage), Done(finish_reason="stop"))

    @staticmethod
    def call_tool(name: str, **arguments: JsonValue) -> tuple[ChatEvent, ...]:
        """An entry that calls the tool `name` with `arguments`, written as the model writes
        them (JSON text), then ends (`Done` of `tool_calls`)."""
        return ScriptedLLM.call_tools((name, arguments))

    @staticmethod
    def call_tools(
        *calls: tuple[str, Mapping[str, JsonValue]], usage: Usage | None = None
    ) -> tuple[ChatEvent, ...]:
        """An entry that calls each tool of `calls` (a name and its arguments) in one request,
        then reports its `usage` if given, then ends (`Done` of `tool_calls`)."""
        asked = [
            ToolCallRequest(
                id=AUTO_ID, name=name, arguments=json.dumps(dict(arguments), ensure_ascii=False)
            )
            for name, arguments in calls
        ]
        return (*asked, *_reported(usage), Done(finish_reason="tool_calls"))

    def stream(self, request: ChatRequest) -> AsyncIterator[ChatEvent]:
        """The next entry's events, `request` kept; fails clearly when the script has run
        out (`ScriptExhaustedError`, from the stream)."""
        self.requests.append(request)
        number = len(self.requests)
        over = _exhausted(len(self.script), self.requests) if number > len(self.script) else None
        return self._entry(number, over)

    async def _entry(
        self, number: int, over: ScriptExhaustedError | None
    ) -> AsyncIterator[ChatEvent]:
        if over is not None:
            raise over
        steps = _checked(self.script[number - 1], f"entry {number} of the script")
        async for event in _play(steps, self.clock or SYSTEM_CLOCK, self._ids):
            yield event

    async def aclose(self) -> None:
        """Nothing to close."""


class FunctionLLM:
    """A chat model whose every request `fn` answers with the steps it gives (the module's
    docstring); a `ChatModel`. `fn` runs when the stream starts, so what it raises comes from
    the stream; a pause waits on `clock`, as `ScriptedLLM`'s."""

    name: str = "function"
    data_flow: DataFlow = FAKE_DATA_FLOW

    def __init__(self, fn: Callable[[ChatRequest], Iterable[ScriptStep]]) -> None:
        self.fn = fn
        self.requests: list[ChatRequest] = []
        self.clock: Clock | None = None
        self._ids = itertools.count(1)

    def stream(self, request: ChatRequest) -> AsyncIterator[ChatEvent]:
        """`fn`'s events for `request`, `request` kept, ending with one `Done`."""
        self.requests.append(request)
        return self._answer(request, len(self.requests))

    async def _answer(self, request: ChatRequest, number: int) -> AsyncIterator[ChatEvent]:
        steps = _checked(self.fn(request), f"the answer to request {number}")
        async for event in _play(steps, self.clock or SYSTEM_CLOCK, self._ids):
            yield event

    async def aclose(self) -> None:
        """Nothing to close."""


def _reported(usage: Usage | None) -> tuple[Usage, ...]:
    return (usage,) if usage is not None else ()


def _checked(steps: Iterable[ScriptStep], where: str) -> tuple[ScriptStep, ...]:
    """`steps` as a stream plays them: each a step, nothing after a `Done` or an error, one
    `Usage` at most, and a `Done` added to an answer that has neither (the module's
    docstring). ValueError naming `where` and the step for a wrong one."""
    read: tuple[object, ...] = tuple(steps)  # as a test gave them, whatever their type
    given: list[ScriptStep] = []
    for number, step in enumerate(read, 1):
        if isinstance(step, int | float) and not isinstance(step, bool):
            given.append(_pause(step, f"{where}: step {number}, a pause,"))
            continue
        if not isinstance(step, TextDelta | ToolCallRequest | Usage | Done | ProviderError):
            kind = type(step).__name__
            raise ValueError(f"{where}: step {number} is a {kind}, not an event, pause or error")
        if isinstance(step, Done | ProviderError) and number < len(read):
            raise ValueError(f"{where}: step {number} ends the stream, but steps follow it")
        given.append(step)
    if sum(isinstance(step, Usage) for step in given) > 1:
        raise ValueError(f"{where}: a stream reports its usage once")
    if given and isinstance(given[-1], Done | ProviderError):
        return tuple(given)
    called = any(isinstance(step, ToolCallRequest) for step in given)
    return (*given, Done(finish_reason="tool_calls" if called else "stop"))


async def _play(
    steps: Iterable[ScriptStep], clock: Clock, ids: Iterator[int]
) -> AsyncIterator[ChatEvent]:
    """Each step in turn: a pause waited on `clock`, an error raised, an event yielded after a
    turn of the loop, as a stream's chunks come, a call's `AUTO_ID` replaced by the next id."""
    for step in steps:
        if isinstance(step, float):
            await clock.sleep(step)
            continue
        if isinstance(step, ProviderError):
            raise step
        await asyncio.sleep(0)
        if isinstance(step, ToolCallRequest) and step.id == AUTO_ID:
            step = step.model_copy(update={"id": f"call_{next(ids)}"})
        yield step


def _pause(seconds: float, what: str) -> float:
    """`seconds` as a pause's length; ValueError saying `what` for one that is not finite, or
    under 0."""
    if not (math.isfinite(seconds) and seconds >= 0):
        raise ValueError(f"{what} lasts a finite number of seconds, 0 or more")
    return float(seconds)


def _exhausted(entries: int, requests: Sequence[ChatRequest]) -> ScriptExhaustedError:
    """The failure of a request past the script's last entry, with the requests so far."""
    lines = [
        f"  {number}. last user text {_last_user(request)!r}, ending with a "
        f"{request.messages[-1].role} message, tools {[tool.name for tool in request.tools]}"
        for number, request in enumerate(requests, 1)
    ]
    return ScriptExhaustedError(
        f"ScriptedLLM's script has {entries} entries, and request {len(requests)} came after "
        "its last. The requests so far:\n" + "\n".join(lines)
    )


def _last_user(request: ChatRequest) -> str | None:
    said = [message.content for message in request.messages if message.role == "user"]
    return said[-1] if said else None

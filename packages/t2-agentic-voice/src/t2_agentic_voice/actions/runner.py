"""The tool runner (the design's 6.4; ARCHITECTURE.md, "What must not know about each other"):
what the api layer injects into the talker beside the chat model, so the talker acts only
through a tool call. It holds an agent's tools, tells the talker their schemas, and runs one
call: the model's argument text parsed into the tool's parameters before the function runs (an
invalid one answered with its field named, invariant 4), the bound parameters filled from the
call's caller, the function run, a sync one in a worker thread, within its `timeout_s` on the
call's clock (core/clock.py: a test's virtual clock times a tool out only when it is moved on,
never on asyncio's own time), and its return made a `ToolResult`; a `ToolError` answered with
its message, any other failure or the timeout with a generic one, logged at ERROR by its type
and its frames alone, never its text or an argument (actions/tools.py). The runner holds no
call's state, so one serves every call of an agent; each call's clock comes with each run, as
its context does.

What the talker reads of a failed call is the result's `data`, `{"error": "..."}`, with `ok`
False: a tool it does not have, arguments that are not a JSON object of the tool's parameters
(each field at fault named, its value never repeated), a bound value the caller does not hold
(logged, as a team's mistake), the tool's own `ToolError`, and "the tool failed" for anything
else. A sync tool cancelled or timed out goes on in its thread, its result discarded (the
design's 6.4; a thread cannot be stopped).
"""

from __future__ import annotations

import asyncio
import json
import traceback
from collections.abc import Callable, Coroutine, Sequence
from pathlib import PurePath
from typing import Any

from pydantic import BaseModel, TypeAdapter, ValidationError

from t2_agentic_voice.actions.signature import context_parameter, is_async
from t2_agentic_voice.actions.tools import CallContext, Tool, ToolResult
from t2_agentic_voice.core.clock import Clock
from t2_agentic_voice.core.errors import ConfigurationError, ProviderError, ToolError
from t2_agentic_voice.core.logging import get_logger
from t2_agentic_voice.domain.ports.chat_model import ToolCallRequest, ToolSchema
from t2_agentic_voice.domain.talker_declaration import DeclaredTool

_log = get_logger(__name__)
# A tool's return as JSON: a model, a dataclass, a date and the like as their JSON values.
_JSON: TypeAdapter[Any] = TypeAdapter(Any)
# What the talker is told of a call that failed in a way the caller may not hear of.
FAILED = "the tool failed"
# The most argument errors told the talker at once, and the most frames of a failure logged.
_ERRORS_TOLD = 5
_FRAMES_LOGGED = 8
_TOOLS_FIX = (
    "FIX: build each tool with @tool, Tool.from_function or knowledge_tool, each with its own name."
)


def failed_result(message: str, failure: str) -> ToolResult:
    """A call that failed, `message` the talker reads, `failure` what its trace names."""
    return ToolResult(data={"error": message}, ok=False, failure=failure)


def _failure_of(error: BaseException) -> str:
    """What a raised `error` was, for the trace: a provider's by its kind and, when its details
    name one, its step; any other by its type; never its text or an argument."""
    if not isinstance(error, ProviderError):
        return type(error).__qualname__
    step = error.details.get("step")
    return f"{error.kind} at {step}" if isinstance(step, str) else error.kind


def frames_of(error: BaseException) -> str:
    """Where `error` was raised, as file, line and function, innermost last; no source line,
    local or message, which could hold an argument."""
    frames = traceback.extract_tb(error.__traceback__)[-_FRAMES_LOGGED:]
    return " > ".join(f"{PurePath(f.filename).name}:{f.lineno}:{f.name}" for f in frames)


class ToolRunner:
    """One agent's `tools`, run for the talker; each name once. It takes the agent's declared
    tools as they are (`ToolRunner(agent.tools)`): ConfigurationError, with a FIX line, for one
    that is not a `Tool` (`VoiceAgent.tools` takes anything with a tool's shape,
    `DeclaredTool`) or a name given twice."""

    def __init__(self, tools: Sequence[DeclaredTool]) -> None:
        checked: list[Tool] = []
        for each in tools:
            if not isinstance(each, Tool):
                raise ConfigurationError(
                    f"The agent's tools hold one the talker cannot run: it is not a Tool. "
                    f"{_TOOLS_FIX}",
                    details={"field": "tools"},
                )
            checked.append(each)
        self.tools = tuple(checked)
        names = [each.name for each in self.tools]
        if len(set(names)) != len(names):
            raise ConfigurationError(
                f"Two of the agent's tools share a name. {_TOOLS_FIX}", details={"field": "tools"}
            )
        self._by_name = {each.name: each for each in self.tools}
        self._schemas = tuple(each.tool_schema() for each in self.tools)
        self._contexts = {
            each.name: context_parameter(each.function, context=CallContext) for each in self.tools
        }
        self._async = {each.name: is_async(each.function) for each in self.tools}

    def schemas(self) -> tuple[ToolSchema, ...]:
        """Each tool as the talker is told of it (`Tool.tool_schema`), in order."""
        return self._schemas

    def tool(self, name: str) -> Tool | None:
        """The tool named `name`, None for a name the agent has none of."""
        return self._by_name.get(name)

    async def run(self, request: ToolCallRequest, ctx: CallContext, *, clock: Clock) -> ToolResult:
        """Run the call `request` names, in the call `ctx` gives, its timeout timed on the
        call's `clock` (the module's docstring); never raises for the tool's own failure, which
        is the result the talker reads, and stops at once when its task is cancelled."""
        tool = self._by_name.get(request.name)
        if tool is None:
            names = ", ".join(self._by_name) or "none"
            message = f"there is no tool named `{request.name}`; the tools are: {names}"
            return failed_result(message, "no_such_tool")
        arguments = parsed_arguments(tool.parameters, request.arguments)
        if isinstance(arguments, ToolResult):
            return arguments
        kwargs = {name: getattr(arguments, name) for name in type(arguments).model_fields}
        for name, binding in tool.bind.items():
            value = binding.value(ctx.caller)
            if value is None:
                _log.error("tool_bound_value_missing", tool=tool.name, parameter=name)
                return failed_result(FAILED, "bound_value_missing")
            kwargs[name] = value
        context = self._contexts[tool.name]
        if context is not None:
            kwargs[context] = ctx
        call = (
            _awaited(tool.function, kwargs)
            if self._async[tool.name]
            else _threaded(tool.function, kwargs)
        )
        return await _within(tool, call, clock)


def parsed_arguments(parameters: type[BaseModel], text: str) -> BaseModel | ToolResult:
    """The arguments `text` gives, parsed into `parameters`; a failed result naming what is
    wrong, each field at fault by its name, never its value."""
    try:
        raw = json.loads(text) if text.strip() else {}
    except json.JSONDecodeError:
        message = "the arguments are not JSON: give a JSON object of the tool's parameters"
        return failed_result(message, "bad_arguments")
    if not isinstance(raw, dict):
        return failed_result(
            "the arguments are a JSON object of the tool's parameters", "bad_arguments"
        )
    try:
        return parameters.model_validate(raw)
    except ValidationError as error:
        problems = error.errors(include_input=False, include_url=False, include_context=False)
    told = "; ".join(
        f"`{'.'.join(str(part) for part in problem['loc']) or 'arguments'}`: {problem['msg']}"
        for problem in problems[:_ERRORS_TOLD]
    )
    return failed_result(f"invalid arguments: {told}", "bad_arguments")


async def _awaited(function: Callable[..., Any], kwargs: dict[str, Any]) -> Any:
    return await function(**kwargs)


async def _threaded(function: Callable[..., Any], kwargs: dict[str, Any]) -> Any:
    return await asyncio.to_thread(function, **kwargs)


async def _within(tool: Tool, call: Coroutine[Any, Any, Any], clock: Clock) -> ToolResult:
    """`call` run within `tool`'s timeout on `clock`, its outcome made the talker's result."""
    work = asyncio.ensure_future(call)
    timer = asyncio.ensure_future(clock.sleep(tool.timeout_s))
    try:
        await asyncio.wait((work, timer), return_when=asyncio.FIRST_COMPLETED)
    finally:
        timer.cancel()
        if not work.done():
            work.cancel()
    if not work.done() or work.cancelled():
        _log.warning("tool_timed_out", tool=tool.name, timeout_s=tool.timeout_s)
        return failed_result(FAILED, "timed_out")
    error = work.exception()
    if isinstance(error, ToolError):
        return failed_result(error.message, "tool_error")
    if error is not None:
        failure = type(error).__qualname__
        _log.error("tool_failed", tool=tool.name, failure=failure, at=frames_of(error))
        return failed_result(FAILED, _failure_of(error))
    value = work.result()
    if isinstance(value, ToolResult):
        return value
    try:
        return ToolResult(data=_JSON.dump_python(value, mode="json"))
    except (TypeError, ValueError):  # pydantic's serialization error is a ValueError
        _log.error("tool_result_unreadable", tool=tool.name, kind=type(value).__qualname__)
        return failed_result(FAILED, "unreadable_result")

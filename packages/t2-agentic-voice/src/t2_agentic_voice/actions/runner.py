"""The tool runner (the design's 6.4; ARCHITECTURE.md, "What must not know about each other"):
what the api layer injects into the talker beside the chat model, so the talker acts only
through a tool call. It holds an agent's tools, tells the talker their schemas, and runs one
call: the model's argument text parsed into the tool's parameters before the function runs (an
invalid one answered with its field named, invariant 4), the bound parameters filled from the
call's caller, the function run, a sync one in a worker thread, within its `timeout_s`, and its
return made a `ToolResult`; a `ToolError` answered with its message, any other failure or the
timeout with a generic one, logged at ERROR by its type alone (actions/tools.py).

Plan 006's Track B builds it; this module holds its shape.
"""

from __future__ import annotations

from collections.abc import Sequence

from t2_agentic_voice.actions.tools import CallContext, Tool, ToolResult
from t2_agentic_voice.domain.ports.chat_model import ToolCallRequest, ToolSchema


class ToolRunner:
    """One agent's `tools`, run for the talker; each name once."""

    def __init__(self, tools: Sequence[Tool]) -> None:
        self.tools = tuple(tools)

    def schemas(self) -> tuple[ToolSchema, ...]:
        """Each tool as the talker is told of it (`Tool.tool_schema`), in order."""
        raise NotImplementedError("the tool runner is plan 006's Track B")

    async def run(self, request: ToolCallRequest, ctx: CallContext) -> ToolResult:
        """Run the call `request` names, in the call `ctx` gives (the module's docstring);
        never raises for the tool's own failure, which is the result the talker reads, and
        stops at once when its task is cancelled."""
        raise NotImplementedError("the tool runner is plan 006's Track B")

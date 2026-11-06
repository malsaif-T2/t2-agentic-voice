"""The tool calls of one reply (agent/turn.py), and what a call's talker keeps of them between
replies (`Memory`).

- **Run.** Each call the model asked for in a request starts at once, through the runner
  (actions/runner.py, which never raises for the tool's own failure): in the reply's scope, so a
  stop cancels it with the reply, but for a tool whose barge-in is `finish`, which the talker
  holds itself, its result kept for the next turn if the reply ends first.
- **Progress.** While they run, the first progress line due is given once a tool has run past
  its `progress_after_s` on the call's clock: one line a reply, however many tools.
- **Results.** Each result, as it comes: `ToolEnded`, its data and evidence kept as the output
  guard's evidence for the rest of the call, and its card shown once the guard passed its text.
- **Framed.** A result goes back to the model as JSON inside the data frame the prompt names
  (`<data tool="...">`, agent/prompt.py), its `<` escaped, so no text in it can close the frame.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator, Callable, Iterable, Sequence
from dataclasses import dataclass, field

from t2_agentic_voice.actions.runner import ToolRunner
from t2_agentic_voice.actions.tools import CallContext, Tool, ToolResult
from t2_agentic_voice.agent.events import (
    ProgressDue,
    ReplyScope,
    ShownCard,
    TalkerEvent,
    ToolBegan,
    ToolEnded,
)
from t2_agentic_voice.agent.prompt import DATA_TAG
from t2_agentic_voice.core.clock import Clock
from t2_agentic_voice.core.events import TurnId
from t2_agentic_voice.domain.cards import Card
from t2_agentic_voice.domain.ports.chat_model import ChatMessage, ToolCallRequest

# The past turns whose tool calls and results the talker keeps for the model.
KEPT_TURNS = 4
# How close to its progress time a tool counts as past it, for a clock's rounding.
_EPSILON_S = 1e-9


@dataclass
class Memory:
    """What one call's talker keeps between its replies, which the heard history does not
    hold: the tool calls and results of its last `KEPT_TURNS` turns, its developer notes, the
    evidence its tools gave, and the tools left to finish after their reply."""

    exchanges: dict[TurnId, list[ChatMessage]] = field(default_factory=dict)
    notes: dict[TurnId, str] = field(default_factory=dict)
    evidence: list[str] = field(default_factory=list)
    finishing: set[asyncio.Future[ToolResult]] = field(default_factory=set)

    def keep(self, turn_id: TurnId, messages: Sequence[ChatMessage]) -> None:
        """Keep `messages`, the calls and results of the turn `turn_id`."""
        self.exchanges.setdefault(turn_id, []).extend(messages)
        while len(self.exchanges) > KEPT_TURNS:
            del self.exchanges[min(self.exchanges)]

    def took(self, result: ToolResult) -> None:
        """Keep `result`'s data and evidence as the guard's evidence."""
        self.evidence += [json.dumps(result.data, ensure_ascii=False), *result.evidence]


def framed(tool: str, result: ToolResult) -> str:
    """`result`'s data as the model reads it: JSON in the data frame the prompt names."""
    body = json.dumps(result.data, ensure_ascii=False).replace("<", "\\u003c")
    return f'<{DATA_TAG} tool="{tool}">{body}</{DATA_TAG}>'


def exchange(calls: Sequence[ToolCallRequest], results: dict[str, ToolResult]) -> list[ChatMessage]:
    """The model's message asking for `calls`, then each one's result, framed, in order."""
    return [
        ChatMessage.assistant(tool_calls=tuple(calls)),
        *(ChatMessage.tool_result(c.id, framed(c.name, results[c.id])) for c in calls),
    ]


def _finishes(tool: Tool | None) -> bool:
    return tool is not None and tool.on_interrupt == "finish"


class ToolCalls:
    """The tool calls of one reply, request by request (the module's docstring): `shown` says
    whether the output guard passes a card, by its tool's name."""

    def __init__(
        self,
        *,
        runner: ToolRunner,
        ctx: CallContext,
        clock: Clock,
        scope: ReplyScope,
        memory: Memory,
        turn_id: TurnId,
        shown: Callable[[Card, str], bool],
    ) -> None:
        self.runner, self.ctx, self.clock, self.scope = runner, ctx, clock, scope
        self.memory, self.turn_id, self.shown = memory, turn_id, shown
        self.progress_said = False

    async def run(
        self, calls: Sequence[ToolCallRequest], results: dict[str, ToolResult]
    ) -> AsyncGenerator[TalkerEvent, None]:
        """Run `calls`, each result into `results` by the call's id, the events as they come."""
        began = self.clock.now()
        tasks: dict[asyncio.Future[ToolResult], ToolCallRequest] = {}
        finished: set[asyncio.Future[ToolResult]] = set()
        timer: asyncio.Future[None] | None = None
        try:
            for call in calls:
                tasks[self._started(call)] = call
            for call in calls:
                yield ToolBegan(call_id=call.id, tool=call.name)
            timer = self._timer(calls, began)
            while len(finished) < len(tasks):
                pending = set(tasks) - finished
                waiters = pending | ({timer} if timer else set())
                done, _ = await asyncio.wait(waiters, return_when=asyncio.FIRST_COMPLETED)
                if timer is not None and timer in done:
                    waiting = [tasks[task] for task in pending if task not in done]
                    due = self._due(waiting, began)
                    if due is not None and due.progress is not None:
                        self.progress_said = True
                        yield ProgressDue(
                            tool=due.name, key=due.progress, language=self.ctx.language
                        )
                    timer = self._timer(waiting, began)
                for task in [task for task in tasks if task in done]:
                    finished.add(task)
                    call = tasks[task]
                    result = results[call.id] = task.result()
                    self.memory.took(result)
                    ms = max(0.0, self.clock.now() - began) * 1000
                    yield ToolEnded(call_id=call.id, tool=call.name, ok=result.ok, ms=ms)
                    if result.card is not None and self.shown(result.card, call.name):
                        yield ShownCard(card=result.card)
        finally:
            if timer is not None:
                timer.cancel()
            for task, call in tasks.items():
                if task in finished:
                    continue
                if _finishes(self.runner.tool(call.name)):
                    self._keep_when_done(call, task)
                elif not task.done():
                    task.cancel()

    def _started(self, call: ToolCallRequest) -> asyncio.Future[ToolResult]:
        """The call's run, started at once: in the reply's scope, but for a tool whose barge-in
        is `finish`, whose task the talker holds itself."""
        work = self.runner.run(call, self.ctx, clock=self.clock)
        if _finishes(self.runner.tool(call.name)):
            task = asyncio.ensure_future(work)
            self.memory.finishing.add(task)
            task.add_done_callback(self.memory.finishing.discard)
            return task
        return self.scope.start(work, name=f"tool-{call.name}")

    def _progressing(self, calls: Iterable[ToolCallRequest]) -> list[Tool]:
        tools = [self.runner.tool(call.name) for call in calls]
        return [tool for tool in tools if tool is not None and tool.progress is not None]

    def _timer(self, calls: Iterable[ToolCallRequest], began: float) -> asyncio.Future[None] | None:
        """A sleep until the next progress line of `calls` is due, None when none is."""
        times = [tool.progress_after_s for tool in self._progressing(calls)]
        if self.progress_said or not times:
            return None
        left = min(times) - (self.clock.now() - began)
        return asyncio.ensure_future(self.clock.sleep(max(0.0, left)))

    def _due(self, calls: Sequence[ToolCallRequest], began: float) -> Tool | None:
        """The first of `calls`' tools now past its progress time."""
        elapsed = self.clock.now() - began + _EPSILON_S
        return next((t for t in self._progressing(calls) if t.progress_after_s <= elapsed), None)

    def _keep_when_done(self, call: ToolCallRequest, task: asyncio.Future[ToolResult]) -> None:
        """A `finish` tool's call outlived its reply: its result is kept for the next turn."""

        def kept(ended: asyncio.Future[ToolResult]) -> None:
            if ended.cancelled() or ended.exception() is not None:
                return
            self.memory.took(ended.result())
            self.memory.keep(self.turn_id, exchange([call], {call.id: ended.result()}))

        if task.done():
            kept(task)
        else:
            task.add_done_callback(kept)

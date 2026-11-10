"""The tool calls of one reply (agent/turn.py), and what a call's talker keeps of them between
replies (`Memory`).

- **Run.** Each call the model asked for in a request starts at once, through the runner
  (actions/runner.py, which never raises for the tool's own failure): in the reply's scope, so a
  stop cancels it with the reply, but for a tool whose barge-in is `finish`, which the talker
  holds itself, its result kept for the next turn if the reply ends first.
- **Progress.** The first call in a reply of a tool with a progress line gives that line
  (`ProgressDue`, with the soonest `progress_after_s` of the request's tools), for the session
  to say if the wait runs long: one line a reply, however many tools.
- **Results.** Each result, as it comes: `ToolEnded`, its data and evidence kept as the output
  guard's evidence for the rest of the call, and its card shown once the guard passed its text.
  A result that succeeded, of a tool whose `reports_on` names actions, is kept as the evidence
  of claims about those actions too (rule A, which takes it only when it holds an ID-shaped
  token: agent/speech_guard.py), and no other tool's result is.
- **Actions** (the design's 6.4). A call of one of the agent's actions goes to the action
  runner's `propose`, in the reply's scope, and writes nothing: its read-back (`plan`, one a
  reply) goes to the session, and the model reads only that it is being read back
  (`READ_BACK`); a refusal goes back to the model as a tool's result does. One action a
  request: a second in the same request is refused unasked (`ONE_AT_A_TIME`). Nothing here
  confirms an action: only the yes rule, over heard words, issues one (invariant 1).
- **Framed.** A result goes back to the model as JSON inside the data frame the prompt names
  (`<data tool="...">`, agent/prompt.py), its `<` escaped, so no text in it can close the frame.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator, Callable, Iterable, Sequence
from dataclasses import dataclass, field

from t2_agentic_voice.actions.action_runner import ActionRunner
from t2_agentic_voice.actions.runner import ToolRunner, failed_result
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
from t2_agentic_voice.domain.action_lines import ReadBackPlan
from t2_agentic_voice.domain.cards import Card
from t2_agentic_voice.domain.ports.chat_model import ChatMessage, ToolCallRequest

# The past turns whose tool calls and results the talker keeps for the model.
KEPT_TURNS = 4
# What the model reads of an action call whose read-back goes to the caller, and of a second
# action call in one request.
READ_BACK = (
    "read back to the caller, who is asked to confirm it; nothing is done unless they say yes, "
    "and the system says how it ended"
)
ONE_AT_A_TIME = "one action at a time: call it again once the caller has answered the first"


@dataclass
class Memory:
    """What one call's talker keeps between its replies, which the heard history does not
    hold: the tool calls and results of its last `KEPT_TURNS` turns, its developer notes, the
    evidence its tools gave, the evidence of claims each action's `reports_on` tools gave
    (`reports`, by the action's name), and the tools left to finish after their reply."""

    exchanges: dict[TurnId, list[ChatMessage]] = field(default_factory=dict)
    notes: dict[TurnId, str] = field(default_factory=dict)
    evidence: list[str] = field(default_factory=list)
    reports: dict[str, list[str]] = field(default_factory=dict)
    finishing: set[asyncio.Future[ToolResult]] = field(default_factory=set)

    def keep(self, turn_id: TurnId, messages: Sequence[ChatMessage]) -> None:
        """Keep `messages`, the calls and results of the turn `turn_id`."""
        self.exchanges.setdefault(turn_id, []).extend(messages)
        while len(self.exchanges) > KEPT_TURNS:
            del self.exchanges[min(self.exchanges)]

    def took(self, result: ToolResult, *, reports_on: Sequence[str] = ()) -> None:
        """Keep `result`'s data and evidence as the guard's evidence, and, when it succeeded,
        as the evidence of claims about each action its tool `reports_on`."""
        texts = [json.dumps(result.data, ensure_ascii=False), *result.evidence]
        self.evidence += texts
        if result.ok:
            for action in reports_on:
                self.reports.setdefault(action, []).extend(texts)


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


async def _given(result: ToolResult) -> ToolResult:
    return result


class ToolCalls:
    """The tool calls of one reply, request by request (the module's docstring): `shown` says
    whether the output guard passes a card, by its tool's name; `actions`, the agent's action
    runner, when it declares any; `plan`, the read-back an action call gave in this reply."""

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
        actions: ActionRunner | None = None,
    ) -> None:
        self.runner, self.ctx, self.clock, self.scope = runner, ctx, clock, scope
        self.memory, self.turn_id, self.shown = memory, turn_id, shown
        self.actions = actions
        self.progress_said = False
        self.plan: ReadBackPlan | None = None

    def is_action(self, name: str) -> bool:
        """Whether `name` is one of the agent's actions."""
        return self.actions is not None and self.actions.action(name) is not None

    async def run(
        self, calls: Sequence[ToolCallRequest], results: dict[str, ToolResult]
    ) -> AsyncGenerator[TalkerEvent, None]:
        """Run `calls`, each result into `results` by the call's id, the events as they come."""
        began = self.clock.now()
        tasks: dict[asyncio.Future[ToolResult], ToolCallRequest] = {}
        finished: set[asyncio.Future[ToolResult]] = set()
        proposed = False
        try:
            for call in calls:
                actions = self.actions
                if actions is None or actions.action(call.name) is None:
                    tasks[self._started(call)] = call
                    continue
                if proposed or self.plan is not None:
                    work = _given(failed_result(ONE_AT_A_TIME, "one_at_a_time"))
                else:
                    work, proposed = self._proposed(actions, call), True
                tasks[self.scope.start(work, name=f"action-{call.name}")] = call
            for call in calls:
                yield ToolBegan(call_id=call.id, tool=call.name, arguments=call.arguments)
            line = self._line(calls)
            if line is not None:
                yield line
            while len(finished) < len(tasks):
                pending = set(tasks) - finished
                done, _ = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
                for task in [task for task in tasks if task in done]:
                    finished.add(task)
                    call = tasks[task]
                    result = results[call.id] = task.result()
                    self.memory.took(result, reports_on=self._reports_on(call.name))
                    ms = max(0.0, self.clock.now() - began) * 1000
                    yield ToolEnded(
                        call_id=call.id,
                        tool=call.name,
                        ok=result.ok,
                        ms=ms,
                        failure=result.failure,
                        result=json.dumps(result.data, ensure_ascii=False),
                    )
                    if result.card is not None and self.shown(result.card, call.name):
                        yield ShownCard(card=result.card)
        finally:
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

    async def _proposed(self, actions: ActionRunner, call: ToolCallRequest) -> ToolResult:
        """The action call proposed to `actions`: its read-back kept as the reply's `plan`,
        the model told only that it is read back; or the runner's refusal, as it is."""
        made = await actions.propose(call, self.ctx, clock=self.clock)
        if isinstance(made, ToolResult):
            return made
        self.plan = made
        return ToolResult(data={"status": READ_BACK})

    def _reports_on(self, name: str) -> tuple[str, ...]:
        """The actions the results of the tool `name` report on; none for any other call."""
        tool = self.runner.tool(name)
        return () if tool is None else tool.reports_on

    def _line(self, calls: Iterable[ToolCallRequest]) -> ProgressDue | None:
        """The reply's progress line, the soonest of `calls`' tools': None once given, or when
        none has one."""
        tools = [self.runner.tool(call.name) for call in calls]
        lined = [
            (t.progress_after_s, t.name, t.progress)
            for t in tools
            if t is not None and t.progress is not None
        ]
        if self.progress_said or not lined:
            return None
        self.progress_said = True
        after_s, name, key = min(lined)
        return ProgressDue(tool=name, key=key, language=self.ctx.language, after_s=after_s)

    def _keep_when_done(self, call: ToolCallRequest, task: asyncio.Future[ToolResult]) -> None:
        """A `finish` tool's call outlived its reply: its result is kept for the next turn."""

        def kept(ended: asyncio.Future[ToolResult]) -> None:
            if ended.cancelled() or ended.exception() is not None:
                return
            self.memory.took(ended.result(), reports_on=self._reports_on(call.name))
            self.memory.keep(self.turn_id, exchange([call], {call.id: ended.result()}))

        if task.done():
            kept(task)
        else:
            task.add_done_callback(kept)

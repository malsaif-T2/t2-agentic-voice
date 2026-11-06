"""What a `TextCall` watches of its talker (testing/text_call.py; plan 006), so a turn's reads give
what the talker did (testing/turn_data.py) through nothing but the talker's own port: each
reply's events with when they came (`WatchedTalker`), and each tool call's arguments and result
(`RecordingRunner`, the tool runner the text call's talker is given), the results' evidence
being what the output guard's checks of the call read.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field

from pydantic import JsonValue

from t2_agentic_voice.actions.runner import ToolRunner
from t2_agentic_voice.actions.tools import CallContext, Tool, ToolResult
from t2_agentic_voice.agent.talker import ReplyScope, Talker, TalkerEvent
from t2_agentic_voice.core.clock import Clock
from t2_agentic_voice.core.conversation import TalkerTurn
from t2_agentic_voice.domain.ports.chat_model import ToolCallRequest


@dataclass(kw_only=True)
class TurnTalk:
    """What the talker gave for one turn: when its reply began, each event with when it came,
    and whether the reply's work was cancelled before its stream ended."""

    turn_id: int
    began_at: float
    events: list[tuple[float, TalkerEvent]] = field(default_factory=list)
    cancelled: bool = False


class WatchedTalker:
    """A `Talker` that hands on `inner`'s events unchanged, keeping each turn's last reply in
    `talks`, timed on `clock`."""

    def __init__(self, inner: Talker, clock: Clock) -> None:
        self.inner, self.clock = inner, clock
        self.talks: dict[int, TurnTalk] = {}

    async def reply(self, turn: TalkerTurn, *, scope: ReplyScope) -> AsyncIterator[TalkerEvent]:
        talk = TurnTalk(turn_id=turn.turn_id, began_at=self.clock.now())
        self.talks[turn.turn_id] = talk
        try:
            async for event in self.inner.reply(turn, scope=scope):
                talk.events.append((self.clock.now(), event))
                yield event
        except (asyncio.CancelledError, GeneratorExit):
            talk.cancelled = True
            raise


def arguments_of(request: ToolCallRequest) -> dict[str, JsonValue]:
    """The arguments the model wrote for a tool call, parsed as JSON; empty when they are not a
    JSON object."""
    try:
        parsed = json.loads(request.arguments) if request.arguments else {}
    except ValueError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


class RecordingRunner(ToolRunner):
    """The tool runner, keeping each call it ran by the model's id for it (`calls`): the request
    and, once it returned, its result."""

    def __init__(self, tools: Sequence[Tool]) -> None:
        super().__init__(tools)
        self.calls: dict[str, tuple[ToolCallRequest, ToolResult | None]] = {}

    async def run(self, request: ToolCallRequest, ctx: CallContext, *, clock: Clock) -> ToolResult:
        self.calls[request.id] = (request, None)
        result = await super().run(request, ctx, clock=clock)
        self.calls[request.id] = (request, result)
        return result

    @property
    def evidence(self) -> tuple[str, ...]:
        """Every text the tools' results gave as evidence, in the order they returned."""
        return tuple(
            text
            for _, result in self.calls.values()
            if result is not None
            for text in result.evidence
        )

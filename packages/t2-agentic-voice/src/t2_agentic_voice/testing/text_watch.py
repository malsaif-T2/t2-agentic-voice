"""What a `TextCall` watches of its talker (testing/text_call.py; plan 006), so a turn's reads give
what the talker did (testing/turn_data.py) through nothing but the talker's own port: each
reply's events with when they came (`WatchedTalker`), and each tool call's arguments and result
(`RecordingRunner`, the tool runner the text call's talker is given), the results' evidence
being what the output guard's checks of the call read; and the agent's tools as the runner runs
them (`tools_of`), and the factory of each call's talker a replayed call uses (`chat_talkers`,
as api/providers.py's `talkers` builds the runtime's).
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field

from pydantic import JsonValue

from t2_agentic_voice.actions.runner import ToolRunner
from t2_agentic_voice.actions.tools import CallContext, Tool, ToolResult
from t2_agentic_voice.agent.talker import (
    ChatTalker,
    ReplyScope,
    Talker,
    TalkerCall,
    TalkerEvent,
)
from t2_agentic_voice.core.clock import Clock
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.conversation import TalkerTurn
from t2_agentic_voice.core.errors import ConfigurationError
from t2_agentic_voice.domain.declaration import VoiceAgent
from t2_agentic_voice.domain.ports.chat_model import ChatModel, ToolCallRequest
from t2_agentic_voice.voice.talkers import TalkerFactory


def tools_of(agent: VoiceAgent) -> tuple[Tool, ...]:
    """The agent's tools, each the library's `Tool` the runner runs; ConfigurationError for any
    other."""
    tools = tuple(tool for tool in agent.tools if isinstance(tool, Tool))
    if len(tools) != len(agent.tools):
        raise ConfigurationError(
            "A tool the agent declares is not one the library runs. FIX: build each with @tool, "
            "Tool.from_function or knowledge_tool."
        )
    return tools


def chat_talkers(
    agent: VoiceAgent, settings: VoiceSettings, chat: ChatModel | None
) -> TalkerFactory | None:
    """The factory of each call's talker: the library's `ChatTalker` on `chat`, with one tool
    runner of the agent's tools; None for an agent whose calls run the echo, or with no chat
    model (voice's entry point then refuses an agent that runs the talker)."""
    mode = settings.session.mode_for(instructed=agent.instructed, prefix=settings.prefix)
    if mode != "talker" or chat is None:
        return None
    runner, model = ToolRunner(tools_of(agent)), chat

    def build(call: TalkerCall, clock: Clock) -> Talker:
        return ChatTalker(
            agent, model=model, runner=runner, settings=settings, call=call, clock=clock
        )

    return build


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
    `talks`, timed on `clock`, and the first AssertionError a reply raised (`failure`: a fake
    model's script that ran out), which the session would tell as its `error` notice; `inner`'s
    stream is closed in the reply's own task, even when it is cancelled."""

    def __init__(self, inner: Talker, clock: Clock) -> None:
        self.inner, self.clock = inner, clock
        self.talks: dict[int, TurnTalk] = {}
        self.failure: AssertionError | None = None

    async def reply(self, turn: TalkerTurn, *, scope: ReplyScope) -> AsyncIterator[TalkerEvent]:
        talk = TurnTalk(turn_id=turn.turn_id, began_at=self.clock.now())
        self.talks[turn.turn_id] = talk
        stream = self.inner.reply(turn, scope=scope)
        try:
            async for event in stream:
                talk.events.append((self.clock.now(), event))
                yield event
        except (asyncio.CancelledError, GeneratorExit):
            talk.cancelled = True
            raise
        except AssertionError as error:  # the test's own failure, never the agent's
            self.failure = self.failure or error
            raise
        finally:
            close = getattr(stream, "aclose", None)  # an async generator's, as a talker's is
            if close is not None:
                await close()


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

"""What a `TextCall` watches of its talker (testing/text_call.py; plans 006 and 007), so a turn's
reads give what the talker did (testing/turn_data.py) through nothing but the talker's own port:
each reply's events with when they came (`WatchedTalker`), the read-backs among them
(`plans_of`), and each tool call's arguments and result (`RecordingRunner`, the tool runner the
text call's talker is given), the results' evidence being what the output guard's checks of the
call read; each confirmed action the session hands the part that acts, and how it ended
(`RecordingJobs`, the `ActionJobs` the text call's session is given).
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field
from typing import Any

from pydantic import JsonValue

from t2_agentic_voice.actions.runner import ToolRunner
from t2_agentic_voice.actions.tools import CallContext, Tool, ToolResult
from t2_agentic_voice.agent.events import ReadBackRequested
from t2_agentic_voice.agent.talker import (
    ReplyScope,
    Talker,
    TalkerEvent,
)
from t2_agentic_voice.core.clock import Clock
from t2_agentic_voice.core.conversation import ConversationLine, TalkerTurn
from t2_agentic_voice.core.events import CallId, TurnId
from t2_agentic_voice.core.identity import Caller
from t2_agentic_voice.core.settings.tts import LanguageTag
from t2_agentic_voice.domain.action_lines import ReadBackPlan
from t2_agentic_voice.domain.ports.action_jobs import ActionJobs, ActionOutcome
from t2_agentic_voice.domain.ports.chat_model import ToolCallRequest
from t2_agentic_voice.domain.yes_rule import ConfirmedAction


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


def plans_of(watched: WatchedTalker | None) -> tuple[ReadBackPlan, ...]:
    """Every read-back the talker asked for in the call, in the order it asked."""
    talks = [] if watched is None else sorted(watched.talks.values(), key=lambda t: t.began_at)
    return tuple(e.plan for t in talks for _, e in t.events if isinstance(e, ReadBackRequested))


def arguments_of(written: str) -> dict[str, JsonValue]:
    """The arguments the model wrote for a tool or an action call (`written`, its JSON text),
    parsed; empty when they are not a JSON object."""
    try:
        parsed = json.loads(written) if written else {}
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
        """Every text the tools' results gave as evidence, in the order they returned: each
        one's data as JSON, then its evidence texts, as the talker keeps them for the output
        guard (agent/tool_calls.py's `Memory.took`)."""
        return tuple(
            text
            for _, result in self.calls.values()
            if result is not None
            for text in result.texts()
        )


@dataclass(kw_only=True)
class JobRun:
    """One confirmed action the session handed the part that acts: as the yes rule issued it,
    the rest of what the session gave with it (`given`), when it began on the call's clock, and
    how it ended (`outcome`, None while it runs, or when it raised)."""

    confirmed: ConfirmedAction
    given: dict[str, Any]
    began_at: float
    outcome: ActionOutcome | None = None


class RecordingJobs:
    """The part that acts (`ActionJobs`), handing each job on to `inner` unchanged and keeping
    each, in the order they began (`runs`)."""

    def __init__(self, inner: ActionJobs) -> None:
        self.inner = inner
        self.runs: list[JobRun] = []

    async def run(
        self,
        confirmed: ConfirmedAction,
        *,
        caller: Caller,
        call_id: CallId,
        language: LanguageTag,
        turn_id: TurnId,
        conversation: tuple[ConversationLine, ...],
        clock: Clock,
        wording: LanguageTag | None = None,
    ) -> ActionOutcome:
        given: dict[str, Any] = {
            "caller": caller,
            "call_id": call_id,
            "language": language,
            "wording": wording,
            "turn_id": turn_id,
            "conversation": conversation,
            "clock": clock,
        }
        job = JobRun(confirmed=confirmed, given=given, began_at=clock.now())
        self.runs.append(job)
        job.outcome = await self.inner.run(confirmed, **given)
        return job.outcome

    async def again(self, job: JobRun) -> ActionOutcome:
        """`job`'s confirmed action handed on once more, with all it was given: the same
        request arriving twice (the design's 9.3)."""
        return await self.run(job.confirmed, **job.given)

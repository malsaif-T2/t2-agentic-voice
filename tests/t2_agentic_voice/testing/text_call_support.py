"""What the tests of `TextCall` share (testing/text_call.py; plan 006, Track C): a scripted
talker of the tests' own, since Track B's `ChatTalker` is built in parallel, given to the call
through the private method that builds its talker (`_talker`), and an instructed agent.

`ScriptTalker` gives each turn the steps its `script` gives that turn: a talker event, `Work`
(a wait of so many seconds on the call's clock, in the reply's scope, as a search would take),
`Ran` (a tool call the runner ran, kept in the call's recording runner as the library's
runner would keep it, with its arguments and its result), or `Asked` (a read-back the talker
asked for, kept among the reply's events in the call's watched talker, where the text call
finds its plans, but never handed to the session, so the session plays only the clauses the
script says, whether or not it reads a read-back back itself)."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from t2_agentic_voice.actions.tools import ToolResult
from t2_agentic_voice.agent.events import ReadBackRequested
from t2_agentic_voice.agent.talker import (
    ModelReplied,
    ModelRequested,
    ReplyDone,
    ReplyScope,
    SpokenClause,
    Talker,
    TalkerCall,
    TalkerEvent,
)
from t2_agentic_voice.core.clock import Clock
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.conversation import TalkerTurn
from t2_agentic_voice.core.settings.tts import LanguageTag
from t2_agentic_voice.domain.action_lines import ReadBackPlan
from t2_agentic_voice.domain.declaration import Language, VoiceAgent
from t2_agentic_voice.domain.ports.chat_model import ToolCallRequest, Usage
from t2_agentic_voice.domain.ports.speech_to_text import DataFlow
from t2_agentic_voice.testing.text_call import TextCall

MODEL = "openai/gpt-oss-120b"
AGENT = VoiceAgent(
    name="text-test",
    languages=[
        Language.english(greeting="Hello.", progress={"looking": "One moment."}),
        Language.saudi_arabic(greeting="هلا.", progress={"looking": "لحظة."}),
    ],
    instructions="Answer briefly.",
)


@dataclass(frozen=True)
class Work:
    seconds: float


@dataclass(frozen=True)
class Ran:
    request: ToolCallRequest
    result: ToolResult


@dataclass(frozen=True)
class Asked:
    plan: ReadBackPlan


Step = TalkerEvent | Work | Ran | Asked


def answer(*clauses: str, language: LanguageTag = "en") -> list[Step]:
    return [
        ModelRequested(model=MODEL),
        ModelReplied(
            model=MODEL, usage=Usage(input_tokens=100, output_tokens=20), first_token_s=0.2
        ),
        *(SpokenClause(text=text, language=language) for text in clauses),
        ReplyDone(),
    ]


class NoModel:
    """A chat model the scripted talker never asks (the call's `llm`)."""

    name = "none"
    data_flow = DataFlow(
        provider="none", processed_in="the test", stored_in="nowhere", retention="none"
    )

    def stream(self, request: object) -> AsyncIterator[Any]:
        raise AssertionError("the scripted talker asks no model")

    async def aclose(self) -> None:
        return None


@dataclass
class ScriptTalker:
    """A talker of the tests' (the module's docstring)."""

    clock: Clock
    call: TextCall
    script: Callable[[TalkerTurn], Sequence[Step]]
    turns: list[TalkerTurn] = field(default_factory=list)

    async def reply(self, turn: TalkerTurn, *, scope: ReplyScope) -> AsyncIterator[TalkerEvent]:
        self.turns.append(turn)
        for step in self.script(turn):
            if isinstance(step, Work):
                await scope.start(self.clock.sleep(step.seconds), name="search")
            elif isinstance(step, Ran):
                runner = self.call._runner
                assert runner is not None
                runner.calls[step.request.id] = (step.request, step.result)
            elif isinstance(step, Asked):
                watched = self.call._watched
                assert watched is not None
                asked = ReadBackRequested(plan=step.plan)
                watched.talks[turn.turn_id].events.append((self.clock.now(), asked))
            else:
                yield step
        await asyncio.sleep(0)


class ScriptedCall(TextCall):
    """A text call whose talker is a `ScriptTalker` of `script`."""

    def __init__(
        self,
        script: Callable[[TalkerTurn], Sequence[Step]],
        *,
        agent: VoiceAgent = AGENT,
        **given: Any,
    ) -> None:
        super().__init__(agent, llm=NoModel(), **given)
        self.script = script
        self.talker: ScriptTalker | None = None

    def _talker(self, call: TalkerCall, settings: VoiceSettings, clock: Clock) -> Talker:
        self.talker = ScriptTalker(clock, self, self.script)
        return self.talker

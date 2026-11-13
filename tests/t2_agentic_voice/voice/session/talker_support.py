"""What the tests of the session's talker share: a fake talker of the tests' own, so these tests
pin the session's side alone (agent/'s `ChatTalker` has tests of its own), and a call of an
instructed agent whose session runs it.

`FakeTalker` gives each turn the events its `script` gives that turn (agent/talker.py's
`TalkerEvent`s), and runs a `Work(seconds)` of the script as a task of the reply's scope that
sleeps that long on the call's clock, as a tool or a model request would, the stream waiting on
it. It keeps each turn it was handed, how many commands the session had given when it began
(`began_after`), each turn whose reply it was cancelled in (`cancelled`), and, by turn, the
name of the task its stream was closed in (`closed_in`): the reply's own, or the event loop's
finalizer when nobody closed it. A `Fail(error)` of the script raises `error` from the stream
where it stands, as a model's failure mid-reply."""

from __future__ import annotations

import asyncio
import dataclasses
from collections.abc import AsyncIterator, Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from t2_agentic_voice.agent.talker import (
    ModelReplied,
    ModelRequested,
    ReplyDone,
    ReplyScope,
    SpokenClause,
    TalkerEvent,
)
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.conversation import TalkerTurn
from t2_agentic_voice.core.settings.tts import LanguageTag
from t2_agentic_voice.domain.declaration import Language, VoiceAgent
from t2_agentic_voice.domain.ports.chat_model import Usage
from t2_agentic_voice.voice.session.call import CallSession

from tests.t2_agentic_voice.fakes import FakeClock, FakePhrases
from tests.t2_agentic_voice.session_fakes import FakeSessionIO
from tests.t2_agentic_voice.voice.session.session_support import turn

MODEL = "openai/gpt-oss-120b"
# The tool's progress line, by its key, in each language the agent speaks.
PROGRESS = {"en": "One moment while I look that up.", "ar-SA": "لحظة أدور لك"}
AGENT = VoiceAgent(
    name="talker-test",
    languages=[
        Language.english(greeting="Welcome to the test line", progress={"looking": PROGRESS["en"]}),
        Language.saudi_arabic(
            greeting="أهلا بك في خط التجربة", progress={"looking": PROGRESS["ar-SA"]}
        ),
    ],
    instructions="Answer briefly.",
)


@dataclass(frozen=True)
class Work:
    """A step of a fake reply that takes `seconds` on the call's clock, in the reply's scope."""

    seconds: float


@dataclass(frozen=True)
class Fail:
    """A step of a fake reply that raises `error` from the stream where it stands."""

    error: Exception


Step = TalkerEvent | Work | Fail
Script = Callable[[TalkerTurn], Sequence[Step]]


def answer(*clauses: str, language: LanguageTag = "en") -> list[Step]:
    """A reply of one model request that says `clauses`, then ends."""
    return [
        ModelRequested(model=MODEL),
        ModelReplied(
            model=MODEL, usage=Usage(input_tokens=120, output_tokens=30), first_token_s=0.3
        ),
        *(SpokenClause(text=text, language=language) for text in clauses),
        ReplyDone(),
    ]


@dataclass
class FakeTalker:
    """A talker of the tests' (the module's docstring), on `clock`; `commands`, when given, is
    the session's, read as each reply begins."""

    clock: FakeClock
    script: Script = lambda turn: answer("Made-up answer.")
    commands: list[Any] | None = None
    turns: list[TalkerTurn] = field(default_factory=list)
    began_after: list[int] = field(default_factory=list)
    cancelled: list[int] = field(default_factory=list)
    closed_in: dict[int, str] = field(default_factory=dict)

    async def reply(self, turn: TalkerTurn, *, scope: ReplyScope) -> AsyncIterator[TalkerEvent]:
        self.turns.append(turn)
        if self.commands is not None:
            self.began_after.append(len(self.commands))
        try:
            for step in self.script(turn):
                if isinstance(step, Work):
                    await scope.start(self.clock.sleep(step.seconds), name="fake-work")
                elif isinstance(step, Fail):
                    raise step.error
                else:
                    yield step
        except asyncio.CancelledError:
            self.cancelled.append(turn.turn_id)
            raise
        finally:
            task = asyncio.current_task()
            self.closed_in[turn.turn_id] = "" if task is None else task.get_name()


async def settle(turns: int = 200) -> None:
    """Let the talker's task, which runs beside the session's events, play what it can now."""
    for _ in range(turns):
        await asyncio.sleep(0)


async def talked(
    io: FakeSessionIO, turn_id: int, text: str | None, *, language: str = "en"
) -> None:
    """The caller's turn, said while the agent is silent, heard, and what the talker gives at
    once played (session_support.py's `turn`, then `settle`)."""
    await turn(io, turn_id, text, language=language)
    await settle()


def phrases(agent: VoiceAgent = AGENT) -> FakePhrases:
    """The phrase audio of `agent`'s calls: its fixed phrases and its progress lines."""
    found = FakePhrases.of(agent)
    lines = {(text, each.tag) for each in agent.languages for text in each.progress.values()}
    found.declared |= lines
    return found


def talker_call(
    settings: VoiceSettings, script: Script | None = None, **given: Any
) -> tuple[FakeSessionIO, CallSession, FakeTalker]:
    """A session of `AGENT` (unless another is given) whose talker is a `FakeTalker` of
    `script`, on the fake session I/O built with `given` (`overlap_model`, the chat model of
    an uncertain overlap, and `action_jobs`, what carries out a confirmed action, none unless
    given)."""
    agent = given.pop("agent", AGENT)
    overlap_model = given.pop("overlap_model", None)
    tracing = given.pop("tracing", None)
    jobs = given.pop("action_jobs", None)
    io = FakeSessionIO(settings, agent=agent, phrases=given.pop("phrases", phrases(agent)), **given)
    talker = FakeTalker(io.clock, commands=io.commands.commands)
    if script is not None:
        talker.script = script
    setup = dataclasses.replace(
        io.setup,
        talker=talker,
        overlap_model=overlap_model,
        tracing=tracing or io.setup.tracing,
        action_jobs=jobs,
    )
    io.setup = setup
    session = CallSession(setup, io.commands)
    io.attach(session)
    return io, session, talker


def ended(session: CallSession, reply_id: int) -> bool:
    """Whether the session's reply `reply_id`, asked for, has ended."""
    reply = session._playback.reply(reply_id)
    assert reply is not None, reply_id
    return reply.ended_at is not None

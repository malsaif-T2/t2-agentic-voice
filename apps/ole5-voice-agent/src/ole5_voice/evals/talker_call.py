"""The seam between runs K and S and the library's `TextCall` (the `evals` facade; the design's
9.2): `ask` runs one variant through a call, `play` one scenario, and `heard` reads what each turn
did into a `HeardTurn`, through the facade's turn data only. Every call is held on the system
clock (`clock="system"`), so its times are real ones: the registration's K times the first clause
on the wall clock. `TextCall` is the default call; a test passes a fake with its signature, so
the integration's wiring is this one module.

On the system clock, `TextCall.user` returns once the turn's reply is written whole, before it has
played, and a turn's reads are live. So a call goes on (`advance`) until its last turn is no
longer pending, and only then are its turns and the guard's violations read, the caller having
heard its replies. A variant's reply plays at `CHARS_PER_SECOND_K`, so it never waits out its
speech on the wall clock; a scenario's at `TextCall`'s own pace, so words can be said over it. The
turn before one said `at="tool_running"` is said as a task, since its `user` returns only once
its search has ended: the next is said while it is still being answered. A moment `TextCall`
waits for in vain (its AssertionError: no reply played, no tool ran, the agent never silent), and
a last reply still playing after `limit_s` on the wall clock, are each a TimeoutError, which a run
counts as a `stuck` variant or play.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from types import TracebackType
from typing import Final, Literal, Protocol, Self

from t2_agentic_voice import Card, VoiceAgent, VoiceSettings
from t2_agentic_voice.evals import BlockedClause, HeardClause, TextCall, TextToolCall
from t2_agentic_voice.ports import ChatModel, Usage

from ole5_voice.evals.scenarios import ScriptTurn
from ole5_voice.evals.talker_data import CardShown, Clause, HeardTurn, Tag, ToolUse

# The pace a variant's reply plays at, in characters a second: fast, since run K reads what the
# reply said, and times its first clause, never its speech.
CHARS_PER_SECOND_K: Final = 1000.0
# The most a run waits on the wall clock for a call's last reply to end (`--variant-timeout-s`'s
# default), and the step it moves the call on by while it waits.
LIMIT_S: Final = 180.0
STEP_S: Final = 0.1


class Turn(Protocol):
    """What a run reads of one of a call's turns (`TextTurn`'s data)."""

    @property
    def fate(self) -> str: ...
    @property
    def clauses(self) -> tuple[HeardClause, ...]: ...
    @property
    def tool_calls(self) -> tuple[TextToolCall, ...]: ...
    @property
    def cards(self) -> tuple[Card, ...]: ...
    @property
    def blocked(self) -> tuple[BlockedClause, ...]: ...
    @property
    def first_token_s(self) -> float | None: ...
    @property
    def first_clause_s(self) -> float | None: ...
    @property
    def model_requests(self) -> int: ...
    @property
    def usage(self) -> Usage: ...


class Call(Protocol):
    """A call held in text, as a run drives it (`TextCall`'s)."""

    async def __aenter__(self) -> Self: ...

    async def __aexit__(
        self,
        kind: type[BaseException] | None,
        error: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    async def user(
        self,
        text: str,
        *,
        during: Literal["agent_speaking"] | None = None,
        at: Literal["tool_running"] | None = None,
    ) -> Turn: ...

    async def advance(self, seconds: float) -> None: ...

    @property
    def violations(self) -> tuple[str, ...]: ...


# Builds a call as `TextCall(agent, llm=..., settings=..., language=..., clock="system")`, a
# variant's with `chars_per_second=CHARS_PER_SECOND_K` too.
CallFactory = Callable[..., Call]


@dataclass(frozen=True)
class Held:
    """What a call did: each of its turns, in order, read once its last reply ended, and how
    many violations the output guard's checks found in what the caller heard."""

    turns: tuple[HeardTurn, ...]
    violations: int


def heard(turn: Turn) -> HeardTurn:
    """`turn`'s data as a run keeps it."""
    return HeardTurn(
        fate=turn.fate,
        clauses=tuple(
            Clause(
                text=c.text,
                language=c.language,
                fate=c.fate,
                played_fraction=c.played_fraction,
                phrase=c.phrase,
            )
            for c in turn.clauses
        ),
        tools=tuple(
            ToolUse(tool=t.tool, arguments=dict(t.arguments), outcome=t.outcome, ms=t.ms)
            for t in turn.tool_calls
        ),
        cards=tuple(CardShown(title=c.title, steps=c.steps, source=c.source) for c in turn.cards),
        blocked=len(turn.blocked),
        first_token_s=turn.first_token_s,
        first_clause_s=turn.first_clause_s,
        model_requests=turn.model_requests,
        input_tokens=turn.usage.input_tokens,
        output_tokens=turn.usage.output_tokens,
    )


async def ask(
    agent: VoiceAgent,
    llm: ChatModel,
    settings: VoiceSettings,
    *,
    words: str,
    language: Tag,
    call: CallFactory = TextCall,
    limit_s: float = LIMIT_S,
) -> Held:
    """One variant: a call of `agent` on `llm` in `language`, in which the caller says
    `words` once, read once its reply has played (the module's docstring)."""
    async with call(
        agent,
        llm=llm,
        settings=settings,
        language=language,
        clock="system",
        chars_per_second=CHARS_PER_SECOND_K,
    ) as held:
        try:
            turn = await held.user(words)
        except AssertionError as error:
            raise _never_came(error) from error
        await _played(held, turn, limit_s)
        return Held((heard(turn),), len(held.violations))


async def play(
    agent: VoiceAgent,
    llm: ChatModel,
    settings: VoiceSettings,
    *,
    turns: Sequence[ScriptTurn],
    language: Tag,
    call: CallFactory = TextCall,
    limit_s: float = LIMIT_S,
) -> Held:
    """One scenario: a call of `agent` on `llm` in `language`, each of `turns` said when it
    says, after the call goes on its `after_s`; every turn read once the last reply has played
    (the module's docstring)."""
    async with call(agent, llm=llm, settings=settings, language=language, clock="system") as held:
        said: dict[int, Turn] = {}
        answering: list[tuple[int, asyncio.Task[Turn]]] = []
        try:
            for n, turn in enumerate(turns):
                if turn.after_s:
                    await held.advance(turn.after_s)
                if n + 1 < len(turns) and turns[n + 1].when == "tool_running":
                    answering.append((n, asyncio.create_task(_say(held, turn))))
                    continue
                said[n] = await _say(held, turn)
                for earlier, task in answering:
                    said[earlier] = await task
                answering.clear()
            await _played(held, said[len(turns) - 1], limit_s)
        except AssertionError as error:
            raise _never_came(error) from error
        finally:
            for _, task in answering:
                task.cancel()
            await asyncio.gather(*(task for _, task in answering), return_exceptions=True)
        return Held(tuple(heard(said[n]) for n in range(len(turns))), len(held.violations))


async def _say(held: Call, turn: ScriptTurn) -> Turn:
    if turn.when == "agent_speaking":
        return await held.user(turn.says, during="agent_speaking")
    if turn.when == "tool_running":
        return await held.user(turn.says, at="tool_running")
    return await held.user(turn.says)


async def _played(held: Call, turn: Turn, limit_s: float) -> None:
    """The call moved on until `turn` is no longer pending: its reply played whole or cut, or
    the turn taken otherwise; TimeoutError once `limit_s` has passed on the wall clock."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + limit_s
    while turn.fate == "pending":
        if loop.time() >= deadline:
            raise TimeoutError("the last turn's reply never ended")
        await held.advance(STEP_S)


def _never_came(error: AssertionError) -> TimeoutError:
    """TextCall's wait for a turn's moment, given up on, as a run counts it (stuck)."""
    return TimeoutError(f"the moment a turn waits for never came: {error}")

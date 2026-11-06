"""The seam between runs K and S and the library's `TextCall` (the `evals` facade; the design's
9.2): `ask` runs one variant through a call, `play` one scenario, and `heard` reads what each turn
did into a `HeardTurn`, through the facade's turn data only. Every call is held on the system
clock (`clock="system"`), so its times are real ones: the registration's K times the first clause
on the wall clock. `TextCall` is the default call; a test passes a fake with its signature, so
the integration's wiring is this one module.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from types import TracebackType
from typing import Literal, Protocol, Self

from t2_agentic_voice import Card, VoiceAgent, VoiceSettings
from t2_agentic_voice.evals import BlockedClause, HeardClause, TextCall, TextToolCall
from t2_agentic_voice.ports import ChatModel, Usage

from ole5_voice.evals.scenarios import ScriptTurn
from ole5_voice.evals.talker_data import CardShown, Clause, HeardTurn, Tag, ToolUse


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


# Builds a call as `TextCall(agent, llm=..., settings=..., language=..., clock="system")`.
CallFactory = Callable[..., Call]


@dataclass(frozen=True)
class Held:
    """What a call did: each of its turns, in order, read at its end, and how many violations
    the output guard's checks found in it."""

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
) -> Held:
    """One variant: a call of `agent` on `llm` in `language`, in which the caller says
    `words` once."""
    async with call(agent, llm=llm, settings=settings, language=language, clock="system") as held:
        turn = await held.user(words)
        return Held((heard(turn),), len(held.violations))


async def play(
    agent: VoiceAgent,
    llm: ChatModel,
    settings: VoiceSettings,
    *,
    turns: Sequence[ScriptTurn],
    language: Tag,
    call: CallFactory = TextCall,
) -> Held:
    """One scenario: a call of `agent` on `llm` in `language`, each of `turns` said when it
    says, after the call goes on its `after_s`; every turn read once the last is answered."""
    async with call(agent, llm=llm, settings=settings, language=language, clock="system") as held:
        said = []
        for turn in turns:
            if turn.after_s:
                await held.advance(turn.after_s)
            if turn.when == "agent_speaking":
                said.append(await held.user(turn.says, during="agent_speaking"))
            elif turn.when == "tool_running":
                said.append(await held.user(turn.says, at="tool_running"))
            else:
                said.append(await held.user(turn.says))
        return Held(tuple(heard(turn) for turn in said), len(held.violations))

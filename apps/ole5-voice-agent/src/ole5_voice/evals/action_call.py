"""The seam between run A and the library's `TextCall` (the `evals` facade; the design's 9.2):
`act` plays one scenario as one call, with the call's caller and outbox, and reads what each of
its turns did, through the facade's turn data and expectations only. A test passes a fake call
with its signature, so the wiring is this one module, as talker_call.py is run S's.

**Saying the turns.** Each turn is said when it says, after the call goes on its `after_s`: over
the reply playing (`agent_speaking`), over a read-back's summary (`read_back`) or its closing
question (`closing_question`), while a tool of the reply runs (`tool_running`: the turn before
it said as a task, as run S says it), or once the agent is silent. Before a turn said once the
agent is silent, the call goes on until every write a turn confirmed has ended and its line was
said, so the turn follows the outcome as a caller's would; and after the last turn, until its
reply is no longer pending and every write has ended. A write still running after `limit_s` on
the wall clock is read as it stands (its outcome missing). A last reply still pending then, a
moment `TextCall` waits for in vain, an AssertionError it raises from any step, or the call's
`whole_s` passed leave the call `stuck` (a provider's error, `provider`): what it did is still
read, as it stands, for the turns said before (`Acted.unread`, those still being said), so a
write confirmed on one of them is checked all the same.

**What a turn did** (`TurnFound`), through `TextCall`'s expectations: whether the agent read a
draft back after it, its summary whole so far, or asked again, as it stood when the caller next
spoke (a read-back the next turn cuts was still given); then, once the call has settled and
before it ends, whether that read-back is still whole, the actions the turn's words confirmed,
and how each of their writes ended, its sending line and then its outcome's said
(`action_ended`).
"""

from __future__ import annotations

import asyncio
import dataclasses
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from types import TracebackType
from typing import Any, Final, Literal, Protocol, Self, get_args

from pydantic import Field, JsonValue
from t2_agentic_voice import Caller, ProviderError, VoiceAgent, VoiceSettings
from t2_agentic_voice.evals import TextCall
from t2_agentic_voice.ports import ChatModel, Outbox

from ole5_voice.evals.action_scenarios import ACTIONS, ActionName, ActionTurn
from ole5_voice.evals.models import Model
from ole5_voice.evals.talker_call import LIMIT_S, STEP_S, Turn, heard
from ole5_voice.evals.talker_data import HeardTurn, Tag

During = Literal["agent_speaking", "read_back", "closing_question"]
# Why a call could not go on (the module's docstring).
Stuck = Literal["stuck", "provider"]
OutcomeKind = Literal["done", "failed", "unknown"]
OUTCOME_KINDS: Final[tuple[OutcomeKind, ...]] = get_args(OutcomeKind)


class Expect(Protocol):
    """The checks of what a turn did with an action (`TurnExpectations`'), each raising
    AssertionError when it did not."""

    def read_back(self, *, contains: str | None = None, **values: JsonValue) -> None: ...
    def asked_again(self) -> None: ...
    def confirmed(self, name: str, **values: JsonValue) -> None: ...
    def action_ended(self, name: str, kind: OutcomeKind) -> None: ...


class ActedTurn(Turn, Protocol):
    """What a run reads of one of a call's turns (`TextTurn`'s data), and its checks: among
    them, how many characters the stray-script filter took out of, or rewrote in, what the
    talker wrote (D-084)."""

    @property
    def expect(self) -> Expect: ...
    @property
    def stray_characters(self) -> int: ...


class ActionCall(Protocol):
    """A call held in text, as run A drives it (`TextCall`'s)."""

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
        during: During | None = None,
        at: Literal["tool_running"] | None = None,
    ) -> ActedTurn: ...

    async def advance(self, seconds: float) -> None: ...

    @property
    def violations(self) -> tuple[str, ...]: ...


# Builds a call as `TextCall(agent, llm=..., settings=..., caller=..., language=...,
# outbox=..., clock="system")`.
ActionCallFactory = Callable[..., ActionCall]


class TurnFound(Model):
    """What the call did after one of its turns (the module's docstring): `read_back` and
    `asked_again` as it stood when the caller next spoke (or once the call settled, for the last
    turn); `kept`, whether the draft it read back was still said whole once the call settled."""

    read_back: bool = False
    asked_again: bool = False
    kept: bool = False
    confirmed: tuple[ActionName, ...] = ()
    ended: dict[ActionName, OutcomeKind] = Field(default_factory=dict)


@dataclass(frozen=True)
class Acted:
    """What a call did: each turn as heard and what came after it, in order, the violations
    the call's checks found (`TextCall.violations`), and the characters the stray-script filter
    took out of what the talker wrote in those turns (`stray_characters`); for a call that
    could not go on (`failure`), the turns said before it stopped, and how many more were being
    said then (`unread`)."""

    turns: tuple[HeardTurn, ...]
    found: tuple[TurnFound, ...]
    violations: tuple[str, ...]
    failure: Stuck | None = None
    unread: int = 0
    stray_characters: int = 0


def _holds(check: Callable[..., None], *args: Any) -> bool:
    """Whether `check(*args)`, one of a turn's expectations, holds."""
    try:
        check(*args)
    except AssertionError:
        return False
    return True


def _ended(turn: ActedTurn, name: ActionName) -> OutcomeKind | None:
    """How the write of `name` that `turn` confirmed ended, its lines said; None until then."""
    return next((k for k in OUTCOME_KINDS if _holds(turn.expect.action_ended, name, k)), None)


def _shown(turn: ActedTurn) -> tuple[bool, bool]:
    """Whether the agent read a draft back after `turn`, and whether it asked again, so far."""
    return _holds(turn.expect.read_back), _holds(turn.expect.asked_again)


def found_of(turn: ActedTurn, shown: tuple[bool, bool]) -> TurnFound:
    """What the call did after `turn`, once it settled, with what it had `shown` when the
    caller next spoke."""
    confirmed = tuple(name for name in ACTIONS if _holds(turn.expect.confirmed, name))
    ended = {name: kind for name in confirmed if (kind := _ended(turn, name)) is not None}
    return TurnFound(
        read_back=shown[0],
        asked_again=shown[1],
        kept=_holds(turn.expect.read_back),
        confirmed=confirmed,
        ended=ended,
    )


def _writing(said: Sequence[ActedTurn]) -> bool:
    """Whether a write some turn of `said` confirmed has not ended, its lines said, yet."""
    return any(
        _holds(turn.expect.confirmed, name) and _ended(turn, name) is None
        for turn in said
        for name in ACTIONS
    )


async def _settle(
    held: ActionCall, said: Sequence[ActedTurn], limit_s: float, *, last: bool
) -> None:
    """The call moved on until no write runs (and, for the `last` turn, its reply is no longer
    pending); a pending last reply after `limit_s` is a TimeoutError (the module's
    docstring)."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + limit_s
    while (last and said[-1].fate == "pending") or _writing(said):
        if loop.time() >= deadline:
            if last and said[-1].fate == "pending":
                raise TimeoutError("the last turn's reply never ended")
            return
        await held.advance(STEP_S)


async def _say(held: ActionCall, turn: ActionTurn) -> ActedTurn:
    if turn.when == "tool_running":
        return await held.user(turn.says, at="tool_running")
    return await held.user(turn.says, during=turn.when)


@dataclass
class _Saying:
    """The turns said so far, what the agent had shown after each when the caller next spoke
    (`_shown`), and how many turns began to be said."""

    said: list[ActedTurn] = field(default_factory=list)
    shown: list[tuple[bool, bool]] = field(default_factory=list)
    begun: int = 0

    def acted(self, held: ActionCall, failure: Stuck | None) -> Acted:
        """What the call did after each turn said, read as it stands."""
        self.shown += [_shown(earlier) for earlier in self.said[len(self.shown) :]]
        return Acted(
            turns=tuple(heard(turn) for turn in self.said),
            found=tuple(found_of(t, seen) for t, seen in zip(self.said, self.shown, strict=True)),
            violations=held.violations,
            failure=failure,
            unread=self.begun - len(self.said),
            stray_characters=sum(turn.stray_characters for turn in self.said),
        )


async def _said_all(
    held: ActionCall, turns: Sequence[ActionTurn], limit_s: float, saying: _Saying
) -> None:
    """Each of `turns` said when it says (the module's docstring), in order, kept in `saying`
    as it is, so a call that stops partway keeps the turns said before."""
    said, shown = saying.said, saying.shown
    answering: asyncio.Task[ActedTurn] | None = None
    try:
        for n, turn in enumerate(turns):
            if turn.after_s:
                await held.advance(turn.after_s)
            if turn.when is None:
                await _settle(held, said, limit_s, last=False)
            shown += [_shown(earlier) for earlier in said[len(shown) :]]
            saying.begun = n + 1
            if n + 1 < len(turns) and turns[n + 1].when == "tool_running":
                answering = asyncio.create_task(_say(held, turn))
                continue
            now = await _say(held, turn)
            if answering is not None:
                said.append(await answering)
                answering = None
            said.append(now)
        await _settle(held, said, limit_s, last=True)
    finally:
        if answering is not None:  # the turn before one that stuck, kept when it was said
            answering.cancel()
            (before,) = await asyncio.gather(answering, return_exceptions=True)
            if not isinstance(before, BaseException):
                said.append(before)


async def act(
    agent: VoiceAgent,
    llm: ChatModel,
    settings: VoiceSettings,
    *,
    turns: Sequence[ActionTurn],
    language: Tag,
    caller: Caller,
    outbox: Outbox,
    call: ActionCallFactory = TextCall,
    limit_s: float = LIMIT_S,
    whole_s: float | None = None,
) -> Acted:
    """One scenario: a call of `agent` on `llm` in `language`, for `caller`, its writes kept in
    `outbox`, each of `turns` said when it says, within `whole_s` in all; what each did read
    once the call settled, or as it stood when it could not go on (the module's docstring)."""
    saying = _Saying()
    acted: Acted | None = None
    try:
        async with call(
            agent,
            llm=llm,
            settings=settings,
            caller=caller,
            language=language,
            outbox=outbox,
            clock="system",
        ) as held:
            failure: Stuck | None = None
            try:
                async with asyncio.timeout(whole_s):
                    await _said_all(held, turns, limit_s, saying)
            except (AssertionError, TimeoutError):  # a wait given up on, or the talker's
                failure = "stuck"
            except ProviderError:
                failure = "provider"
            acted = saying.acted(held, failure)
            return acted
    except AssertionError as error:  # the talker's, raised as the call begins or ends
        if acted is None:
            raise TimeoutError(f"the moment a turn waits for never came: {error}") from error
        return dataclasses.replace(acted, failure=acted.failure or "stuck")

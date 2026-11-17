"""The seam between the flight agent's scripted calls and the library's `TextCall` (the `evals`
facade): `play` plays one scenario as one call of the app's own agent (agent.py's `declare`)
over a new mock airline and trip book, the scenario's modes set and its today pinned, for the
demo traveler, and reads what each turn did through the facade's turn data and expectations
only, as plain data the checks read (checks.py). A test passes a fake model, or a fake call
with `TextCall`'s signature, so the wiring is this one module.

**Saying the turns.** Each turn waits its `after_s` first, then is said when it says: over the
reply playing (`agent_speaking`), over a read-back's summary (`read_back`) or its closing
question (`closing_question`), while a tool of the reply runs (`tool_running`: the turn before
it said as a task, since `user` returns only once its reply is written on the system clock), or
once the agent is silent. Before a turn said once the agent is silent, the call goes on until a
booking its words confirmed has ended and its line was said; after the last turn, until its
reply is no longer pending and the booking has ended; a last turn said over a summary, first
until its words confirmed the booking or no reply has played for `HELD_S`, since a yes held
there books only once the summary played whole (D-108). A **stop** (`stop = true`) is the
client's Stop, `after_s` after the moment `at` names began: `TextCall` has no public wait for a
moment without words, so the moment is read as the reply before it being written
(`agent_speaking`, `read_back`, `closing_question`) or its words handed (`tool_running`), and
`after_s` counts from there. A play may say its turns its own way (`say`, handed the turn said
before each: the lean play's, lean_call.py). A write or a last reply still running after
`limit_s` on the wall clock, a moment the call waits for in vain, or the play's whole limit
passed leave the play `stuck` (a provider's error: `provider`); what it did is still read, as it
stands, for the turns said before.

**What a turn did** (`TurnRead`): its reply's clauses, those heard and those the guard blocked,
the talker's clauses as written (`TextTurn.written`: digits and all, where a clause cut into
several requests is heard as said), its tool calls and cards; as it stood when the caller next
spoke, whether the read-back the scenario expects (its values, the total priced from the
airline) was said whole, or any read-back when it expects none, and whether the caller was asked
again; once the call settled, whether its words confirmed the booking and how its write ended,
its sending line and then its outcome's said.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import date
from typing import Any, Final, Literal

from pydantic import JsonValue
from t2_agentic_voice import ProviderError, VoiceAgent, VoiceSettings
from t2_agentic_voice.evals import HeardClause, TextCall, TextToolCall, TextTurn
from t2_agentic_voice.ports import ChatModel

from flight_voice.agent import declare
from flight_voice.airline.bookings import Booking, BookingStore, Leg, priced
from flight_voice.airline.system import Airline
from flight_voice.booking.draft import BOOK_TRIP
from flight_voice.evals.call_wait import OutcomeKind, holds, outcome_of, settle, wait_held
from flight_voice.evals.scenarios import ReadBack, Scenario, Turn
from flight_voice.traveler import demo_caller
from flight_voice.trip import TripBook

LIMIT_S: Final = 120.0  # wall seconds a booking's write, or the last reply, may take to end
TURN_S: Final = 90.0  # a play's whole limit, a turn's share
Stuck = Literal["stuck", "provider"]
ClockKind = Literal["virtual", "system"]
# Builds a call as `TextCall(agent, llm=..., settings=..., caller=..., language=..., today=...)`.
CallFactory = Callable[..., TextCall]
# Builds the agent a play measures, over its airline and trip book: the app's own.
AgentOf = Callable[[Airline, TripBook], VoiceAgent]
# Says a turn of a play, given the turn said before it (None for none): `say_turn` by default.
Say = Callable[[TextCall, Turn, TextTurn | None], Coroutine[Any, Any, TextTurn]]


def airline_for(scenario: Scenario) -> Airline:
    """A new mock airline for one play of `scenario`: its today pinned, its modes set."""
    modes = scenario.modes

    def today() -> date:
        return scenario.today

    bookings = BookingStore(today=today, mode=modes.booking, lookup=modes.lookup)
    return Airline(
        today=today, bookings=bookings, search_mode=modes.search, profile_mode=modes.profile
    )


def call_language(scenario: Scenario) -> Literal["ar-SA", "en"]:
    """The agent's language the call joins in: its Arabic for a Saudi or an MSA caller."""
    return "en" if scenario.language == "en" else "ar-SA"


def read_back_values(read_back: ReadBack, today: date) -> dict[str, JsonValue]:
    """The values the booking's draft holds when it reads `read_back` back, its total priced
    from the airline on `today`."""
    back = read_back.return_
    legs: tuple[Leg, ...] = (Leg(flight=read_back.outbound.number, day=read_back.outbound.day),)
    if back is not None:
        legs = (*legs, Leg(flight=back.number, day=back.day))
    return {
        "outbound_flight": read_back.outbound.number,
        "outbound_date": read_back.outbound.day.isoformat(),
        "return_flight": None if back is None else back.number,
        "return_date": None if back is None else back.day.isoformat(),
        "one_way": read_back.one_way,
        "travelers": read_back.travelers,
        "cabin": read_back.cabin,
        "total_sar": priced(legs, read_back.cabin, read_back.travelers, today),
    }


@dataclass(frozen=True)
class TurnRead:
    """What one said turn did (the module's docstring); `index`, its place in the scenario."""

    index: int
    fate: str
    clauses: tuple[HeardClause, ...]
    heard: tuple[HeardClause, ...]
    tools: tuple[TextToolCall, ...]
    cards: int
    read_back: bool = False
    asked_again: bool = False
    confirmed: bool = False
    ended: OutcomeKind | None = None
    blocked: int = 0  # the reply's clauses the output guard blocked
    blocked_texts: tuple[str, ...] = ()  # their texts, in order, never said
    written: tuple[str, ...] = ()  # the talker's clauses the guard passed, as written


@dataclass(frozen=True)
class PlayRead:
    """What a play did: a read for each scenario turn (None for a stop, or a turn never said),
    the call's violations (`TextCall.violations`), why it could not go on (`failure`), the
    bookings the airline made and the writes that reached it."""

    turns: tuple[TurnRead | None, ...]
    violations: tuple[str, ...]
    failure: Stuck | None = None
    made: tuple[Booking, ...] = ()
    writes: int = 0


@dataclass
class _Saying:
    """The turns said so far by their scenario place, what each had shown when the caller
    next spoke, and the expected read-back's values by place."""

    expected: Mapping[int, dict[str, JsonValue]]
    said: dict[int, TextTurn] = field(default_factory=dict)
    shown: dict[int, tuple[bool, bool]] = field(default_factory=dict)

    def look(self) -> None:
        """What each said turn has shown so far, read once, as the caller next speaks."""
        for n, turn in self.said.items():
            if n not in self.shown:
                values = self.expected.get(n, {})
                self.shown[n] = (
                    holds(turn.expect.read_back, **values),
                    holds(turn.expect.asked_again),
                )

    def read(self, count: int, call: TextCall, airline: Airline, failure: Stuck | None) -> PlayRead:
        self.look()
        turns = tuple(self._turn(n) for n in range(count))
        store = airline.bookings
        return PlayRead(turns, call.violations, failure, store.made, len(store.writes))

    def _turn(self, n: int) -> TurnRead | None:
        turn = self.said.get(n)
        if turn is None:
            return None
        read_back, asked_again = self.shown[n]
        return TurnRead(
            index=n,
            fate=turn.fate,
            clauses=turn.clauses,
            heard=turn.heard(),
            tools=turn.tool_calls,
            cards=len(turn.cards),
            read_back=read_back,
            asked_again=asked_again,
            confirmed=holds(turn.expect.confirmed, BOOK_TRIP),
            ended=outcome_of(turn),
            blocked=len(turn.blocked),
            blocked_texts=tuple(c.text for c in turn.blocked),
            written=turn.written,
        )


async def say_turn(call: TextCall, turn: Turn, before: TextTurn | None = None) -> TextTurn:
    """`turn` said when it says (the module's docstring); `before` is not read here."""
    text = turn.says or ""
    if turn.when == "tool_running":
        return await call.user(text, at="tool_running")
    return await call.user(text, during=turn.when)


def _next_runs_a_tool(turns: Sequence[Turn], n: int) -> bool:
    if n + 1 >= len(turns):
        return False
    after = turns[n + 1]
    return (after.at if after.stop else after.when) == "tool_running"


async def _said_all(
    call: TextCall, turns: Sequence[Turn], limit_s: float, saying: _Saying, say: Say
) -> None:
    """Each of `turns` said by `say`, or a stop made, when it says (the module's docstring),
    kept in `saying` as it is, so a play that stops partway keeps the turns said before."""
    answering: tuple[int, asyncio.Task[TextTurn]] | None = None
    try:
        for n, turn in enumerate(turns):
            if turn.stop:
                await call.advance(turn.after_s)
                await call.stop()
            else:
                if turn.after_s:
                    await call.advance(turn.after_s)
                if turn.when is None:
                    await settle(call, list(saying.said.values()), limit_s, last=False)
                saying.look()
                last = list(saying.said.values())[-1] if saying.said else None
                if _next_runs_a_tool(turns, n):
                    answering = (n, asyncio.create_task(say(call, turn, last)))
                    continue
                saying.said[n] = await say(call, turn, last)
            if answering is not None:
                earlier, task = answering
                answering = None
                saying.said[earlier] = await task
        said = list(saying.said.values())
        if turns and turns[-1].when == "read_back":
            await wait_held(call, said, saying.said.get(len(turns) - 1), limit_s)
        await settle(call, said, limit_s, last=True)
    finally:
        if answering is not None:  # the turn before one that stuck, kept when it was said
            earlier, task = answering
            task.cancel()
            (before,) = await asyncio.gather(task, return_exceptions=True)
            if isinstance(before, TextTurn):
                saying.said[earlier] = before


async def play(
    scenario: Scenario,
    llm: ChatModel,
    settings: VoiceSettings,
    *,
    agent: AgentOf = declare,
    call: CallFactory = TextCall,
    clock: ClockKind = "system",
    limit_s: float = LIMIT_S,
    whole_s: float | None = None,
    say: Say = say_turn,
) -> PlayRead:
    """One play of `scenario`: a call of `agent` over a new airline and trip book on `llm`,
    with `settings`, each turn said when it says (by `say`), within `whole_s` in all (`TURN_S` a
    turn when None); what each did read once the call settled, or as it stood when it could not
    go on."""
    airline, trips = airline_for(scenario), TripBook()
    expected = {
        n: read_back_values(t.read_back, scenario.today)
        for n, t in enumerate(scenario.turns)
        if t.read_back is not None
    }
    saying = _Saying(expected)
    limit = TURN_S * len(scenario.turns) if whole_s is None else whole_s
    read: PlayRead | None = None
    try:
        async with call(
            agent(airline, trips),
            llm=llm,
            settings=settings,
            caller=demo_caller(),
            language=call_language(scenario),
            clock=clock,
            today=scenario.today,
        ) as held:
            failure: Stuck | None = None
            try:
                async with asyncio.timeout(limit):
                    await _said_all(held, scenario.turns, limit_s, saying, say)
            except (AssertionError, TimeoutError):  # a wait given up on, or the talker's
                failure = "stuck"
            except ProviderError:
                failure = "provider"
            read = saying.read(len(scenario.turns), held, airline, failure)
            return read
    except AssertionError:  # the talker's, raised as the call ends
        if read is None:
            raise
        return replace(read, failure=read.failure or "stuck")

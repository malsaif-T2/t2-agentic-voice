"""Run F's play of a scripted call with the lean agent (`poe eval-flights --agent lean`; D-113):
call.py's `play`, the same seam and the same turns said, with the lean agent over the play's new
airline and trip book, its booking check reading the call's own events (`TextCall.emitted`).

**The timing words.** A turn said `when = "read_back"` or `"closing_question"` names a moment of
the library's read-back, which the lean agent has none of. One said `"closing_question"` is said
over the reply's last clause, its question ("Shall I book it?"), once every clause before it has
played and those clauses stated the trip's total (`say`: `TextCall`'s `during="agent_speaking"`;
`total_heard`, by the booking check's `stated_at`, the total priced from the play's trip), and
the call is then moved on until that reply has ended and the turn was answered, or `HELD_S`
passed: the library answers a yes said there once the reply's tail and the speech detector's
lag have passed (`interruptions.answer_yes_over_question`, D-116), and other words over it stop
it or go on as the interruption rule says. When the reply has ended by then, or never came, or
its total is said in its last clause or not at all, the turn is said once the agent is silent,
so the play never measures a refusal the agent did not cause. One said `"read_back"` is said
right after the agent's reply, once the agent is silent (`when` unset): a yes over a summary
that goes on is settled by the voice layer, never answered. A stop at one of those moments stops
the reply playing (`at = "agent_speaking"`).

**What else it reads** (`LeanRead`, a `PlayRead` with more): the model's replies the plain-speech
rule drops (D-111's rule written here again, so the measurement never reads the rule it
measures: a clause fewer than half of whose characters, spaces aside, are letters, marks or
digits, or one holding "[", "{" or "<"), counted over the talker's requests alone (those whose
system prompt names `find_flights`); and, from the call's events, the booking: the caller turns
until it (the turn whose reply booked, from 1), its scenario turn, and the seconds from the
call's start to the `book_trip` result that booked.
"""

from __future__ import annotations

import json
import unicodedata
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, fields
from typing import Any, Final

from t2_agentic_voice import VoiceAgent, VoiceSettings
from t2_agentic_voice.evals import TextCall, TextTurn
from t2_agentic_voice.events import CallStarted, Event, ToolFinished
from t2_agentic_voice.languages import split_clauses
from t2_agentic_voice.ports import ChatEvent, ChatModel, ChatRequest, TextDelta

from flight_voice.airline.system import Airline
from flight_voice.evals import call
from flight_voice.evals.call_wait import HELD_S, STEP_S
from flight_voice.evals.scenarios import Scenario, Turn
from flight_voice.lean.agent import declare
from flight_voice.lean.book import BOOK_TRIP
from flight_voice.lean.booking_check import BookingCheck, stated_at
from flight_voice.lean.find import FIND_FLIGHTS
from flight_voice.trip import TripBook

# The read-back's moments: in a lean play, a stop's over the reply; a turn's over its closing
# question (`OVER_QUESTION`) or right after it.
READ_BACK_MOMENTS: Final = frozenset({"read_back", "closing_question"})
OVER_QUESTION: Final = "closing_question"
WAIT_S: Final = 60.0  # call seconds a lean play waits for a reply's question, or its end
_NOT_SAID: Final = frozenset("[{<")
MIN_SHARE: Final = 0.5


@dataclass(frozen=True)
class LeanRead(call.PlayRead):
    """What a lean play did (the module's docstring): `PlayRead`'s, and the replies the
    plain-speech rule drops, and the booking's caller turns, scenario turn and seconds."""

    drops: int = 0
    booked_turns: int | None = None
    booked_index: int | None = None
    booked_s: float | None = None


def not_speech(clause: str) -> bool:
    """Whether `clause` is no speech, by D-111's rule (the module's docstring)."""
    if any(mark in clause for mark in _NOT_SAID):
        return True
    shown = [c for c in clause if not c.isspace()]
    said = [c for c in shown if c.isalnum() or unicodedata.category(c).startswith("M")]
    return bool(shown) and len(said) < MIN_SHARE * len(shown)


class Watched:
    """`inner`, the talker's model, each reply of its talker's requests read for a clause the
    plain-speech rule drops (`drops`); every other request passed on as it is."""

    def __init__(self, inner: ChatModel) -> None:
        self.inner = inner
        self.name, self.data_flow = inner.name, inner.data_flow
        self.drops = 0

    def stream(self, request: ChatRequest) -> AsyncIterator[ChatEvent]:
        return self._read(request)

    async def _read(self, request: ChatRequest) -> AsyncIterator[ChatEvent]:
        talker = any(m.role == "system" and FIND_FLIGHTS in m.content for m in request.messages)
        written: list[str] = []
        async for event in self.inner.stream(request):
            if isinstance(event, TextDelta):
                written.append(event.text)
            yield event
        if talker and any(not_speech(c) for c in split_clauses("".join(written), max_chars=None)):
            self.drops += 1

    async def aclose(self) -> None:
        await self.inner.aclose()


def lean_turns(scenario: Scenario) -> Scenario:
    """`scenario` with its read-back's moments made the lean agent's (the module's docstring):
    a turn said over the closing question keeps its word, which `say` reads."""
    turns: list[Turn] = []
    for turn in scenario.turns:
        if turn.stop and turn.at in READ_BACK_MOMENTS:
            turn = turn.model_copy(update={"at": "agent_speaking"})
        elif turn.when in READ_BACK_MOMENTS and turn.when != OVER_QUESTION:
            turn = turn.model_copy(update={"when": None})
        turns.append(turn)
    return scenario.model_copy(update={"turns": tuple(turns)})


async def _until(
    text_call: TextCall, ready: Callable[[], bool], *, limit_s: float = WAIT_S
) -> bool:
    """The call moved on, `STEP_S` at a time, until `ready`, at most `limit_s` call seconds:
    whether it came."""
    waited = 0.0
    while not ready():
        if waited >= limit_s:
            return False
        await text_call.advance(STEP_S)
        waited += STEP_S
    return True


def _ended(before: TextTurn) -> bool:
    """Whether every clause of `before`'s reply has played or was cut."""
    return all(c.fate != "unplayed" for c in before.clauses)


async def to_question(text_call: TextCall, before: TextTurn) -> bool:
    """The call moved on until `before`'s reply plays its last clause, every clause before it
    played whole (at most `WAIT_S`): whether that clause still plays."""

    def ready() -> bool:
        clauses = before.clauses
        return bool(clauses) and all(c.fate == "played" for c in clauses[:-1])

    return await _until(text_call, ready) and not _ended(before)


async def to_end(text_call: TextCall, before: TextTurn) -> None:
    """The call moved on until `before`'s reply has ended (at most `WAIT_S`)."""
    await _until(text_call, lambda: _ended(before))


def total_heard(before: TextTurn, total: int | None) -> bool:
    """Whether the clauses of `before`'s reply before its last state `total`, the trip's (the
    booking check's `stated_at`); never for no total."""
    said = " ".join(clause.text for clause in before.clauses[:-1])
    return total is not None and stated_at(said, total) is not None


async def say(
    text_call: TextCall, turn: Turn, before: TextTurn | None, *, total: Callable[[], int | None]
) -> TextTurn:
    """`turn` said as a lean play says it (the module's timing words): over the closing
    question of `before`'s reply when it is marked so and the clauses before it stated the
    trip's total (`total`, read once they have played), then the call moved on until that reply
    ended and the turn was answered, or `HELD_S` passed; any other as call.py says it."""
    if turn.when != OVER_QUESTION:
        return await call.say_turn(text_call, turn)
    words = turn.says or ""
    over = before is not None and await to_question(text_call, before)
    if before is None or not over or not total_heard(before, total()):
        return await text_call.user(words)  # said once the agent is silent
    said = await text_call.user(words, during="agent_speaking")
    await to_end(text_call, before)
    await _until(text_call, lambda: said.fate != "went_on", limit_s=HELD_S)
    return said


def _total(text_call: TextCall, airline: Airline, trips: TripBook) -> int | None:
    """The total of the trip the call has chosen so far, priced now; None before the call
    started, or while a leg is missing."""
    call_id = next((event.call_id for event in text_call.emitted), None)
    return None if call_id is None else trips.get(call_id).total(airline.today())


def booking_of(events: tuple[Event, ...], scenario: Scenario) -> dict[str, Any]:
    """The booking's caller turns, scenario turn and seconds from the call's start, read from
    its events; none of them when nothing was booked."""
    started = next((e.at for e in events if isinstance(e, CallStarted)), None)
    booked = next(
        (
            e
            for e in events
            if isinstance(e, ToolFinished)
            and e.tool == BOOK_TRIP
            and e.ok
            and e.turn_id is not None
            and _status(e.result) == "booked"
        ),
        None,
    )
    if booked is None or booked.turn_id is None:
        return {}
    said = [n for n, t in enumerate(scenario.turns) if not t.stop]
    index = said[booked.turn_id] if booked.turn_id < len(said) else None
    seconds = None if started is None else (booked.at - started).total_seconds()
    return {
        "booked_turns": booked.turn_id + 1,
        "booked_index": index,
        "booked_s": None if seconds is None else round(max(0.0, seconds), 3),
    }


def _status(result: str) -> object:
    """A tool result's status; a result cut short is read by its text."""
    try:
        found = json.loads(result)
    except ValueError:
        return "booked" if '"status": "booked"' in result else None
    return found.get("status") if isinstance(found, dict) else None


async def play(
    scenario: Scenario, llm: ChatModel, settings: VoiceSettings, **options: Any
) -> LeanRead:
    """One lean play of `scenario` on `llm` with `settings` (the module's docstring); `options`
    are call.py's `play`'s (`clock`, `limit_s`, `whole_s`, `call`)."""
    check = BookingCheck()
    made: list[TextCall] = []
    built: list[tuple[Airline, TripBook]] = []
    build = options.pop("call", TextCall)

    def agent(airline: Airline, trips: TripBook) -> VoiceAgent:
        built.append((airline, trips))
        return declare(airline, trips, check)

    async def said(text_call: TextCall, turn: Turn, before: TextTurn | None) -> TextTurn:
        airline, trips = built[-1]
        return await say(text_call, turn, before, total=lambda: _total(text_call, airline, trips))

    def held(*args: Any, **kwargs: Any) -> TextCall:
        text_call: TextCall = build(*args, **kwargs)
        made.append(text_call)
        check.read_from(lambda: text_call.emitted)
        return text_call

    watched = Watched(llm)
    lean = lean_turns(scenario)
    read = await call.play(lean, watched, settings, agent=agent, call=held, say=said, **options)
    found = booking_of(made[0].emitted, scenario) if made else {}
    kept = {f.name: getattr(read, f.name) for f in fields(read)}
    return LeanRead(**kept, drops=watched.drops, **found)

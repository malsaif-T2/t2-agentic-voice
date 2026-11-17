"""Run F's play of a scripted call with the lean agent (`poe eval-flights --agent lean`; D-113):
call.py's `play`, the same seam and the same turns said, with the lean agent over the play's new
airline and trip book, its booking check reading the call's own events (`TextCall.emitted`).

**The timing words.** A turn said `when = "read_back"` or `"closing_question"` names a moment of
the library's read-back, which the lean agent has none of: it is said right after the agent's
reply, once the agent is silent (`when` unset), so it answers the reply that states the trip's
total. A stop at one of those moments stops the reply playing (`at = "agent_speaking"`).
Words said over a reply that goes on are settled by the voice layer, never answered, so a yes
over the summary would be lost: right after it is the lean agent's moment for it.

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
from collections.abc import AsyncIterator
from dataclasses import dataclass, fields
from typing import Any, Final

from t2_agentic_voice import VoiceAgent, VoiceSettings
from t2_agentic_voice.evals import TextCall
from t2_agentic_voice.events import CallStarted, Event, ToolFinished
from t2_agentic_voice.languages import split_clauses
from t2_agentic_voice.ports import ChatEvent, ChatModel, ChatRequest, TextDelta

from flight_voice.airline.system import Airline
from flight_voice.evals import call
from flight_voice.evals.scenarios import Scenario, Turn
from flight_voice.lean.agent import declare
from flight_voice.lean.book import BOOK_TRIP
from flight_voice.lean.booking_check import BookingCheck
from flight_voice.lean.find import FIND_FLIGHTS
from flight_voice.trip import TripBook

# The read-back's moments, said right after the reply in a lean play; a stop's, over it.
READ_BACK_MOMENTS: Final = frozenset({"read_back", "closing_question"})
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
    """`scenario` with its read-back's moments made the lean agent's (the module's docstring)."""
    turns: list[Turn] = []
    for turn in scenario.turns:
        if turn.stop and turn.at in READ_BACK_MOMENTS:
            turn = turn.model_copy(update={"at": "agent_speaking"})
        elif turn.when in READ_BACK_MOMENTS:
            turn = turn.model_copy(update={"when": None})
        turns.append(turn)
    return scenario.model_copy(update={"turns": tuple(turns)})


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
    build = options.pop("call", TextCall)

    def agent(airline: Airline, trips: TripBook) -> VoiceAgent:
        return declare(airline, trips, check)

    def held(*args: Any, **kwargs: Any) -> TextCall:
        text_call: TextCall = build(*args, **kwargs)
        made.append(text_call)
        check.read_from(lambda: text_call.emitted)
        return text_call

    watched = Watched(llm)
    lean = lean_turns(scenario)
    read = await call.play(lean, watched, settings, agent=agent, call=held, **options)
    found = booking_of(made[0].emitted, scenario) if made else {}
    kept = {f.name: getattr(read, f.name) for f in fields(read)}
    return LeanRead(**kept, drops=watched.drops, **found)

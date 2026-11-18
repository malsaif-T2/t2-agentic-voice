"""What the lean agent's tests share: one call's tools over one set of sources (`LeanCall`: the
mock airline behind the flight data port, `mock_deps`, or any `LeanDeps`), each tool run through
the library's own runner from the arguments as JSON (tests/flight_voice/tools/tool_support.py's
`run`), and the call's events fed to the check as the runtime's observers would (`said`,
`heard`, `ended`)."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any, Final

from flight_voice.airline.system import Airline
from flight_voice.lean.book import book_trip
from flight_voice.lean.booking_check import BookingCheck
from flight_voice.lean.choose import choose_flights
from flight_voice.lean.deps import LeanDeps, mock_deps
from flight_voice.lean.draft import LeanBook, LeanDraft
from flight_voice.lean.find import find_flights
from flight_voice.persona import Names
from flight_voice.said import Tag
from t2_agentic_voice import Caller, ToolResult
from t2_agentic_voice.events import AgentSpeechEnded, CallEnded, CallReport, UserTurnEnded

from tests.flight_voice.tools.tool_support import CALL_ID, CALLER, airline, data, run

AT: Final = datetime(2026, 11, 16, 9, 0, tzinfo=UTC)
# Jeddah: four flights a day each way; out on Thursday 19 November, back on Saturday the 21st.
OUT: Final = "2026-11-19"
BACK: Final = "2026-11-21"


def lean_deps(flights: Airline | None = None, **more: Any) -> LeanDeps:
    """The lean tools' sources over the mock airline (`flights`, or a new one on the pinned
    day)."""
    return mock_deps(flights if flights is not None else airline(), Names(), **more)


class LeanCall:
    """One call's lean tools over one set of sources (the mock's unless `deps` is given), in
    `tag`."""

    def __init__(
        self, tag: Tag = "en", flights: Airline | None = None, deps: LeanDeps | None = None
    ) -> None:
        self.tag = tag
        self.deps = deps if deps is not None else lean_deps(flights)
        self.airline = self.deps.airline
        self.trips: LeanBook = self.deps.trips
        self.check: BookingCheck = self.deps.check
        self._turn = 0

    def find(self, **arguments: Any) -> ToolResult:
        return run(find_flights(self.deps), self.tag, **arguments)

    def choose(self, **arguments: Any) -> ToolResult:
        return run(choose_flights(self.deps), self.tag, **arguments)

    def book(self, caller: Caller = CALLER) -> ToolResult:
        return run(book_trip(self.deps), self.tag, caller=caller)

    @property
    def draft(self) -> LeanDraft:
        return self.trips.get(CALL_ID)

    def said(self, text: str, played: float = 1.0, turn: int | None = None) -> None:
        """A reply of the agent ended, `played` of it heard, answering `turn` (the caller's
        last turn unless given)."""
        answered = self._turn if turn is None else turn
        event = AgentSpeechEnded(
            call_id=CALL_ID, turn_id=answered, at=AT, text=text, played_fraction=played
        )
        asyncio.run(self.check.observed(event))

    def heard(self, words: str, played: str | None = None) -> None:
        """A turn of the caller's ended, `words` heard, begun once `played` of the reply it
        was said over had played (None: said while the agent was silent)."""
        self._turn += 1
        event = UserTurnEnded(
            call_id=CALL_ID, turn_id=self._turn, at=AT, heard=words, reply_played=played
        )
        asyncio.run(self.check.observed(event))

    def ended(self) -> None:
        """The call ended."""
        report = CallReport(
            call_id=CALL_ID, agent="flight-lean", started_at=AT, ended_at=AT, ended_by="hangup"
        )
        asyncio.run(self.check.observed(CallEnded(call_id=CALL_ID, at=AT, report=report)))

    def total(self) -> int:
        """The trip's total, every leg chosen."""
        total = self.draft.total()
        assert total is not None
        return total


def ids(result: ToolResult, leg: str = "outbound") -> list[str]:
    """The ids of a leg's options in a `find_flights` result, or listed in a `choose_flights`
    one (a round trip's return, once the outbound is chosen)."""
    answer = data(result)
    return [o["id"] for o in answer.get("listed", answer)[leg]["options"]]


def chosen_trip(tag: Tag = "en", **found: Any) -> LeanCall:
    """A call that found Jeddah, out on the 19th and back on the 21st, and chose the first
    flight each way."""
    call = LeanCall(tag)
    listed = call.find(destination="Jeddah", depart=OUT, return_date=BACK, **found)
    out = call.choose(outbound_id=ids(listed)[0])
    picked = call.choose(return_id=ids(out, "return")[0])
    assert data(picked)["missing"] == []
    return call

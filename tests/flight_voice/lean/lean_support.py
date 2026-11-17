"""What the lean agent's tests share: one call's four tools over one airline, one trip book and
one booking check (`LeanCall`), each tool run through the library's own runner from the
arguments as JSON (tests/flight_voice/tools/tool_support.py's `run`), and the call's events fed
to the check as the runtime's observers would (`said`, `heard`, `ended`)."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any, Final

from flight_voice.airline.system import Airline
from flight_voice.lean.book import book_trip
from flight_voice.lean.booking_check import BookingCheck
from flight_voice.lean.choose import choose_flights
from flight_voice.lean.find import find_flights
from flight_voice.said import Tag
from flight_voice.trip import TripBook, TripDraft
from t2_agentic_voice import Caller, ToolResult
from t2_agentic_voice.events import AgentSpeechEnded, CallEnded, CallReport, UserTurnEnded

from tests.flight_voice.tools.tool_support import CALL_ID, CALLER, airline, data, run

AT: Final = datetime(2026, 11, 16, 9, 0, tzinfo=UTC)
# Jeddah: four flights a day each way; out on Thursday 19 November, back on Saturday the 21st.
OUT: Final = "2026-11-19"
BACK: Final = "2026-11-21"


class LeanCall:
    """One call's lean tools over one airline, trip book and booking check, in `tag`."""

    def __init__(self, tag: Tag = "en", flights: Airline | None = None) -> None:
        self.tag = tag
        self.airline = flights if flights is not None else airline()
        self.trips = TripBook()
        self.check = BookingCheck()
        self._turn = 0

    def find(self, **arguments: Any) -> ToolResult:
        return run(find_flights(self.airline, self.trips, self.check), self.tag, **arguments)

    def choose(self, **arguments: Any) -> ToolResult:
        return run(choose_flights(self.airline, self.trips, self.check), self.tag, **arguments)

    def book(self, caller: Caller = CALLER) -> ToolResult:
        tool = book_trip(self.airline, self.trips, self.check)
        return run(tool, self.tag, caller=caller)

    @property
    def draft(self) -> TripDraft:
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
        total = self.draft.total(self.airline.today())
        assert total is not None
        return total


def ids(result: ToolResult, leg: str = "outbound") -> list[str]:
    """The ids of a leg's options in a `find_flights` result."""
    return [o["id"] for o in data(result)[leg]["options"]]


def chosen_trip(tag: Tag = "en", **found: Any) -> LeanCall:
    """A call that found Jeddah, out on the 19th and back on the 21st, and chose the first
    flight each way."""
    call = LeanCall(tag)
    listed = call.find(destination="Jeddah", depart=OUT, return_date=BACK, **found)
    picked = call.choose(outbound_id=ids(listed)[0], return_id=ids(listed, "return")[0])
    assert data(picked)["missing"] == []
    return call

"""The flight agent's read tools as one set: seven, each named once, each a read tool with the
library's five-second timeout, the search and the cabins under the search's progress line and the
calendar under its own; none backs up a booking claim; and every `say` the tools give is one of
the app's fixed strings, listed here, none built from words a caller could say."""

from __future__ import annotations

from flight_voice.tools import flight_tools
from flight_voice.tools.results import SAY
from flight_voice.trip import TripBook

from tests.flight_voice.tools.tool_support import airline

SAYS = {
    "listed",
    "listed_more",
    "listed_full",
    "listed_more_full",
    "not_served_city",
    "not_served_route",
    "past",
    "beyond_window",
    "no_such_day",
    "return_before_departure",
    "return_only",
    "needs_return_date",
    "cabin_not_offered",
    "no_flights_that_day",
    "no_seats",
    "no_seats_flight",
    "nothing_listed",
    "unclear_choice",
    "chosen_then_return",
    "chosen_then_outbound",
    "chosen_needs_return",
    "chosen_return_full",
    "complete",
    "changed",
    "changed_relist",
    "changed_lost",
    "changed_needs_return",
    "trip",
    "trip_empty",
    "calendar",
    "cabins",
    "profile",
}


def test_the_seven_read_tools_each_named_once() -> None:
    tools = flight_tools(airline(), TripBook())
    names = [t.name for t in tools]
    assert names == [
        "search_flights",
        "choose_flight",
        "change_trip",
        "get_trip",
        "fare_calendar",
        "compare_cabins",
        "traveler_profile",
    ]
    assert all(t.timeout_s == 5.0 and t.reports_on == () for t in tools)
    progress = {t.name: t.progress for t in tools if t.progress is not None}
    assert progress == {
        "search_flights": "searching",
        "fare_calendar": "fares",
        "compare_cabins": "searching",
    }


def test_every_say_is_one_of_the_fixed_strings_listed() -> None:
    assert set(SAY) == SAYS
    assert all(text and "{" not in text and text.endswith(".") for text in SAY.values())
    assert "book_trip" in SAY["complete"] and "say nothing yourself" in SAY["complete"]

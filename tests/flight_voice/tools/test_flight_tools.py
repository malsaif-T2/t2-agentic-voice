"""The flight agent's read tools as one set: seven, each named once, each a read tool with the
library's five-second timeout, the search and the cabins under the search's progress line and the
calendar under its own; none backs up a booking claim; and every `say` the tools give is one of
the app's fixed strings, listed here, none built from words a caller could say: a listing's asks
for three times aloud and a fourth by its part of the day; a first outbound one for its day and
weekday first (f27, f-dev-5), a return one for no day, and one on a new day for that day first,
the fare's basis not said again."""

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
    "return_listed",
    "return_listed_more",
    "return_listed_full",
    "return_listed_more_full",
    "relisted",
    "relisted_more",
    "relisted_full",
    "relisted_more_full",
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


def test_a_listing_says_three_times_and_the_one_more_by_its_part_of_the_day() -> None:
    """Spec 3.2: three aloud, then "and one more in the evening"; never the fourth's time."""
    for start in ("listed", "return_listed", "relisted"):
        for key in (f"{start}_more", f"{start}_more_full"):
            assert "options 1 to 3 in order" in SAY[key]
            assert "one more and its part of the day (part_of_day_said)" in SAY[key]
            assert "never its time or its fare" in SAY[key] and "when it leaves" not in SAY[key]
        for key in (start, f"{start}_full"):
            assert "at most three" in SAY[key] and "one more" not in SAY[key]


def test_a_first_outbound_listing_says_its_day_first_and_a_return_one_does_not() -> None:
    """f27 p2: a first listing that named no day, then the bare day the caller said was heard
    as an hour. A return listing follows the outbound choice said back, so it keeps its words."""
    first = "Say the day with its weekday first, in place of saying their request back, then "
    for key in ("listed", "listed_more", "listed_full", "listed_more_full"):
        assert SAY[key].startswith(first) and "Say once that fares" in SAY[key]
        back = SAY["return_" + key]
        assert back == "Say " + SAY[key].removeprefix(first) and "weekday" not in back


def test_a_listing_on_a_new_day_says_the_day_first_and_not_the_basis_again() -> None:
    for key in ("relisted", "relisted_more", "relisted_full", "relisted_more_full"):
        assert SAY[key].startswith("Say the new day with its weekday first, then ")
        assert "Do not say again that fares are one way, per person." in SAY[key]
        assert "Then ask which one they want." in SAY[key]
        assert "Say once that fares" in SAY[key.replace("relisted", "listed")]

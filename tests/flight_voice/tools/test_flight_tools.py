"""The flight agent's read tools as one set: seven, each named once, each a read tool with the
library's five-second timeout, the search and the cabins under the search's progress line and the
calendar under its own; none backs up a booking claim; and every `say` the tools give is one of
the app's fixed strings, listed here, none built from words a caller could say: a listing of
three or four flights asks for their count, first and last times and the cheapest, of one or two
for each (the owner's ruling); a first outbound one for its day and weekday first (f27,
f-dev-5) and the fare's basis, said once a call, a return one for no day, and one on a new day
for that day first; a span of days for its days, times and two cheapest; a full flight said as
full, and nothing changed unasked after one."""

from __future__ import annotations

from flight_voice.tools import flight_tools
from flight_voice.tools.results import SAY
from flight_voice.trip import TripBook

from tests.flight_voice.tools.tool_support import airline

SAYS = {
    "listed",
    "listed_full",
    "listed_brief",
    "listed_brief_full",
    "return_listed",
    "return_listed_full",
    "return_listed_brief",
    "return_listed_brief_full",
    "relisted",
    "relisted_full",
    "relisted_brief",
    "relisted_brief_full",
    "days",
    "days_some",
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
    "unclear_choice_full",
    "unclear_choice_brief",
    "unclear_choice_brief_full",
    "chosen_then_return",
    "chosen_then_outbound",
    "chosen_needs_return",
    "chosen_return_full",
    "complete",
    "changed",
    "changed_relist",
    "changed_relist_full",
    "changed_relist_brief",
    "changed_relist_brief_full",
    "changed_lost",
    "changed_lost_full",
    "changed_lost_brief",
    "changed_lost_brief_full",
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


def test_a_day_of_three_or_four_flights_is_said_briefly_the_others_only_when_asked() -> None:
    """The owner's ruling of 2026-11-17 ("Brief, voice only"): three or four flights are said
    by their count, their first and last departure times and the cheapest; one or two each by
    time and fare."""
    brief = (
        "how many flights there are (count), the first and last departure times (first_departs, "
        "last_departs), and the cheapest by its departure time and"
    )
    starts = ("listed", "return_listed", "relisted", "changed_relist", "changed_lost")
    for start in (*starts, "unclear_choice"):
        for key in (f"{start}_brief", f"{start}_brief_full"):
            assert brief in SAY[key], key
            assert "say the other flights only when the caller asks for them" in SAY[key]
            assert "one more" not in SAY[key] and "at most three" not in SAY[key]
        for key in (start, f"{start}_full"):
            assert "each by its departure time and" in SAY[key] and brief not in SAY[key], key
    assert "new fare" in SAY["changed_relist_brief"] and "new fare" in SAY["changed_lost"]


def test_the_fares_basis_is_said_once_a_call_on_the_first_listing() -> None:
    """The return listing said the basis a second time (the owner's ruling): only the first outbound
    listing says it; every other listing, and the pick that lists the return, does not again."""
    once, again = "Say once that fares", "Do not say again that fares are one way, per person."
    for key, text in SAY.items():
        if key.startswith("listed"):
            assert once in text and again not in text, key
        elif key.startswith(("return_listed", "relisted", "chosen_then_return")):
            assert again in text and once not in text, key
    assert "returns.say" in SAY["chosen_then_return"]


def test_a_span_of_days_is_said_by_its_days_its_times_and_its_two_cheapest() -> None:
    for key in ("days", "days_some"):
        assert SAY[key].startswith("Say the span by its first and last days with their weekdays")
        assert "the two cheapest days (marked) with their fares" in SAY[key]
        assert SAY[key].endswith("which day they would like to leave. Do not list flights yet.")
    assert "but the days in no_flight_days" in SAY["days_some"]
    assert "no_flight_days" not in SAY["days"]


def test_a_first_outbound_listing_says_its_day_first_and_a_return_one_does_not() -> None:
    """f27 p2: a first listing that named no day, then the bare day the caller said was heard
    as an hour. A return listing follows the outbound choice said back, so it keeps its words."""
    first = "Say the day with its weekday first, in place of saying their request back, then "
    for key in ("listed", "listed_brief", "listed_full", "listed_brief_full"):
        assert SAY[key].startswith(first) and "Say once that fares" in SAY[key]
        back = SAY["return_" + key]
        own = (
            SAY[key]
            .removeprefix(first)
            .replace(
                "Say once that fares are one way, per person.",
                "Do not say again that fares are one way, per person.",
            )
        )
        assert back == "Say " + own and "weekday" not in back


def test_a_listing_on_a_new_day_says_the_day_first_and_not_the_basis_again() -> None:
    for key in ("relisted", "relisted_brief", "relisted_full", "relisted_brief_full"):
        assert SAY[key].startswith("Say the new day with its weekday first, then ")
        assert "Do not say again that fares are one way, per person." in SAY[key]
        assert "Then ask which one they want." in SAY[key]
        assert "Say once that fares" in SAY[key.replace("relisted", "listed")]


def test_a_full_flight_is_said_as_full_before_the_fares_basis_and_never_as_the_cheapest() -> None:
    """The owner's live call: a full flight was said with its fare, a dearer one as the
    cheapest, and the caller picked the full one. The rule is an order, before the basis."""
    full = (
        "A flight with seats_ok false is full in this cabin: say it by its departure time as "
        "full, with no fare, and never as the cheapest."
    )
    keys = [k for k in SAY if k.endswith("_full") and k != "chosen_return_full"]
    assert len(keys) == 12
    for key in keys:
        assert full in SAY[key], key
        basis = [at for at in (SAY[key].find(" Say once"), SAY[key].find(" Do not say")) if at > 0]
        assert all(SAY[key].index(full) < at for at in basis), key
        assert full not in SAY[key.removesuffix("_full")], key


def test_after_a_full_flight_or_day_nothing_is_changed_the_caller_did_not_ask_for() -> None:
    """The owner's live call: after a full flight, the reply changed the cabin unasked."""
    wait = "Then wait for their answer; call change_trip only for a cabin the caller asks for."
    assert SAY["no_seats"].endswith(wait) and SAY["no_seats_flight"].endswith(wait)
    for key in ("changed_lost", "changed_lost_full"):
        assert "the one leaving at lost_departs" in SAY[key]

"""A listing as the talker reads it: of four options, the say asks for their count, their first
and last departure times and the cheapest (the owner's ruling), which the result gives, and its
data keeps every option's times, so the talker can answer a caller who asks for the others; and
a listing on a new day, after the caller heard another day's, said from that day, the fare's
basis not said again (f04's correction)."""

from __future__ import annotations

from typing import Any

import pytest
from flight_voice.said import Tag
from flight_voice.tools.cards import indic
from flight_voice.tools.results import SAY
from flight_voice.tools.search import search_flights
from flight_voice.trip import TripBook

from tests.flight_voice.tools.tool_support import TAGS, airline, data, run

TOMORROW: dict[str, Any] = {"kind": "relative", "when": "tomorrow"}


@pytest.mark.parametrize("tag", TAGS)
def test_four_flights_are_said_by_their_count_first_last_and_cheapest(tag: Tag) -> None:
    tool = search_flights(airline(), TripBook())
    made = run(tool, tag, destination="Jeddah", depart=TOMORROW, one_way=True)
    found = data(made)
    assert found["say"] == SAY["listed_brief"] and "more" not in found
    assert (found["count"], found["first_departs"], found["last_departs"]) == (4, "06:00", "21:00")
    assert all({"departs", "arrives", "fare_sar"} <= set(o) for o in found["options"])
    assert found["options"][3]["n"] == 4 and found["options"][3]["departs"] == "21:00"
    assert made.card is not None and len(made.card.rows) == 4
    assert made.card.rows[3].title.startswith("21:00" if tag == "en" else indic("21:00"))


def test_one_or_two_flights_are_each_said_and_their_spread_given() -> None:
    found = data(
        run(
            search_flights(airline(), TripBook()),
            destination="London",
            depart=TOMORROW,
            one_way=True,
        )
    )
    assert found["say"] == SAY["listed"] and found["count"] == 2
    assert (found["first_departs"], found["last_departs"]) == ("09:10", "14:40")


def test_a_search_on_a_new_day_is_said_from_that_day_without_the_basis_again() -> None:
    """«ثلطعش ديسمبر», then «لا لا، أربعطعش»: the caller heard the 13th's flights, so the 14th's
    are said from their day and its weekday, the fare's basis not said again; a search of the day
    already listed, or of another city that day, is a first listing."""
    tool = search_flights(airline(), TripBook())

    def day(n: int, city: str = "جدة") -> dict[str, Any]:
        on: dict[str, Any] = {"kind": "on", "day": n, "month": 12}
        return data(run(tool, "ar-SA", destination=city, depart=on, one_way=True))

    assert day(13)["say"] == SAY["listed_brief"]
    again = day(14)
    assert again["say"] == SAY["relisted_brief"] and again["date"]["iso"] == "2026-12-14"
    assert again["date"]["weekday"] and again["count"] == 4
    assert day(14)["say"] == SAY["listed_brief"]
    assert day(14, "الدوحة")["say"] == SAY["listed_brief"]
    assert day(17, "لندن")["say"] == SAY["relisted"]


def test_every_option_says_it_flies_nonstop() -> None:
    """The owner's live call: «فيها transit؟» got no answer, though every flight is nonstop."""
    found = data(run(search_flights(airline(), TripBook()), destination="Jeddah", depart=TOMORROW))
    assert found["status"] == "needs_return_date"
    listed = data(
        run(
            search_flights(airline(), TripBook()),
            destination="Paris",
            depart=TOMORROW,
            one_way=True,
        )
    )
    assert listed["options"] and all(o["nonstop"] is True for o in listed["options"])

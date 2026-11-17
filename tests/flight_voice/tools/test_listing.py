"""A listing as the talker reads it: of four options, the say asks for the fourth by its part of
the day (spec 3.2, "and one more in the evening"), and its data keeps its times, so the talker
can answer a caller who asks when it leaves; and a listing on a new day, after the caller heard
another day's, said from that day, the fare's basis not said again (f04's correction)."""

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
def test_the_one_more_is_asked_by_its_part_of_the_day_and_keeps_its_times(tag: Tag) -> None:
    tool = search_flights(airline(), TripBook())
    made = run(tool, tag, destination="Jeddah", depart=TOMORROW, one_way=True)
    found = data(made)
    more = found["options"][3]
    assert found["more"] == 1 and found["say"] == SAY["listed_more"]
    assert "its part of the day (part_of_day_said)" in found["say"]
    assert more["n"] == 4 and more["part_of_day_said"] and more["fare_sar"] > 0
    assert all({"departs", "arrives"} <= set(o) for o in found["options"])
    assert more["departs"] == "21:00"
    assert made.card is not None and len(made.card.rows) == 4
    assert made.card.rows[3].title.startswith("21:00" if tag == "en" else indic("21:00"))


def test_a_search_on_a_new_day_is_said_from_that_day_without_the_basis_again() -> None:
    """«ثلطعش ديسمبر», then «لا لا، أربعطعش»: the caller heard the 13th's flights, so the 14th's
    are said from their day and its weekday, the fare's basis not said again; a search of the day
    already listed, or of another city that day, is a first listing."""
    tool = search_flights(airline(), TripBook())

    def day(n: int, city: str = "جدة") -> dict[str, Any]:
        on: dict[str, Any] = {"kind": "on", "day": n, "month": 12}
        return data(run(tool, "ar-SA", destination=city, depart=on, one_way=True))

    assert day(13)["say"] == SAY["listed_more"]
    again = day(14)
    assert again["say"] == SAY["relisted_more"] and again["date"]["iso"] == "2026-12-14"
    assert again["date"]["weekday"] and again["more"] == 1
    assert day(14)["say"] == SAY["listed_more"]
    assert day(14, "الدوحة")["say"] == SAY["listed"]
    assert day(17, "لندن")["say"] == SAY["relisted"]

"""The cards the flight results show, each option one of the card's rows: a flight's times as
its title, its length, stops, flight and aircraft as its detail, its fare as its value, the
cheapest marked best, a full one unavailable, a picked leg chosen; each row's words and digits in
the reply's script; a listing of at most four rows, each an option the result gives the talker to
say; and every card of every tool, route and language passing the output guard's ID rule against
its result's data alone, so no number reaches the page that the result does not hold. The rule
reads numbers joined only by marks as one group, which is why a word always stands between two
numbers."""

from __future__ import annotations

import json
from typing import Any

import pytest
from flight_voice.airline.airports import CODES, HOME
from flight_voice.airline.system import Airline
from flight_voice.said import Tag
from flight_voice.tools.cabins import compare_cabins
from flight_voice.tools.calendar import fare_calendar
from flight_voice.tools.cards import indic
from flight_voice.tools.choose import change_trip
from flight_voice.tools.search import search_flights
from flight_voice.tools.trip_view import get_trip
from flight_voice.trip import TripBook
from t2_agentic_voice import Card, CardRow, ToolResult
from t2_agentic_voice.domain.cards import MAX_ROWS

from tests.flight_voice.scenario_dates import TODAY, business_sold_out
from tests.flight_voice.tools.tool_support import (
    CHEAPEST,
    FIRST,
    TAGS,
    airline,
    card_passes,
    data,
    ids_pass,
    london,
    run,
)

DEC_17: dict[str, Any] = {"kind": "on", "day": 17, "month": 12}
DEC_20: dict[str, Any] = {"kind": "on", "day": 20, "month": 12}
TOMORROW: dict[str, Any] = {"kind": "relative", "when": "tomorrow"}


def _listed(tag: Tag, **arguments: Any) -> Any:
    result = run(search_flights(airline(), TripBook()), tag, **arguments)
    assert result.ok and result.card is not None, result.data
    return result


def _card(result: ToolResult) -> Card:
    assert result.card is not None, result.data
    return result.card


def test_an_english_card_lists_each_flight_as_a_row_with_words_between_its_numbers() -> None:
    card = _listed("en", destination="London", depart=DEC_17, return_date=DEC_20).card
    assert card.title == "Riyadh to London, Thu 17 Dec" and card.steps == ()
    assert card.rows == (
        CardRow(
            title="09:10 to 13:15",
            detail="7 h 5 min, nonstop, flight T2 401 on a 787-9",
            value="3,560 SAR",
            mark="best",
        ),
        CardRow(
            title="14:40 to 18:45",
            detail="7 h 5 min, nonstop, flight T2 403 on a 787-9",
            value="3,780 SAR",
        ),
    )


def test_an_arabic_card_writes_its_times_and_fares_in_arabic_indic_digits() -> None:
    card = _listed("ar-SA", destination="لندن", depart=DEC_17, return_date=DEC_20).card
    assert card.title == "الرياض إلى لندن، الخميس ١٧ ديسمبر"
    assert card.rows[0] == CardRow(
        title="٠٩:١٠ إلى ١٣:١٥",
        detail="٧ س ٥ د، مباشرة، رحلة T2 401 على 787-9",
        value="٣٬٥٦٠ ريال",
        mark="best",
    )


def test_a_flight_landing_the_next_day_says_so() -> None:
    found = {"destination": "Singapore", "depart": DEC_17, "one_way": True}
    english = _listed("en", **found).card.rows[0]
    arabic = _listed("ar", **found).card.rows[0]
    assert english.title == "22:05 to 11:25 next day"
    assert english.detail is not None and english.detail.startswith("8 h 20 min,")
    assert arabic.title.endswith("من اليوم التالي")


@pytest.mark.parametrize("tag", TAGS)
def test_four_flights_are_four_rows_each_an_option_the_talker_says(tag: Tag) -> None:
    result = _listed(tag, destination="Jeddah", depart=TOMORROW, one_way=True, travelers=2)
    options = data(result)["options"]
    rows = result.card.rows
    assert len(rows) == len(options) == 4
    assert [row.mark for row in rows].count("best") == 1
    cheapest = next(n for n, o in enumerate(options) if o.get("mark") == "cheapest")
    assert rows[cheapest].mark == "best"
    for row, option in zip(rows, options, strict=True):
        departs = option["departs"] if tag == "en" else indic(option["departs"])
        assert row.title.startswith(departs) and row.detail is not None
        assert row.value is not None and indic(f"{option['fare_sar']:,}") in indic(row.value)
    assert data(result)["more"] == 1 and "one more" in data(result)["say"]


def test_a_full_flight_is_marked_unavailable_never_best() -> None:
    sold_out = business_sold_out("RUH", "CAI")
    assert sold_out is not None
    number, day = sold_out
    on = {"kind": "on", "day": day.day, "month": day.month}
    result = _listed("en", destination="Cairo", depart=on, one_way=True, cabin="business")
    by_flight = {
        row.detail.split("flight ")[1].split(" on ")[0]: row
        for row in result.card.rows
        if row.detail is not None
    }
    full = by_flight[f"T2 {number}"]
    assert full.mark == "unavailable"
    assert [row.mark for row in result.card.rows].count("best") <= 1 and card_passes(result)


@pytest.mark.parametrize("tag", TAGS)
@pytest.mark.parametrize("city", [c for c in CODES if c != HOME])
def test_every_listing_card_passes_the_id_rule_against_its_data_alone(tag: Tag, city: str) -> None:
    for cabin in ("economy", "business"):
        out = _listed(tag, destination=city, depart=DEC_17, one_way=True, cabin=cabin)
        assert card_passes(out), out.card
        assert len(out.card.rows) <= 4
        back = _listed(tag, destination="Riyadh", origin=city, depart=DEC_20, one_way=True)
        assert card_passes(back), back.card
        assert len(back.card.rows) <= 4


@pytest.mark.parametrize("tag", TAGS)
def test_every_card_of_every_tool_holds_rows_and_passes_the_id_rule(tag: Tag) -> None:
    call = london(tag)
    city = "لندن" if tag != "en" else "London"
    made: list[ToolResult] = [
        run(compare_cabins(call.airline, call.trips), tag, leg="outbound", choice=FIRST),
        call.choose("outbound", FIRST),
        run(get_trip(call.airline, call.trips), tag),
        call.choose("return", CHEAPEST),
        run(change_trip(call.airline, call.trips), tag, travelers=2),
        run(change_trip(call.airline, call.trips), tag, cabin="business"),
        run(fare_calendar(call.airline), tag, destination=city, month=1),
        run(fare_calendar(call.airline), tag, destination=city, from_date=DEC_17),
    ]
    for result in made:
        card = _card(result)
        assert card.steps == () and 1 <= len(card.rows) <= MAX_ROWS, card
        assert card_passes(result), card
        assert result.evidence == card.texts()
    cabins, back, planned, whole, two, _, month, days = (_card(r) for r in made)
    assert len(cabins.rows) == 3 and len(back.rows) <= 4
    assert [row.mark for row in whole.rows] == ["chosen", "chosen", None, None]
    assert planned.rows[0].mark == "chosen" and len(planned.rows) == 2
    assert len(month.rows) == len(days.rows) == 7
    assert [row.mark for row in days.rows].count("best") == 3
    assert two.rows[2].title != whole.rows[2].title


def test_numbers_joined_only_by_marks_would_fail_the_rule() -> None:
    result = _listed("en", destination="London", depart=DEC_17, one_way=True)
    evidence = (json.dumps(result.data),)
    assert not ids_pass(["T2 401 · 787-9 · 3,560 SAR"], evidence)
    assert ids_pass(["flight T2 401 on a 787-9", "3,560 SAR"], evidence)


def test_a_row_holding_a_number_the_result_lacks_fails_the_rule() -> None:
    result = _listed("en", destination="London", depart=DEC_17, one_way=True)
    evidence = (json.dumps(result.data),)
    assert not ids_pass(["flight T2 999 on a 787-9"], evidence)
    assert not ids_pass(["9,999 SAR"], evidence)


def test_the_airline_code_on_a_card_is_the_airlines() -> None:
    tool = search_flights(Airline(today=lambda: TODAY, code="XQ"), TripBook())
    result = run(tool, "en", destination="London", depart=DEC_17, one_way=True)
    row = _card(result).rows[0]
    assert row.detail is not None and "flight XQ 401 on a 787-9" in row.detail
    assert data(result)["options"][0]["flight"] == "XQ 401" and card_passes(result)

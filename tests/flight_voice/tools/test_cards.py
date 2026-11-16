"""The cards the flight results show: each step's words and digits in the reply's script, and
every card of every route and language passing the output guard's ID rule against its result's
data alone, so no number reaches the page that the result does not hold. The rule reads numbers
joined only by marks as one group, which is why a word always stands between two numbers."""

from __future__ import annotations

import json
from typing import Any

import pytest
from flight_voice.airline.airports import CODES, HOME
from flight_voice.airline.system import Airline
from flight_voice.said import Tag
from flight_voice.tools.search import search_flights
from flight_voice.trip import TripBook

from tests.flight_voice.scenario_dates import TODAY
from tests.flight_voice.tools.tool_support import TAGS, airline, card_passes, data, ids_pass, run

DEC_17: dict[str, Any] = {"kind": "on", "day": 17, "month": 12}
DEC_20: dict[str, Any] = {"kind": "on", "day": 20, "month": 12}


def _listed(tag: Tag, **arguments: Any) -> Any:
    result = run(search_flights(airline(), TripBook()), tag, **arguments)
    assert result.ok and result.card is not None, result.data
    return result


def test_an_english_card_says_each_flight_with_words_between_its_numbers() -> None:
    card = _listed("en", destination="London", depart=DEC_17, return_date=DEC_20).card
    assert card.title == "Riyadh to London, Thu 17 Dec"
    assert card.steps == (
        "09:10 to 13:15, 7 h 5 min, nonstop, flight T2 401 on a 787-9 for 3,560 SAR, lowest fare",
        "14:40 to 18:45, 7 h 5 min, nonstop, flight T2 403 on a 787-9 for 3,780 SAR",
    )


def test_an_arabic_card_writes_its_times_and_fares_in_arabic_indic_digits() -> None:
    card = _listed("ar-SA", destination="لندن", depart=DEC_17, return_date=DEC_20).card
    assert card.title == "الرياض إلى لندن، الخميس ١٧ ديسمبر"
    assert card.steps[0] == (
        "٠٩:١٠ إلى ١٣:١٥، ٧ س ٥ د، مباشرة، رحلة T2 401 على 787-9 بسعر ٣٬٥٦٠ ريال، أقل سعر"
    )


def test_a_flight_landing_the_next_day_says_so() -> None:
    found = {"destination": "Singapore", "depart": DEC_17, "one_way": True}
    english = _listed("en", **found).card.steps[0]
    arabic = _listed("ar", **found).card.steps[0]
    assert english.startswith("22:05 to 11:25 next day, 8 h 20 min,")
    assert "من اليوم التالي" in arabic


@pytest.mark.parametrize("tag", TAGS)
@pytest.mark.parametrize("city", [c for c in CODES if c != HOME])
def test_every_listing_card_passes_the_id_rule_against_its_data_alone(tag: Tag, city: str) -> None:
    for cabin in ("economy", "business"):
        out = _listed(tag, destination=city, depart=DEC_17, one_way=True, cabin=cabin)
        assert card_passes(out), out.card
        back = _listed(tag, destination="Riyadh", origin=city, depart=DEC_20, one_way=True)
        assert card_passes(back), back.card


def test_numbers_joined_only_by_marks_would_fail_the_rule() -> None:
    result = _listed("en", destination="London", depart=DEC_17, one_way=True)
    evidence = (json.dumps(result.data),)
    assert not ids_pass(["T2 401 · 787-9 · 3,560 SAR"], evidence)
    assert ids_pass(["flight T2 401 on a 787-9 for 3,560 SAR"], evidence)


def test_the_airline_code_on_a_card_is_the_airlines() -> None:
    tool = search_flights(Airline(today=lambda: TODAY, code="XQ"), TripBook())
    result = run(tool, "en", destination="London", depart=DEC_17, one_way=True)
    assert result.card is not None and "flight XQ 401 on a 787-9" in result.card.steps[0]
    assert data(result)["options"][0]["flight"] == "XQ 401" and card_passes(result)

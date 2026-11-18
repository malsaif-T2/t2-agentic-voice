"""A span on the real network whose source counted no flights (SerpApi's fare calendar): each
day is given with its price and weekday and no count, never a count of 0, and the days it did
not price inside its run are days with no flight."""

from __future__ import annotations

from datetime import timedelta

from flight_voice.flight_data.model import Money
from flight_voice.flight_data.queries import DayFare, DayFares, SpanQuery

from tests.flight_voice.flight_data.fake import JEDDAH, RIYADH, FakeFlightData
from tests.flight_voice.lean.real_support import OUT, real_call
from tests.flight_voice.tools.tool_support import card_passes, data


def test_a_calendars_days_are_given_without_a_count() -> None:
    first, last = OUT, OUT + timedelta(days=2)
    span = SpanQuery(origin=RIYADH, destination=JEDDAH, first=first, last=last)
    fares = DayFares(
        query=span,
        status="ok",
        days=(
            DayFare(day=first, lowest=Money(amount=429), flights=None),
            DayFare(day=first + timedelta(days=1), flights=None),
            DayFare(day=last, lowest=Money(amount=369), flights=None),
        ),
    )
    found = real_call(FakeFlightData(spans={"RUH-JED": fares})).find(
        destination="Jeddah", depart={"first": first.isoformat(), "last": last.isoformat()}
    )
    answer = data(found)
    assert answer["status"] == "days"
    assert [(d["date"], d["lowest_price"]) for d in answer["days"]] == [
        (first.isoformat(), 429),
        (last.isoformat(), 369),
    ]
    assert all("flights" not in d for d in answer["days"])
    assert [d["date"] for d in answer["no_flight_days"]] == [(first + timedelta(1)).isoformat()]
    assert answer["cheapest_days"] == [last.isoformat(), first.isoformat()]
    assert found.card is not None and card_passes(found)

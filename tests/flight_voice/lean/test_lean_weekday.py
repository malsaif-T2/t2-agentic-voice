"""The weekday a caller said held over the date the model worked out (flight_voice/lean/weekday.py,
find.py): the date moves to that weekday's nearest date, three days at most either way, never
before today for the departure or before the departure for the return; with no weekday said,
the date is searched as it was given."""

from __future__ import annotations

from datetime import date

from flight_voice.lean.weekday import on_weekday

from tests.flight_voice.lean.lean_support import LeanCall
from tests.flight_voice.tools.tool_support import data

SATURDAY = date(2026, 11, 28)


def test_a_weekday_said_moves_its_date_to_the_nearest_one() -> None:
    # The owner's call of 2026-11-18: «نرجع يوم الخميس» after Saturday 28 November was
    # searched as Tuesday 1 December.
    assert on_weekday(date(2026, 12, 1), "thursday", not_before=SATURDAY) == date(2026, 12, 3)
    assert on_weekday(date(2026, 11, 26), "saturday", not_before=SATURDAY) == SATURDAY
    assert on_weekday(SATURDAY, "saturday", not_before=SATURDAY) == SATURDAY
    assert on_weekday(date(2026, 11, 30), "friday", not_before=SATURDAY) == date(2026, 12, 4)
    assert on_weekday(date(2026, 12, 1), None, not_before=SATURDAY) == date(2026, 12, 1)


def test_a_day_moved_before_its_bound_is_the_next_weeks() -> None:
    assert on_weekday(date(2026, 11, 30), "thursday", not_before=SATURDAY) == date(2026, 12, 3)
    assert on_weekday(SATURDAY, "thursday", not_before=SATURDAY) == date(2026, 12, 3)


def test_the_search_holds_the_weekdays_said() -> None:
    call = LeanCall()
    answer = data(
        call.find(
            destination="Jeddah",
            depart="2026-11-27",
            return_date="2026-12-01",
            depart_weekday="saturday",
            return_weekday="thursday",
        )
    )
    assert answer["outbound"]["day"]["date"] == "2026-11-28"
    assert answer["return"]["day"]["date"] == "2026-12-03"
    assert call.draft.depart == SATURDAY and call.draft.return_date == date(2026, 12, 3)
    plain = data(LeanCall().find(destination="Jeddah", depart="2026-11-27"))
    assert plain["outbound"]["day"]["date"] == "2026-11-27"  # no weekday said: as given

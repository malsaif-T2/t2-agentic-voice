"""The dates a caller says, resolved by the code: every form against Monday 2026-11-16, a
Saturday and a month's end; the days that do not exist, have passed or fall past the window, a
return before its departure, a form the schema refuses, and the forms' words that keep a return
said after the departure from being counted from today."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from flight_voice.airline.dates import (
    DateProblem,
    DateSpec,
    InDays,
    Nights,
    OnDay,
    OnWeekday,
    Relative,
    Resolved,
    WeekdayAfter,
    resolve_departure,
    resolve_return,
    riyadh_today,
    week_index,
)
from pydantic import TypeAdapter, ValidationError

MONDAY = date(2026, 11, 16)
SATURDAY = date(2026, 11, 21)
MONTH_END = date(2026, 11, 30)
SPECS: TypeAdapter[DateSpec] = TypeAdapter(DateSpec)


def _day(spec: DateSpec, today: date) -> date:
    resolved = resolve_departure(spec, today)
    assert isinstance(resolved, Resolved), resolved
    return resolved.day


@pytest.mark.parametrize(
    ("spec", "expected"),
    [
        (Relative(when="today"), date(2026, 11, 16)),
        (Relative(when="tomorrow"), date(2026, 11, 17)),
        (Relative(when="day_after_tomorrow"), date(2026, 11, 18)),
        (OnWeekday(weekday="thu"), date(2026, 11, 19)),
        (OnWeekday(weekday="mon"), date(2026, 11, 23)),  # coming is never today
        (OnWeekday(weekday="tue", which="next_week"), date(2026, 11, 24)),
        (OnWeekday(weekday="sun", which="next_week"), date(2026, 11, 22)),
        (OnWeekday(weekday="thu", which="following"), date(2026, 11, 26)),
        (OnDay(day=14), date(2026, 12, 14)),  # the 14th has passed this month
        (OnDay(day=20), date(2026, 11, 20)),
        (OnDay(day=16), date(2026, 11, 16)),
        (OnDay(day=14, month=12), date(2026, 12, 14)),
        (OnDay(day=10, month=1), date(2027, 1, 10)),
        (InDays(days=3), date(2026, 11, 19)),
    ],
)
def test_each_form_on_monday_the_16th(spec: DateSpec, expected: date) -> None:
    assert _day(spec, MONDAY) == expected


def test_the_code_marks_a_month_or_year_it_chose() -> None:
    assert resolve_departure(OnDay(day=14), MONDAY) == Resolved(date(2026, 12, 14), True)
    assert resolve_departure(OnDay(day=20), MONDAY) == Resolved(date(2026, 11, 20), True)
    assert resolve_departure(OnDay(day=14, month=12), MONDAY) == Resolved(date(2026, 12, 14))
    assert resolve_departure(OnDay(day=10, month=1), MONDAY) == Resolved(date(2027, 1, 10), True)
    assert resolve_departure(Relative(when="tomorrow"), MONDAY) == Resolved(date(2026, 11, 17))


@pytest.mark.parametrize(
    ("spec", "expected"),
    [
        (OnWeekday(weekday="sat"), date(2026, 11, 28)),
        (OnWeekday(weekday="sun"), date(2026, 11, 22)),
        (OnWeekday(weekday="tue", which="next_week"), date(2026, 11, 24)),
        (OnWeekday(weekday="sat", which="next_week"), date(2026, 11, 28)),
        (OnWeekday(weekday="thu", which="following"), date(2026, 12, 3)),
        (Relative(when="day_after_tomorrow"), date(2026, 11, 23)),
    ],
)
def test_each_weekday_form_on_a_saturday(spec: DateSpec, expected: date) -> None:
    assert week_index(SATURDAY) == 6
    assert _day(spec, SATURDAY) == expected


@pytest.mark.parametrize(
    ("spec", "today", "expected"),
    [
        (Relative(when="tomorrow"), MONTH_END, date(2026, 12, 1)),
        (OnDay(day=1), MONTH_END, date(2026, 12, 1)),
        (OnDay(day=30), MONTH_END, date(2026, 11, 30)),
        (OnWeekday(weekday="tue", which="next_week"), MONTH_END, date(2026, 12, 8)),
        (OnDay(day=2), date(2026, 12, 31), date(2027, 1, 2)),  # December's end into January
        (InDays(days=2), date(2026, 12, 31), date(2027, 1, 2)),
    ],
)
def test_each_form_at_a_months_end(spec: DateSpec, today: date, expected: date) -> None:
    assert _day(spec, today) == expected


def test_a_day_that_does_not_exist_is_a_problem() -> None:
    last = date(2027, 3, 16)
    assert resolve_departure(OnDay(day=31), MONDAY) == DateProblem("no_such_day", last)
    assert resolve_departure(OnDay(day=31, month=11), MONDAY) == DateProblem("no_such_day", last)
    assert resolve_departure(OnDay(day=30, month=2), MONDAY) == DateProblem("no_such_day", last)


def test_a_day_past_the_window_names_its_last_day() -> None:
    assert resolve_departure(InDays(days=120), MONDAY) == Resolved(date(2027, 3, 16))
    assert resolve_departure(OnDay(day=17, month=3), MONDAY) == DateProblem(
        "beyond_window", date(2027, 3, 16)
    )
    assert resolve_departure(OnDay(day=15, month=11), MONDAY) == DateProblem(
        "beyond_window", date(2027, 3, 16)
    )  # 15 November is a year off, past the window


def test_a_day_before_today_is_a_problem() -> None:
    """No spec names a past day by itself; a return checked against a later today can."""
    early = resolve_return(OnDay(day=17, month=11), date(2026, 11, 17), date(2026, 11, 18))
    assert isinstance(early, DateProblem)
    assert early.problem == "beyond_window"  # 17 November resolved a year on
    later = resolve_return(Nights(nights=1), date(2026, 11, 10), MONDAY)
    assert later == DateProblem("past", date(2027, 3, 16))


@pytest.mark.parametrize(
    ("spec", "expected"),
    [
        (Nights(nights=7), date(2026, 11, 26)),
        (Nights(nights=3), date(2026, 11, 22)),
        (WeekdayAfter(weekday="sun"), date(2026, 11, 22)),
        (WeekdayAfter(weekday="thu"), date(2026, 11, 26)),  # the one after, never the same day
        (OnWeekday(weekday="sun"), date(2026, 11, 22)),
        (OnDay(day=17, month=12), date(2026, 12, 17)),
        (InDays(days=5), date(2026, 11, 21)),
    ],
)
def test_each_return_form_after_a_thursday_departure(spec: DateSpec, expected: date) -> None:
    resolved = resolve_return(spec, date(2026, 11, 19), MONDAY)
    assert isinstance(resolved, Resolved) and resolved.day == expected


@pytest.mark.parametrize(
    ("spec", "expected"),
    [
        (OnDay(day=20), date(2026, 12, 20)),
        (OnDay(day=17), date(2026, 12, 17)),  # back the same day
        (OnDay(day=5), date(2027, 1, 5)),  # the 5th has passed by the departure
        (OnWeekday(weekday="sun"), date(2026, 12, 20)),
        (OnWeekday(weekday="thu"), date(2026, 12, 24)),  # the coming one is never the same day
    ],
)
def test_a_return_without_its_month_counts_from_the_departure(
    spec: DateSpec, expected: date
) -> None:
    """ "December 17th, back on the 20th", «١٧ ديسمبر وأرجع يوم ٢٠»: the return's day of the
    month, or its coming weekday, is the next one from the departure, not from today, and the
    code marks the month it chose."""
    resolved = resolve_return(spec, date(2026, 12, 17), MONDAY)
    assert resolved == Resolved(expected, assumed=True)


def test_a_return_days_after_the_departure_is_nights_never_days_from_today() -> None:
    """f08's «بعد بكرة للدوحة وأرجع بعد ثلاث أيام» is back on the 21st, three nights after the
    18th, not on the 19th: the forms' descriptions, which the talker reads, give that phrase to
    `nights` and keep `in_days` for a departure, with another number than the scenario's (D-011)."""
    nights = Nights.model_json_schema()["description"]
    in_days = InDays.model_json_schema()["description"]
    assert "«أرجع بعد أربع أيام»" in nights and "back four days later" in nights
    assert "«أسافر بعد أربع أيام»" in in_days and "أرجع" not in in_days
    assert "never a return said after the departure" in in_days
    back = resolve_return(Nights(nights=3), date(2026, 11, 18), MONDAY)
    assert back == Resolved(date(2026, 11, 21))


def test_a_return_before_its_departure_is_a_problem() -> None:
    back = resolve_return(Relative(when="tomorrow"), date(2026, 11, 19), MONDAY)
    assert back == DateProblem("return_before_departure", date(2027, 3, 16))
    same = resolve_return(Relative(when="day_after_tomorrow"), date(2026, 11, 18), MONDAY)
    assert same == Resolved(date(2026, 11, 18))


def test_a_return_only_form_cannot_name_a_departure() -> None:
    for spec in (Nights(nights=3), WeekdayAfter(weekday="sun")):
        problem = resolve_departure(spec, MONDAY)
        assert isinstance(problem, DateProblem) and problem.problem == "return_only"


def test_the_schema_takes_only_date_forms() -> None:
    """The talker passes a form, never a date it worked out: a raw date is refused, and so are
    a year, a day out of range and an unknown kind."""
    assert SPECS.validate_python({"kind": "weekday", "weekday": "thu"}) == OnWeekday(weekday="thu")
    for bad in (
        "2026-11-19",
        {"kind": "on", "day": 32},
        {"kind": "on", "day": 3, "month": 12, "year": 2027},
        {"kind": "date", "iso": "2026-11-19"},
        {"kind": "in_days", "days": 0},
        {"kind": "nights", "nights": 61},
    ):
        with pytest.raises(ValidationError):
            SPECS.validate_python(bad)


def test_today_is_riyadhs_date() -> None:
    """Riyadh is three hours ahead of UTC all year: 21:30 UTC is already the next day there."""
    assert riyadh_today(datetime(2026, 11, 15, 21, 30, tzinfo=UTC)) == MONDAY
    assert riyadh_today(datetime(2026, 11, 15, 20, 59, tzinfo=UTC)) == date(2026, 11, 15)

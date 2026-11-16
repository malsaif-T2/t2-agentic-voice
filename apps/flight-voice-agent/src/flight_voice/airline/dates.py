"""The dates a caller says, as the talker passes them (`DateSpec`), resolved against today in
Riyadh: the code picks every day, month and year, so the talker never works a date out.

Riyadh keeps UTC+3 all year, so today there is a fixed offset's date. A spec is one of:
`relative` (today, tomorrow, the day after), `weekday` (the coming one, never today; the one of
next week, the week from the next Sunday, as the Saudi week starts on Sunday; or the one after
the coming one), `on` (a day of the month, this month if not past, else next month; with a
month, its next date on or after today), `in_days`, and two for a return only, `nights` after
the departure and `weekday_after` it. A day that does not exist, a day before today or past the
booking window, a return before its departure, and a return-only form for a departure are each
a `DateProblem`, never a guess. `assumed` marks a date whose month or year the code chose, so
the caller hears it back with its weekday.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Annotated, Final, Literal, get_args

from pydantic import BaseModel, ConfigDict, Field

from flight_voice.airline.schedule import window

RIYADH: Final = timezone(timedelta(hours=3), "+03")
Weekday = Literal["sun", "mon", "tue", "wed", "thu", "fri", "sat"]
WEEKDAYS: Final[tuple[Weekday, ...]] = get_args(Weekday)  # the Saudi week, Sunday first
_DAYS_AHEAD: Final = {"today": 0, "tomorrow": 1, "day_after_tomorrow": 2}


def riyadh_today(now: datetime) -> date:
    """The date in Riyadh at the aware moment `now`."""
    return now.astimezone(RIYADH).date()


def week_index(day: date) -> int:
    """The day's place in the Saudi week: Sunday 0 to Saturday 6."""
    return (day.weekday() + 1) % 7


class _Spec(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Relative(_Spec):
    """Today, tomorrow or the day after tomorrow: «بكرة», «بعد بكرة», "tomorrow"."""

    kind: Literal["relative"] = "relative"
    when: Literal["today", "tomorrow", "day_after_tomorrow"]


class OnWeekday(_Spec):
    """A weekday: `coming` ("next Thursday", «الخميس الجاي»: 1 to 7 days on, never today),
    `next_week` ("Tuesday next week": in the week from the next Sunday) or `following`
    ("Thursday after next": a week after the coming one)."""

    kind: Literal["weekday"] = "weekday"
    weekday: Weekday
    which: Literal["coming", "next_week", "following"] = "coming"


class OnDay(_Spec):
    """A day of the month ("the 14th", «يوم ١٤»), with its month when the caller said one."""

    kind: Literal["on"] = "on"
    day: int = Field(ge=1, le=31)
    month: int | None = Field(default=None, ge=1, le=12)


class InDays(_Spec):
    """A number of days from today: "in three days", «بعد ثلاث أيام»."""

    kind: Literal["in_days"] = "in_days"
    days: int = Field(ge=1, le=120)


class Nights(_Spec):
    """A return a number of nights after the departure: "a week later", «أرجع بعد أسبوع»."""

    kind: Literal["nights"] = "nights"
    nights: int = Field(ge=1, le=60)


class WeekdayAfter(_Spec):
    """A return on the first such weekday after the departure: «الأحد اللي بعده»."""

    kind: Literal["weekday_after"] = "weekday_after"
    weekday: Weekday


DateSpec = Annotated[
    Relative | OnWeekday | OnDay | InDays | Nights | WeekdayAfter, Field(discriminator="kind")
]
DepartSpec = Annotated[Relative | OnWeekday | OnDay | InDays, Field(discriminator="kind")]

Problem = Literal["past", "beyond_window", "no_such_day", "return_before_departure", "return_only"]


@dataclass(frozen=True)
class Resolved:
    """A resolved date, and whether the code chose its month or its year."""

    day: date
    assumed: bool = False


@dataclass(frozen=True)
class DateProblem:
    """Why a date could not be used, with the window's last day for the caller to hear."""

    problem: Problem
    last_day: date


def resolve_departure(spec: DateSpec, today: date) -> Resolved | DateProblem:
    """The departure date `spec` names, today being `today`."""
    if isinstance(spec, Nights | WeekdayAfter):
        return DateProblem("return_only", window(today)[1])
    return _checked(_resolve(spec, today), today)


def resolve_return(spec: DateSpec, departure: date, today: date) -> Resolved | DateProblem:
    """The return date `spec` names, after a departure on `departure`, today being `today`."""
    if isinstance(spec, Nights):
        resolved: Resolved | None = Resolved(departure + timedelta(days=spec.nights))
    elif isinstance(spec, WeekdayAfter):
        ahead = (WEEKDAYS.index(spec.weekday) - week_index(departure) - 1) % 7 + 1
        resolved = Resolved(departure + timedelta(days=ahead))
    else:
        resolved = _resolve(spec, today)
    checked = _checked(resolved, today)
    if isinstance(checked, Resolved) and checked.day < departure:
        return DateProblem("return_before_departure", window(today)[1])
    return checked


def _checked(resolved: Resolved | None, today: date) -> Resolved | DateProblem:
    first, last = window(today)
    if resolved is None:
        return DateProblem("no_such_day", last)
    if resolved.day < first:
        return DateProblem("past", last)
    if resolved.day > last:
        return DateProblem("beyond_window", last)
    return resolved


def _resolve(spec: Relative | OnWeekday | OnDay | InDays, today: date) -> Resolved | None:
    """The date `spec` names, or `None` for a day that does not exist."""
    if isinstance(spec, Relative):
        return Resolved(today + timedelta(days=_DAYS_AHEAD[spec.when]))
    if isinstance(spec, InDays):
        return Resolved(today + timedelta(days=spec.days))
    if isinstance(spec, OnWeekday):
        return Resolved(_weekday(spec, today))
    return _on(spec, today)


def _weekday(spec: OnWeekday, today: date) -> date:
    target = WEEKDAYS.index(spec.weekday)
    if spec.which == "next_week":
        sunday = today + timedelta(days=7 - week_index(today))
        return sunday + timedelta(days=target)
    coming = today + timedelta(days=(target - week_index(today) - 1) % 7 + 1)
    return coming + timedelta(days=7) if spec.which == "following" else coming


def _on(spec: OnDay, today: date) -> Resolved | None:
    if spec.month is None:
        month, year = today.month, today.year
        if spec.day < today.day:
            month, year = (1, year + 1) if month == 12 else (month + 1, year)
        found = _date(year, month, spec.day)
        return None if found is None else Resolved(found, assumed=True)
    year = today.year
    if (spec.month, spec.day) < (today.month, today.day):
        year += 1
    found = _date(year, spec.month, spec.day)
    return None if found is None else Resolved(found, assumed=year != today.year)


def _date(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None

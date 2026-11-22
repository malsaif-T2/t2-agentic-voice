"""The weekday a caller said, held over the date the model worked out for it.

The model copies a weekday it heard well and counts dates less well: in the owner's call of
2026-11-18, «نرجع يوم الخميس» after Saturday 28 November was searched as Tuesday 1 December. So
`find_flights` takes the weekday the caller said beside each date, and the date moves to that
weekday's nearest date, three days at most either way; a day moved before the one it must not
precede (today for the departure, the departure for the return) is the next week's.

On the real network a way back said by its weekday alone needs no date (`next_weekday`): in
the replays of 2026-11-22, «والرجعة السبت» after «بكرة» was searched as Wednesday the 25th in
10 of 12 tries, the model never passing the weekday, so the parameters ask for the weekday
plainly (`SAID_OUT`, `SAID_BACK`) and its date is worked out here: the first after the day
out.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Final, Literal

Weekday = Literal["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
# In `date.weekday()`'s order, Monday 0.
WEEKDAYS: Final[tuple[Weekday, ...]] = (
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
)
SAID: Final = "The weekday the caller said for that day, only when they said one."
# The real network's: the weekday asked for whenever one is named, the way back's enough alone.
SAID_OUT: Final = (
    "The weekday the caller named for the day out (Thursday, «الخميس»), beside depart: the "
    "tool moves depart to it."
)
SAID_BACK: Final = (
    "The weekday the caller named for the way back (Saturday, «السبت»): enough alone, the "
    "tool works out its date, the first after the day out."
)


def on_weekday(day: date, said: Weekday | None, *, not_before: date) -> date:
    """`day` moved to the date of the weekday `said` nearest it, never before `not_before`
    (the module's docstring); `day` itself when no weekday was said."""
    if said is None:
        return day
    shift = (WEEKDAYS.index(said) - day.weekday() + 3) % 7 - 3
    moved = day + timedelta(days=shift)
    return moved + timedelta(days=7) if moved < not_before else moved


def next_weekday(said: Weekday, *, after: date) -> date:
    """The first date of the weekday `said` after `after`: a way back said by its weekday alone
    (the module's docstring)."""
    return after + timedelta(days=(WEEKDAYS.index(said) - after.weekday()) % 7 or 7)

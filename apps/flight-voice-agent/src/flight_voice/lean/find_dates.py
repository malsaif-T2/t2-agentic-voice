"""The dates `find_flights` refuses, and how: a day before today, a day past the last the source
sells (`last_day`), a return before its departure, and a span too long or the wrong way round
are a `date_problem` naming the first and last days, with a short note. The note on a day too
far ahead is the network's: the mock's booking window, or the airlines not showing that day
yet."""

from __future__ import annotations

from datetime import date
from typing import Final, Literal

from pydantic import JsonValue
from t2_agentic_voice import ToolResult

from flight_voice.lean.results import Network, lean_result
from flight_voice.lean.span import MOST_DAYS, DaySpan

__all__ = ["NOTES", "Problem", "date_problem", "refused"]

Problem = Literal["past", "beyond_window", "return_before_departure", "span_too_long"]
NOTES: Final[dict[Problem, str]] = {
    "past": "That day has passed.",
    "beyond_window": "Bookings are open only up to last_day.",
    "return_before_departure": (
        "The day back comes before the day out: a return must be on or after the departure."
    ),
    "span_too_long": f"A span is {MOST_DAYS} days at most, its first day before its last.",
}
TOO_FAR_REAL: Final = "The airlines do not show flights that far ahead yet; ask for an earlier day."


def date_problem(problem: Problem, today: date, last: date, network: Network) -> ToolResult:
    """A date refused: why, the first and last days, and a short note (the module's
    docstring)."""
    note = TOO_FAR_REAL if problem == "beyond_window" and network == "real" else NOTES[problem]
    answer: dict[str, JsonValue] = {"status": "date_problem", "problem": problem}
    answer |= {"first_day": today.isoformat(), "last_day": last.isoformat()}
    return lean_result(answer | {"note": note})


def refused(depart: date | DaySpan, back: date | None, today: date, last: date) -> Problem | None:
    """Why the dates are refused between `today` and `last`, or None."""
    start, end = (depart.first, depart.last) if isinstance(depart, DaySpan) else (depart, depart)
    if isinstance(depart, DaySpan) and not 0 <= (end - start).days < MOST_DAYS:
        return "span_too_long"
    if end < today:
        return "past"
    if start > last or (back is not None and back > last):
        return "beyond_window"
    if back is not None and back < start:
        return "return_before_departure"
    return None

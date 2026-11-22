"""What `find_flights`' parameters tell the model (find.py), and the mock's schema as run F
reads it (`as_run_f`): before plan 011's round 2, with none of the real network's own
parameters (`REAL_ONLY`: `flights_per_day`, a span's flights day by day, and `one_way`, the
trip made one way while a round trip's way back otherwise follows its way out). The function's
defaults, false, hold there, so the mock's search is as it was.
"""

from __future__ import annotations

from copy import copy
from typing import Any, Final

from pydantic import create_model
from pydantic.fields import FieldInfo
from t2_agentic_voice import Tool

from flight_voice.lean.weekday import SAID

__all__ = [
    "AIRLINE",
    "CABIN",
    "CITY",
    "DEPART",
    "ONE_WAY",
    "ORIGIN",
    "PER_DAY",
    "REAL_ONLY",
    "RETURN",
    "RETURN_REAL",
    "TRAVELERS",
    "as_run_f",
]

CITY: Final = "The city they go to, in any language, or its code."
ORIGIN: Final = "The city they leave from; Riyadh unless they said another."
DEPART: Final = (
    "The day they leave, YYYY-MM-DD, from the calendar; or a span of at most two months they "
    "asked about without naming one day."
)
RETURN: Final = "The day they come back, YYYY-MM-DD; null for one way or not said yet."
# The real network's: a weekday passed as one (find.py, weekday.py's `SAID_BACK`).
RETURN_REAL: Final = (
    "The day they come back, YYYY-MM-DD, for a date they said or a day like tomorrow; for a "
    "weekday, pass return_weekday instead. Null for one way or not said yet."
)
CABIN: Final = "economy, business or first; the trip's own (economy at first) when not said."
TRAVELERS: Final = "How many travel, 1 to 9; the trip's own (1 at first) when not said."
AIRLINE: Final = (
    "An airline the caller asked for, by its name in any language or its code; null for every "
    "airline."
)
PER_DAY: Final = (
    "For a span only: true when the caller asks about the days' flights beyond each day's "
    "cheapest price (the priciest, a time of day, an airline, nonstop only); each day is then "
    "searched, which takes longer."
)
ONE_WAY: Final = (
    "True only when the caller wants no way back at all, the whole trip one way; a search for "
    "the way back itself is never one way."
)
# The real network's parameters, left out of the mock's schema (run F reads it as before).
REAL_ONLY: Final = ("flights_per_day", "one_way")


def as_run_f(made: Tool) -> Tool:
    """The mock's search as run F reads it (the module's docstring): `made` with no `REAL_ONLY`
    parameter in its schema."""
    fields = made.parameters.model_fields
    kept: dict[str, Any] = {
        n: (f.annotation, _as_before(n, f)) for n, f in fields.items() if n not in REAL_ONLY
    }
    config = made.parameters.model_config
    narrowed = create_model("Arguments", __config__=config, **kept)
    return made.model_copy(update={"parameters": narrowed})


def _as_before(name: str, field: FieldInfo) -> FieldInfo:
    """`field` with the description run F's schema had: the weekdays' and the return day's are
    the real network's own (weekday.py's `SAID_OUT`, `SAID_BACK`; `RETURN_REAL`)."""
    before = {"depart_weekday": SAID, "return_weekday": SAID, "return_date": RETURN}.get(name)
    if before is None:
        return field
    again = copy(field)
    again.description = before
    return again

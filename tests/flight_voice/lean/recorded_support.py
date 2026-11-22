"""A lean call on the real network over the app's recorded SerpApi answers
(apps/flight-voice-agent/evals/flight_data/, replayed offline: RUH-JED and JED-RUH on
2026-11-26, JED-RUH on the 29th, RUH-DXB on the 26th and DXB-RUH on the 29th ...) and the real
directory, as the round trip's tests play the owner's calls of 2026-11-22."""

from __future__ import annotations

from typing import Any, Final

from flight_voice.flight_data.compose import real_places
from flight_voice.flight_data.recorded import recorded
from flight_voice.lean.booking_check import BookingCheck
from flight_voice.lean.deps import LeanDeps
from flight_voice.lean.draft import LeanBook
from flight_voice.said import Tag

from tests.flight_voice.lean.lean_support import LeanCall
from tests.flight_voice.tools.tool_support import airline

DAY_OUT: Final = "2026-11-26"
DAY_BACK: Final = "2026-11-29"
# Riyadh to Jeddah on the 26th, as listed: Saudia at 17:00 lands 18:55; flynas at 09:35 lands
# 11:35; Saudia at 23:00 lands 00:55 the next day.
EVENING: Final = "SV1041-2026-11-26"
MORNING: Final = "XY17-2026-11-26"
LATE: Final = "SV1053-2026-11-26"
# Jeddah to Riyadh on the 26th: flynas at 00:25, listed; flyadeal at 21:20.
NIGHT_BACK: Final = "XY54-2026-11-26"
LATE_BACK: Final = "F3140-2026-11-26"


def recorded_call(tag: Tag = "en") -> LeanCall:
    """A call on the real network over the recorded answers (the module's docstring)."""
    places = real_places()
    deps = LeanDeps(
        data=recorded(),
        places=places,
        today=airline().today,
        airline=airline(),
        trips=LeanBook(places.home),
        check=BookingCheck(),
        bookable=False,
        network="real",
    )
    return LeanCall(tag, deps=deps)


def option_ids(leg: dict[str, Any]) -> list[str]:
    """The ids of a leg's options, as listed."""
    return [o["id"] for o in leg["options"]]


__all__ = [
    "DAY_BACK",
    "DAY_OUT",
    "EVENING",
    "LATE",
    "LATE_BACK",
    "MORNING",
    "NIGHT_BACK",
    "option_ids",
    "recorded_call",
]

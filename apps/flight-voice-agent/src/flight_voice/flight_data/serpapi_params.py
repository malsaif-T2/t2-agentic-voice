"""The params the SerpApi adapter sends, the key aside: a day's search (`search_params`) and a
span's fare calendar (`calendar_params`), both one way (`type=2`) between the places' airports
(comma-joined), in the cabin, for the travelers, in SAR, on Saudi Google in English.

A day keeps to one stop or fewer (`stops=2`) and asks for SerpApi's `deep_search` only when
set; the calendar (`engine=google_flights_calendar`) takes the span's first and last days as its
range, and no stops filter, as Phase 0 asked it (2026-11-18).
"""

from __future__ import annotations

from typing import Final

from flight_voice.flight_data.queries import OfferQuery, SpanQuery

__all__ = ["CALENDAR_ENGINE", "calendar_params", "search_params"]

CALENDAR_ENGINE: Final = "google_flights_calendar"
_CLASSES: Final = {"economy": "1", "business": "3", "first": "4"}


def search_params(q: OfferQuery, *, deep_search: bool = False) -> dict[str, str]:
    """A day's parameters as the adapter sends them, the key aside."""
    params = {
        "engine": "google_flights",
        "type": "2",
        "departure_id": ",".join(q.origin.airports),
        "arrival_id": ",".join(q.destination.airports),
        "outbound_date": q.day.isoformat(),
        "travel_class": _CLASSES[q.cabin],
        "adults": str(q.adults),
        "currency": "SAR",
        "gl": "sa",
        "hl": "en",
        "stops": "2",
    }
    if deep_search:
        params["deep_search"] = "true"
    return params


def calendar_params(q: SpanQuery) -> dict[str, str]:
    """A span's fare calendar's parameters as the adapter sends them, the key aside."""
    return {
        "engine": CALENDAR_ENGINE,
        "type": "2",
        "departure_id": ",".join(q.origin.airports),
        "arrival_id": ",".join(q.destination.airports),
        "date_range_start": q.first.isoformat(),
        "date_range_end": q.last.isoformat(),
        "travel_class": _CLASSES[q.cabin],
        "adults": str(q.adults),
        "currency": "SAR",
        "gl": "sa",
        "hl": "en",
    }

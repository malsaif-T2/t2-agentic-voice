"""The lean agent's deps from the app's settings (`lean_deps`), and the real network's parts
they are built from: the flight data source (`real_data`), the places (`real_places`), the
speech-to-text terms (`REAL_TERMS`) and how the Saudi carriers' codes are said
(`real_pronounce`).

`lean_deps` gives the mock airline's own deps for `mock` (lean/deps.py's `mock_deps`), and for
`recorded` or `serpapi` the real network's: its source, its places, a trip book from Riyadh, a
booking check, `bookable` false (no `book_trip`), its terms and its codes said. The mock airline
is kept on both, for the traveler's profile.

- `recorded`: the SerpApi adapter over a replay of `flight_data_fixtures` (the app's own
  folder, recorded.py's `APP_FIXTURES`, when unset), with no cache: a replay is instant.
- `serpapi`: the live adapter behind the cache (`flight_data_cache_s`; 0 keeps none), recording
  each answer into `flight_data_record_to` when it is set.

`real_data` never builds the mock: the lean agent's mock deps are its own.

**The Whisper bytes.** A call's Whisper prompt is the vocabulary's terms first, then the stop,
wait and repeat words, cut to 224 bytes of UTF-8 (the library's `whisper_prompt`). So the real
network's terms replace the mock's (persona.py's `TERMS`) within about the same bytes, and every
command word stays in the prompt.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import Final

from flight_voice.airline.system import Airline
from flight_voice.flight_data.cache import CachedFlightData
from flight_voice.flight_data.carriers import pronounced
from flight_voice.flight_data.places import Directory
from flight_voice.flight_data.port import FlightData
from flight_voice.flight_data.recorded import APP_FIXTURES, RecordingTransport, recorded
from flight_voice.flight_data.serpapi import SerpApiFlightData
from flight_voice.flight_data.settings import FlightDataFields
from flight_voice.lean.booking_check import BookingCheck
from flight_voice.lean.deps import LeanDeps, mock_deps
from flight_voice.lean.draft import LeanBook
from flight_voice.persona import Names

__all__ = ["REAL_TERMS", "lean_deps", "real_data", "real_places", "real_pronounce"]

REAL_TERMS: Final = (
    "Riyadh",
    "Jeddah",
    "Dammam",
    "Dubai",
    "Cairo",
    "London",
    "Saudia",
    "flynas",
    "flyadeal",
    "Riyadh Air",
    "economy",
    "business",
)


def real_data(app: FlightDataFields) -> FlightData:
    """The real network's flight data for `app`'s `flight_data` (recorded or serpapi), as the
    module's docstring says; ValueError for the mock, which is not built here, and for serpapi
    with no key (settings.py's `load` refuses both before)."""
    adapter = {
        "deadline_s": app.flight_data_deadline_s,
        "span_days": app.flight_data_span_days,
        "span_concurrency": app.flight_data_span_concurrency,
        "span_deadline_s": app.flight_data_span_deadline_s,
        "deep_search": app.serpapi_deep_search,
    }
    if app.flight_data == "recorded":
        return recorded(app.flight_data_fixtures or APP_FIXTURES, **adapter)
    if app.flight_data != "serpapi":
        raise ValueError("the mock's flight data is the lean agent's mock deps")
    if app.serpapi_key is None:
        raise ValueError("serpapi needs its key")
    folder = app.flight_data_record_to
    live = SerpApiFlightData(
        app.serpapi_key,
        transport=RecordingTransport(folder) if folder is not None else None,
        deadline_s=app.flight_data_deadline_s,
        span_days=app.flight_data_span_days,
        span_concurrency=app.flight_data_span_concurrency,
        span_deadline_s=app.flight_data_span_deadline_s,
        deep_search=app.serpapi_deep_search,
    )
    if app.flight_data_cache_s == 0:
        return live
    return CachedFlightData(live, ttl_s=app.flight_data_cache_s)


def lean_deps(
    app: FlightDataFields, airline: Airline, names: Names, *, today: Callable[[], date]
) -> LeanDeps:
    """The lean tools' deps for `app`'s `flight_data`, as the module's docstring says, `today`
    their day."""
    if app.flight_data == "mock":
        return mock_deps(airline, names, today=today)
    places = real_places()
    return LeanDeps(
        data=real_data(app),
        places=places,
        today=today,
        airline=airline,
        trips=LeanBook(places.home),
        check=BookingCheck(),
        bookable=False,
        network="real",
        pronounce=real_pronounce(),
        terms=REAL_TERMS,
    )


def real_places() -> Directory:
    """The real network's places."""
    return Directory()


def real_pronounce() -> dict[str, dict[str, str]]:
    """How the four Saudi carriers' codes are said."""
    return pronounced()

"""The real network's parts, built from the app's settings: the flight data source
(`real_data`), the places (`real_places`), the speech-to-text terms (`REAL_TERMS`) and how the
Saudi carriers' codes are said (`real_pronounce`).

- `recorded`: the SerpApi adapter over a replay of `flight_data_fixtures` (the app's own
  folder, recorded.py's `APP_FIXTURES`, when unset), with no cache: a replay is instant.
- `serpapi`: the live adapter behind the cache (`flight_data_cache_s`; 0 keeps none), recording
  each answer into `flight_data_record_to` when it is set.

The mock is not built here: the lean agent's mock deps are its own (block A's `mock_deps`), and
`lean_deps`, which picks between them, joins this module once block A is merged (plan 011's B3).

**The Whisper bytes.** A call's Whisper prompt is the vocabulary's terms first, then the stop,
wait and repeat words, cut to 224 bytes of UTF-8 (the library's `whisper_prompt`). So the real
network's terms replace the mock's (persona.py's `TERMS`) within about the same bytes, and every
command word stays in the prompt.
"""

from __future__ import annotations

from typing import Final

from flight_voice.flight_data.cache import CachedFlightData
from flight_voice.flight_data.carriers import pronounced
from flight_voice.flight_data.places import Directory
from flight_voice.flight_data.port import FlightData
from flight_voice.flight_data.recorded import APP_FIXTURES, RecordingTransport, recorded
from flight_voice.flight_data.serpapi import SerpApiFlightData
from flight_voice.flight_data.settings import FlightDataFields

__all__ = ["REAL_TERMS", "real_data", "real_places", "real_pronounce"]

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


def real_places() -> Directory:
    """The real network's places."""
    return Directory()


def real_pronounce() -> dict[str, dict[str, str]]:
    """How the four Saudi carriers' codes are said."""
    return pronounced()

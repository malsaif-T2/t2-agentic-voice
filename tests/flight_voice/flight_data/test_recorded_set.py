"""The app's own recorded set (apps/flight-voice-agent/evals/flight_data/, SerpApi's answers of
2026-11-18 recorded through the app's settings): a call's query, the cities as the model names
them, replays offline from it, a day and a span's calendar alike, and no file holds a key's
parameter."""

from __future__ import annotations

import asyncio
from datetime import date

from flight_voice.flight_data.places import Directory
from flight_voice.flight_data.queries import DayFares, DayOffers, OfferQuery, SpanQuery
from flight_voice.flight_data.recorded import APP_FIXTURES, recorded

PLACES = Directory()


def test_a_day_and_a_calendar_replay_from_the_apps_folder() -> None:
    start, end = PLACES.find("Riyadh"), PLACES.find("Dubai")
    jeddah = PLACES.find("Jeddah")
    assert start is not None and end is not None and jeddah is not None
    source = recorded()

    async def scene() -> tuple[DayOffers, DayFares]:
        try:
            day = await source.day(
                OfferQuery(origin=start, destination=end, day=date(2026, 11, 26))
            )
            span = SpanQuery(
                origin=start, destination=jeddah, first=date(2026, 11, 19), last=date(2027, 1, 15)
            )
            return day, await source.days(span)
        finally:
            await source.aclose()

    day, fares = asyncio.run(scene())
    assert day.status == "ok" and len(day.offers) >= 5
    assert {"SV", "XY", "F3"} <= {o.carrier.code for o in day.offers}
    assert len(fares.days) == 58 and all(d.lowest is not None for d in fares.days)


def test_no_recorded_file_holds_a_key() -> None:
    files = sorted(APP_FIXTURES.glob("*.json"))
    assert len(files) >= 13
    assert [f.name for f in files if "api_key" in f.read_text(encoding="utf-8")] == []

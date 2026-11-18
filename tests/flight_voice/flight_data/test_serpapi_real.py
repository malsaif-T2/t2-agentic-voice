"""SerpApi's parser (serpapi_parse.py) over the real answers of Phase 0 (2026-11-18, for
2026-11-26; tests/flight_voice/flight_data/fixtures/, each in the envelope with the params the
adapter sends): RUH-JED's 22 nonstops of Saudia, flyadeal and flynas from 429; RUH-LHR's Riyadh
Air RX 401 nonstop beside a Qatar and British Airways connection; JED-DXB's flydubai, Emirates
and AJet (flown by Turkish) with connections; RUH-DMM's connections and its one nonstop; and two
travelers' prices, each the party's (twice one's, the cheapest exactly, or more where a fare
had one seat left)."""

from __future__ import annotations

import json
from collections import Counter
from datetime import date, datetime
from pathlib import Path
from typing import Final

import pytest
from flight_voice.flight_data.queries import DayOffers, OfferQuery
from flight_voice.flight_data.serpapi import search_params
from flight_voice.flight_data.serpapi_parse import read_day

from tests.flight_voice.flight_data.serpapi_support import FIXTURES, KEY, NOW, PLACES, content

DAY: Final = date(2026, 11, 26)
ROUTES: Final = (
    ("RUH", "JED", 1),
    ("RUH", "JED", 2),
    ("RUH", "LHR", 1),
    ("JED", "DXB", 1),
    ("RUH", "DMM", 1),
)


def _path(origin: str, destination: str, adults: int) -> Path:
    return FIXTURES / f"{origin}_{destination}_{DAY.isoformat()}_c1_a{adults}.json"


def _query(origin: str, destination: str, adults: int = 1) -> OfferQuery:
    start, end = PLACES.find(origin), PLACES.find(destination)
    assert start is not None and end is not None
    return OfferQuery(origin=start, destination=end, day=DAY, adults=adults)


def _read(origin: str, destination: str, adults: int = 1) -> DayOffers:
    held = json.loads(_path(origin, destination, adults).read_text(encoding="utf-8"))
    q = _query(origin, destination, adults)
    return read_day(content(held["body"]), q, NOW).answer


@pytest.mark.parametrize(("origin", "destination", "adults"), ROUTES)
def test_each_fixture_holds_the_adapters_params_and_no_key(
    origin: str, destination: str, adults: int
) -> None:
    path = _path(origin, destination, adults)
    assert json.loads(path.read_text(encoding="utf-8"))["params"] == search_params(
        _query(origin, destination, adults)
    )
    assert KEY not in path.read_text(encoding="utf-8")


def test_riyadh_to_jeddah_is_22_nonstops_of_three_saudi_airlines_from_429() -> None:
    day = _read("RUH", "JED")
    assert day.status == "ok" and len(day.offers) == 22 and all(o.nonstop for o in day.offers)
    assert Counter(o.carrier.name_en for o in day.offers) == {
        "Saudia": 11,
        "flyadeal": 6,
        "flynas": 5,
    }
    cheapest = min(day.offers, key=lambda o: o.price.amount)
    assert (cheapest.id, cheapest.price.amount, cheapest.flights) == (
        "XY17-2026-11-26",
        429,
        ("XY 17",),
    )
    assert dict(day.cities) == {"RUH": "Riyadh", "JED": "Jeddah"}
    departs = [o.departs for o in day.offers]
    assert departs == sorted(departs)


def test_riyadh_to_london_has_riyadh_air_nonstop_and_a_qatar_british_connection() -> None:
    day = _read("RUH", "LHR")
    by_id = {o.id: o for o in day.offers}
    rx = by_id["RX401-2026-11-26"]
    assert rx.nonstop and rx.carrier.name_en == "Riyadh Air" and rx.price.amount == 2078
    assert rx.departs == datetime(2026, 11, 26, 3, 25)
    mixed = by_id["QR1173+BA126-2026-11-26"]
    assert mixed.stops == 1 and [c.code for c in mixed.carriers] == ["QR", "BA"]
    assert mixed.layovers[0].airport == "DOH" and mixed.price.amount == 1425
    assert {o.id for o in day.offers if o.nonstop} == {"RX401-2026-11-26", "SV111-2026-11-26"}
    assert len(day.offers) == 8


def test_jeddah_to_dubai_has_flydubai_emirates_ajet_and_connections() -> None:
    day = _read("JED", "DXB")
    carriers = Counter(o.carrier.code for o in day.offers)
    assert carriers == {"SV": 8, "FZ": 3, "XY": 2, "EK": 2, "VF": 1}
    ajet = next(o for o in day.offers if o.carrier.code == "VF")
    assert ajet.stops == 1 and ajet.layovers[0].airport == "ESB"
    assert {s.operated_by.code for s in ajet.segments if s.operated_by} == {"TK"}
    connections = {o.layovers[0].airport for o in day.offers if not o.nonstop}
    assert connections == {"ESB", "ELQ", "MED"}


def test_riyadh_to_dammam_is_mostly_connections() -> None:
    day = _read("RUH", "DMM")
    nonstops = [o.id for o in day.offers if o.nonstop]
    assert nonstops == ["SV1162-2026-11-26"] and len(day.offers) == 8
    via = {w.airport for o in day.offers for w in o.layovers}
    assert via == {"JED", "MED", "DOH", "AMM"}


def test_two_travelers_prices_are_the_partys() -> None:
    one = {o.id: o.price.amount for o in _read("RUH", "JED").offers}
    two = {o.id: o.price.amount for o in _read("RUH", "JED", 2).offers}
    assert one.keys() == two.keys()
    # Never less than twice one's (Google rounds each fare), and more when the cheaper fare has
    # one seat left (SV 1053: 927, then 2047 for two).
    assert all(two[k] >= 2 * one[k] - 2 for k in one)
    assert sum(abs(two[k] - 2 * one[k]) <= 2 for k in one) >= 18
    assert min(two.values()) == 2 * min(one.values()) == 858
    assert all(o.adults == 2 for o in _read("RUH", "JED", 2).offers)

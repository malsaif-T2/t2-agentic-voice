"""The page's own routes (flight_voice/routes.py): the profile the page shows, for any client; the
traveler's bookings and the demo's reset on this machine alone (404 for any other client); the
reset taking JSON alone, an empty object at most 64 bytes, so a cross-site form cannot post it;
and no request naming another traveler."""

from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi.testclient import TestClient
from flight_voice.airline.bookings import SEED, Leg, NewBooking, priced
from flight_voice.airline.schedule import departures
from flight_voice.airline.system import Airline

from tests.flight_voice.scenario_dates import TODAY
from tests.flight_voice.server_support import ELSEWHERE, LOCAL, LOOPBACK, app

JSON = {"content-type": "application/json"}


def _client(
    folder: Path, airline: Airline | None = None, *, where: tuple[str, int] = LOOPBACK
) -> TestClient:
    return TestClient(app(folder, airline=airline), client=where, base_url=LOCAL)


def _book(airline: Airline) -> str:
    out = departures("RUH", "DXB", TODAY)[0]
    leg = Leg(flight=out.flight.number, day=TODAY)
    new = NewBooking(
        request_id="r-1",
        traveler_id="T-0001",
        legs=(leg,),
        cabin="economy",
        travelers=1,
        total_sar=priced((leg,), "economy", 1, TODAY),
    )
    return asyncio.run(airline.bookings.create(new)).reference


def test_the_profile_gives_the_traveler_the_persona_and_three_lines(tmp_path: Path) -> None:
    for where in (LOOPBACK, ELSEWHERE):
        answer = _client(tmp_path, where=where).get("/api/profile")
        assert answer.status_code == 200
        assert answer.headers["cache-control"] == "no-store"
    shown = answer.json()
    assert shown["first_name"] == {"ar": "خالد", "en": "Khalid"}
    assert shown["tier"] == {"ar": "ذهبي", "en": "Gold"}
    assert shown["persona"] == {"ar": "سعد", "en": "Saad"}
    assert shown["airline"] == {"ar": "طيران تي تو", "en": "T2 Air"}
    assert shown["lines"]["en"] == ["Back to Dubai", "Cheapest days to London", "Business to Paris"]
    assert shown["lines"]["ar"] == ["ودي أرجع لدبي", "أرخص الأيام للندن", "بزنس لباريس"]


def test_the_bookings_are_listed_newest_first_on_this_machine(tmp_path: Path) -> None:
    airline = Airline(today=lambda: TODAY)
    made = _book(airline)
    listed = _client(tmp_path, airline).get("/api/bookings").json()["bookings"]
    assert [b["reference"] for b in listed][:2] == [made, SEED[0].reference]
    assert len(listed) == len(SEED) + 1
    first = listed[0]
    assert first["to"] == {"ar": "دبي", "en": "Dubai"}
    assert first["return_date"] is None and first["flown"] is False
    assert set(first) == {
        "reference",
        "from",
        "to",
        "depart",
        "return_date",
        "travelers",
        "cabin",
        "total_sar",
        "flown",
    }


def test_another_machine_sees_no_bookings_and_cannot_reset(tmp_path: Path) -> None:
    airline = Airline(today=lambda: TODAY)
    _book(airline)
    client = _client(tmp_path, airline, where=ELSEWHERE)
    assert client.get("/api/bookings").status_code == 404
    assert client.post("/api/demo/reset", content=b"{}", headers=JSON).status_code == 404
    assert len(airline.bookings.listed("T-0001")) == len(SEED) + 1


def test_the_reset_puts_the_bookings_back_to_the_seed(tmp_path: Path) -> None:
    airline = Airline(today=lambda: TODAY)
    _book(airline)
    answer = _client(tmp_path, airline).post("/api/demo/reset", content=b"{}", headers=JSON)
    assert answer.status_code == 200
    assert answer.json() == {"reset": True}
    assert len(airline.bookings.listed("T-0001")) == len(SEED)


def test_the_reset_takes_an_empty_json_object_alone(tmp_path: Path) -> None:
    airline = Airline(today=lambda: TODAY)
    _book(airline)
    client = _client(tmp_path, airline)
    form = {"content-type": "application/x-www-form-urlencoded"}
    for body, headers, status in (
        (b"{}", form, 415),
        (b"{}", {"content-type": "text/plain"}, 415),
        (b"{}", {}, 415),
        (b'{"traveler_id": "T-0002"}', JSON, 400),
        (b"[]", JSON, 400),
        (b"not json", JSON, 400),
        (b'{"pad": "' + b"x" * 64 + b'"}', JSON, 413),
    ):
        answer = client.post("/api/demo/reset", content=body, headers=headers)
        assert answer.status_code == status, body
    assert len(airline.bookings.listed("T-0001")) == len(SEED) + 1


def test_a_get_cannot_reset(tmp_path: Path) -> None:
    assert _client(tmp_path).get("/api/demo/reset").status_code == 405

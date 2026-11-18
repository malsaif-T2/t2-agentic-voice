"""SerpApi's answers recorded and replayed at the wire (flight_data/recorded.py): a replay of
the seeded fixture through the real adapter and parser, a search no fixture holds as
`not_recorded`, a missing folder, a fixture's params matched whole (the round trip's never
answers a one-way search), and a recording written without the key, or refused when its text
would hold it."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx
import pytest
from flight_voice.flight_data.port import FlightDataUnavailableError
from flight_voice.flight_data.queries import DayOffers, OfferQuery
from flight_voice.flight_data.recorded import (
    APP_FIXTURES,
    RecordingTransport,
    ReplayTransport,
    fixture_name,
    recorded,
)
from flight_voice.flight_data.serpapi import SerpApiFlightData, search_params
from pydantic import SecretStr

from tests.flight_voice.flight_data.serpapi_support import (
    FIXTURES,
    KEY,
    ONE_WAY,
    ROUND_TRIP,
    body,
    content,
    held,
    query,
)
from tests.leaks import holding, shown


def _day(source: SerpApiFlightData, q: OfferQuery | None = None) -> DayOffers:
    async def one() -> DayOffers:
        try:
            return await source.day(q or query())
        finally:
            await source.aclose()

    return asyncio.run(one())


def test_the_seeded_fixtures_hold_the_adapters_own_params_and_no_key() -> None:
    assert held(ONE_WAY)["params"] == search_params(query())
    assert fixture_name(search_params(query())) == ONE_WAY.name == "RUH_JED_2026-11-19_c1_a1.json"
    assert held(ROUND_TRIP)["params"]["type"] == "1"
    for file in FIXTURES.glob("*.json"):
        assert "api_key" not in file.read_text(encoding="utf-8")


def test_a_replay_runs_through_the_real_adapter() -> None:
    answer = _day(recorded(FIXTURES))
    assert answer.status == "ok" and len(answer.offers) == 11
    assert recorded(FIXTURES).name == "recorded"


def test_a_search_no_fixture_holds_is_not_recorded(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level("INFO")
    q = query().model_copy(update={"adults": 2})
    with pytest.raises(FlightDataUnavailableError) as failed:
        _day(recorded(FIXTURES), q)
    assert failed.value.failure == "not_recorded"
    assert not failed.value.lasting
    [logged] = [r for r in caplog.records if r.getMessage() == "flight_data_not_recorded"]
    assert vars(logged)["fields"] == {"fixture": "RUH_JED_2026-11-19_c1_a2.json"}


def test_a_fixtures_params_are_matched_whole(tmp_path: Path) -> None:
    (tmp_path / "rt.json").write_text(ROUND_TRIP.read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / "broken.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(FlightDataUnavailableError) as failed:
        _day(recorded(tmp_path))
    assert failed.value.failure == "not_recorded"


def test_a_missing_folder_is_one_warning_then_nothing_recorded(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level("INFO")
    source = recorded(tmp_path / "absent")
    assert [r.getMessage() for r in caplog.records].count("flight_data_fixtures_missing") == 1
    with pytest.raises(FlightDataUnavailableError) as failed:
        _day(source)
    assert failed.value.failure == "not_recorded"


def test_the_apps_folder_is_found_from_the_package() -> None:
    assert APP_FIXTURES.parts[-3:] == ("flight-voice-agent", "evals", "flight_data")


def _recording(
    folder: Path, answer: bytes, status: int = 200
) -> tuple[SerpApiFlightData, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    async def network(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(status, content=answer, headers={"content-type": "application/json"})

    transport = RecordingTransport(folder, inner=httpx.MockTransport(network))
    return SerpApiFlightData(SecretStr(KEY), transport=transport), seen


def test_a_recording_is_written_without_the_key_and_replays(tmp_path: Path) -> None:
    source, seen = _recording(tmp_path, content(body()))
    assert _day(source).status == "ok"
    assert seen[0].url.params["api_key"] == KEY
    (written,) = tmp_path.iterdir()
    assert written.name == ONE_WAY.name
    text = written.read_text(encoding="utf-8")
    assert KEY not in text
    assert json.loads(text) == held(ONE_WAY)
    assert len(_day(recorded(tmp_path)).offers) == 11


def test_a_recording_that_would_hold_the_key_is_refused(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    caplog.set_level("DEBUG")
    leaky = body() | {"search_metadata": {"status": "Success", "json_endpoint": f"x?{KEY}"}}
    source, _ = _recording(tmp_path, content(leaky))
    assert _day(source).status == "ok"  # the answer still reaches the adapter
    assert list(tmp_path.iterdir()) == []
    assert any(r.getMessage() == "flight_data_recording_refused" for r in caplog.records)
    assert holding(KEY, shown(caplog=caplog, capsys=capsys)) == []


def test_a_failed_answer_is_never_recorded(tmp_path: Path) -> None:
    source, _ = _recording(tmp_path, b"{}", status=503)
    with pytest.raises(FlightDataUnavailableError):
        _day(source)
    assert not tmp_path.exists() or list(tmp_path.iterdir()) == []


def test_a_replay_answers_only_the_search_path() -> None:
    async def one() -> int:
        transport = ReplayTransport(FIXTURES)
        params = search_params(query())
        request = httpx.Request("GET", "https://serpapi.com/other", params=params)
        return (await transport.handle_async_request(request)).status_code

    assert asyncio.run(one()) == 404

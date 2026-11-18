"""The real network's parts built from the settings (flight_data/compose.py): the recorded
source over the fixtures with no cache, the live one behind the cache (none at 0) and recording
when asked, the mock refused here, the places and the Saudi codes said, and the real terms held
within the mock's Whisper bytes, so every command word stays in the prompt; and the lean
agent's deps for each source (`lean_deps`): the mock's own, which book, or the real network's,
which do not. The server booting on recorded is test_server_lean.py's."""

from __future__ import annotations

import asyncio
from datetime import date
from pathlib import Path
from typing import Any, Literal

import pytest
from flight_voice.flight_data.cache import CachedFlightData
from flight_voice.flight_data.compose import (
    REAL_TERMS,
    lean_deps,
    real_data,
    real_places,
    real_pronounce,
)
from flight_voice.flight_data.mock import MockFlightData
from flight_voice.flight_data.places import Directory
from flight_voice.flight_data.serpapi import SerpApiFlightData
from flight_voice.flight_data.settings import FlightDataFields
from flight_voice.persona import TERMS, Names
from pydantic import SecretStr
from t2_agentic_voice.languages import whisper_prompt

from tests.flight_voice.flight_data.serpapi_support import FIXTURES, query
from tests.flight_voice.tools.tool_support import airline


def _fields(**values: Any) -> FlightDataFields:
    """The settings given, the others their defaults, with nothing read from the shell (the
    mixin has no prefix of its own)."""
    return FlightDataFields.model_construct(**values)


def test_recorded_replays_the_fixtures_with_no_cache() -> None:
    data = real_data(_fields(flight_data="recorded", flight_data_fixtures=FIXTURES))
    assert isinstance(data, SerpApiFlightData) and data.name == "recorded"

    async def one() -> int:
        try:
            return len((await data.day(query())).offers)
        finally:
            await data.aclose()

    assert asyncio.run(one()) == 11


def test_serpapi_is_cached_unless_the_cache_is_off(tmp_path: Path) -> None:
    key = SecretStr("made-up-serpapi-key-zq9")
    cached = real_data(_fields(flight_data="serpapi", serpapi_key=key, flight_data_span_days=7))
    assert isinstance(cached, CachedFlightData)
    assert (cached.name, cached.span_days) == ("serpapi", 7)
    live = real_data(
        _fields(
            flight_data="serpapi",
            serpapi_key=key,
            flight_data_cache_s=0,
            flight_data_record_to=tmp_path,
        )
    )
    assert isinstance(live, SerpApiFlightData)
    asyncio.run(cached.aclose())
    asyncio.run(live.aclose())


def test_the_mock_and_a_keyless_serpapi_are_not_built_here() -> None:
    with pytest.raises(ValueError, match="mock"):
        real_data(_fields())
    with pytest.raises(ValueError, match="key"):
        real_data(_fields(flight_data="serpapi"))


def test_the_places_and_the_saudi_codes_said() -> None:
    assert real_places().home.code == "RUH"
    assert set(real_pronounce()) == {"SV", "XY", "F3", "RX"}


@pytest.mark.parametrize("language", ["ar", "en"])
def test_the_real_terms_fit_in_the_mocks_whisper_bytes(language: Literal["ar", "en"]) -> None:
    airline = Names().airline_name_en
    real = ", ".join((*REAL_TERMS, airline)).encode()
    mock = ", ".join((*TERMS, airline)).encode()
    assert len(real) <= len(mock)
    mocked = whisper_prompt((*TERMS, airline), language)
    prompt = whisper_prompt((*REAL_TERMS, airline), language)
    assert prompt.of - prompt.kept <= mocked.of - mocked.kept  # no command word lost


def _day() -> date:
    return date(2026, 11, 18)


def test_the_lean_deps_on_the_mock_are_the_mocks_and_book() -> None:
    deps = lean_deps(_fields(), airline(), Names(), today=_day)
    assert isinstance(deps.data, MockFlightData)
    assert (deps.bookable, deps.network, deps.terms) == (True, "mock", None)
    assert deps.today() == _day()


@pytest.mark.parametrize("source", ["recorded", "serpapi"])
def test_the_lean_deps_off_the_mock_are_the_real_networks_and_do_not_book(source: str) -> None:
    fields = _fields(
        flight_data=source,
        flight_data_fixtures=FIXTURES,
        serpapi_key=SecretStr("made-up-serpapi-key-zq9"),
    )
    deps = lean_deps(fields, airline(), Names(), today=_day)
    assert deps.data.name == source
    assert isinstance(deps.places, Directory) and deps.trips.home.code == "RUH"
    assert (deps.bookable, deps.network, deps.terms) == (False, "real", REAL_TERMS)
    assert set(deps.pronounce) == {"SV", "XY", "F3", "RX"}
    assert deps.today() == _day()
    asyncio.run(deps.data.aclose())

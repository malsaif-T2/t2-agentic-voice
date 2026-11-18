"""SerpApi's answer read into a day's offers (flight_data/serpapi_parse.py), over the seeded
fixtures: every itinerary with its carrier's id, Saudia's bus connection with its overnight
layover in Qassim and its next-day arrival, an itinerary with no price dropped, an answer with
only `other_flights`, no results as `no_flights`, a status of Error and a currency not SAR as
unavailable, and the provider's city names."""

from __future__ import annotations

import copy
from typing import Any

import pytest
from flight_voice.flight_data.port import FlightDataUnavailableError
from flight_voice.flight_data.serpapi_parse import read_day

from tests.flight_voice.flight_data.serpapi_support import (
    NOW,
    ROUND_TRIP,
    body,
    content,
    query,
)

IDS = [
    "SV1057-2026-11-19",
    "F3103-2026-11-19",
    "SV1021-2026-11-19",
    "F3111-2026-11-19",
    "F3113-2026-11-19",
    "XY17-2026-11-19",
    "XY35-2026-11-19",
    "F3121-2026-11-19",
    "SV1037-2026-11-19",
    "SV3079+SV8607-2026-11-19",
    "XY33-2026-11-19",
]


def _read(value: object) -> Any:
    return read_day(content(value), query(), NOW).answer


def test_every_itinerary_is_an_offer_with_its_carriers_id_in_departure_order() -> None:
    read = read_day(content(body()), query(), NOW)
    answer = read.answer
    assert answer.status == "ok" and read.took_s == 4.82
    assert [o.id for o in answer.offers] == IDS
    first = answer.offers[0]
    assert (first.carrier.code, first.carrier.name_en, first.flights) == (
        "SV",
        "Saudia",
        ("SV 1057",),
    )
    assert (first.price.amount, first.cabin, first.adults, first.seats_left) == (
        1122,
        "economy",
        1,
        None,
    )
    assert first.segments[0].aircraft == "Airbus A321" and first.nonstop
    assert {o.carrier.name_en for o in answer.offers} == {"Saudia", "flynas", "flyadeal"}
    assert answer.fetched_at == NOW


def test_saudias_bus_connection_keeps_its_layover_and_next_day() -> None:
    (connection,) = [o for o in _read(body()).offers if o.stops]
    assert connection.id == "SV3079+SV8607-2026-11-19"
    assert connection.bus and connection.segments[0].bus and not connection.segments[1].bus
    assert connection.next_day and connection.minutes == 460
    (layover,) = connection.layovers
    assert (layover.airport, layover.minutes, layover.overnight) == ("ELQ", 60, True)
    assert layover.name == "Prince Naif Bin Abdulaziz International Airport"
    assert connection.price.amount == 1142


def test_an_itinerary_with_no_whole_price_or_a_bad_number_is_dropped() -> None:
    value = body()
    del value["best_flights"][0]["price"]
    value["best_flights"][1]["price"] = 979.5
    value["best_flights"][2]["flights"][0]["flight_number"] = "Saudia 1057"
    ids = [o.id for o in _read(value).offers]
    assert "F3111-2026-11-19" not in ids and "XY17-2026-11-19" not in ids
    assert "SV1057-2026-11-19" not in ids
    assert len(ids) == len(IDS) - 3


def test_offers_sharing_an_id_keep_the_cheaper() -> None:
    value = body()
    twin = copy.deepcopy(value["best_flights"][0])
    twin["price"] = 500
    value["other_flights"].append(twin)
    (offer,) = [o for o in _read(value).offers if o.id == "F3111-2026-11-19"]
    assert offer.price.amount == 500


def test_an_answer_with_only_other_flights_is_read() -> None:
    value = body()
    value["other_flights"] = value.pop("best_flights") + value["other_flights"]
    assert [o.id for o in _read(value).offers] == IDS


def test_no_results_is_no_flights() -> None:
    value = body()
    del value["best_flights"], value["other_flights"]
    value["error"] = "Google hasn't returned any results for this query."
    answer = _read(value)
    assert (answer.status, answer.offers) == ("no_flights", ())


def test_itineraries_none_of_which_could_be_read_are_never_no_flights() -> None:
    value = body()
    for itinerary in (*value["best_flights"], *value["other_flights"]):
        itinerary["price"] = None
    with pytest.raises(FlightDataUnavailableError) as failed:
        _read(value)
    assert failed.value.failure == "bad_answer"


@pytest.mark.parametrize(
    ("change", "failure"),
    [
        ({"search_metadata": {"status": "Error"}}, "http_error"),
        ({"search_parameters": {"currency": "USD"}}, "bad_answer"),
        ({"search_parameters": {}}, "bad_answer"),
        ({"best_flights": "not a list"}, "bad_answer"),
    ],
)
def test_an_answer_that_failed_or_cannot_be_read_is_unavailable(
    change: dict[str, object], failure: str
) -> None:
    with pytest.raises(FlightDataUnavailableError) as failed:
        _read(body() | change)
    assert failed.value.failure == failure
    assert failed.value.__cause__ is None and failed.value.__context__ is None


def test_a_body_that_is_not_json_is_a_bad_answer() -> None:
    with pytest.raises(FlightDataUnavailableError) as failed:
        read_day(b"<html>busy</html>", query(), NOW)
    assert failed.value.failure == "bad_answer"
    assert failed.value.__context__ is None


def test_the_providers_city_names_are_kept() -> None:
    assert _read(body()).cities == (("RUH", "Riyadh"), ("JED", "Jeddah"))


def test_the_round_trip_example_reads_as_its_outbound_offers() -> None:
    answer = _read(body(ROUND_TRIP))
    assert len(answer.offers) == 7
    assert "SV3079+SV8607-2026-11-19" in [o.id for o in answer.offers]


def test_an_operating_carrier_is_kept_when_another_flies_it() -> None:
    value = body()
    value["best_flights"][0]["flights"][0]["flight_number"] = "RX 1111"
    value["best_flights"][0]["flights"][0]["plane_and_crew_by"] = "Saudia"
    value["best_flights"][1]["flights"][0]["plane_and_crew_by"] = "Flynas"
    offers = {o.id: o for o in _read(value).offers}
    operated = offers["RX1111-2026-11-19"].segments[0]
    assert operated.carrier.code == "RX"
    assert operated.operated_by is not None and operated.operated_by.code == "SV"
    assert offers["XY17-2026-11-19"].segments[0].operated_by is None

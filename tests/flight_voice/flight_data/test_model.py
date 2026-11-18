"""The flight data's model (flight_voice/flight_data/model.py, queries.py): an offer's id is its
flights' codes and its first day, within 40 characters, and a wrong id is refused; the derived
facts (next day, stops, flights, carriers, bus, seats); the models are frozen; and a bare place
is only ever three capital letters."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta, timezone
from typing import Any

import pytest
from flight_voice.flight_data.model import (
    Carrier,
    Layover,
    Money,
    Offer,
    Place,
    Segment,
    has_seats,
    offer_id,
)
from flight_voice.flight_data.queries import DayOffers, OfferQuery, SpanQuery
from pydantic import ValidationError

SAUDIA = Carrier(code="SV", name_en="Saudia", name_ar="السعودية")
AT = datetime(2026, 11, 18, 9, 0, tzinfo=UTC)
RIYADH = Place(code="RUH", airports=("RUH",), city_en="Riyadh", city_ar="الرياض")
LONDON = Place(
    code="LHR", airports=("LHR", "LGW", "STN"), city_en="London", city_ar="لندن", country="GB"
)


def _segment(number: str, origin: str, destination: str, departs: datetime, **more: Any) -> Segment:
    minutes = more.pop("minutes", 115)
    return Segment(
        carrier=more.pop("carrier", SAUDIA),
        number=number,
        origin=origin,
        destination=destination,
        departs=departs,
        arrives=departs + timedelta(minutes=minutes),
        minutes=minutes,
        **more,
    )


def _offer(*segments: Segment, **more: Any) -> Offer:
    fields: dict[str, Any] = {
        "id": offer_id(segments),
        "segments": segments,
        "minutes": sum(s.minutes for s in segments),
        "cabin": "economy",
        "adults": 1,
        "price": Money(amount=899),
        "fetched_at": AT,
    }
    return Offer(**(fields | more))


def test_an_offer_id_is_its_flights_codes_and_its_first_day() -> None:
    nonstop = _offer(_segment("1020", "RUH", "JED", datetime(2026, 11, 19, 8, 15)))
    connection = _offer(
        _segment("3079", "RUH", "ULH", datetime(2026, 11, 19, 22, 30), bus=True),
        _segment("8607", "ULH", "JED", datetime(2026, 11, 20, 6, 0)),
        layovers=(Layover(airport="ULH", minutes=360, overnight=True),),
    )
    assert nonstop.id == "SV1020-2026-11-19"
    assert connection.id == "SV3079+SV8607-2026-11-19"
    mock = _offer(
        _segment(
            "401",
            "RUH",
            "LHR",
            datetime(2026, 11, 19, 1, 40),
            carrier=Carrier(code="T2", name_en="T2 Air", name_ar="طيران تي تو"),
        )
    )
    assert mock.id == "T2401-2026-11-19"


def test_three_segments_of_the_longest_numbers_fit_in_forty_characters() -> None:
    start = datetime(2026, 11, 19, 1, 0)
    longest = _offer(
        _segment("1234A", "RUH", "DXB", start),
        _segment("1234A", "DXB", "IST", start + timedelta(hours=4)),
        _segment("1234A", "IST", "LHR", start + timedelta(hours=9)),
    )
    assert longest.id == "SV1234A+SV1234A+SV1234A-2026-11-19"
    assert len(longest.id) == 34 <= 40


def test_more_than_three_segments_are_refused() -> None:
    start = datetime(2026, 11, 19, 1, 0)
    legs = [_segment(str(n), "RUH", "JED", start + timedelta(hours=3 * n)) for n in range(1, 5)]
    with pytest.raises(ValidationError):
        _offer(*legs)


def test_a_wrong_id_is_refused() -> None:
    segment = _segment("1020", "RUH", "JED", datetime(2026, 11, 19, 8, 15))
    for wrong in ("SV1020-2026-11-20", "SV 1020-2026-11-19", "XY1020-2026-11-19"):
        with pytest.raises(ValidationError, match="its flights' codes"):
            _offer(segment, id=wrong)


def test_the_derived_facts_of_an_offer() -> None:
    flynas = Carrier(code="XY", name_en="flynas", name_ar="طيران ناس")
    late = _offer(
        _segment("3079", "RUH", "ULH", datetime(2026, 11, 19, 22, 30), bus=True),
        _segment("8607", "ULH", "JED", datetime(2026, 11, 20, 6, 0), carrier=flynas),
        _segment("3080", "JED", "MED", datetime(2026, 11, 20, 9, 0)),
    )
    assert late.next_day
    assert late.stops == 2
    assert not late.nonstop
    assert late.flights == ("SV 3079", "XY 8607", "SV 3080")
    assert late.carriers == (SAUDIA, flynas)
    assert late.carrier == SAUDIA
    assert (late.origin, late.destination) == ("RUH", "MED")
    assert late.day == date(2026, 11, 19)
    assert late.bus

    morning = _offer(_segment("1020", "RUH", "JED", datetime(2026, 11, 19, 8, 15)))
    assert not morning.next_day
    assert morning.stops == 0
    assert morning.nonstop
    assert morning.flights == ("SV 1020",)
    assert not morning.bus
    assert morning.segments[0].code == "SV1020"
    assert morning.segments[0].flight == "SV 1020"


def test_seats_are_enough_when_unknown_or_at_least_the_travelers() -> None:
    segment = _segment("1020", "RUH", "JED", datetime(2026, 11, 19, 8, 15))
    assert has_seats(_offer(segment), 9)
    assert has_seats(_offer(segment, seats_left=2), 2)
    assert not has_seats(_offer(segment, seats_left=1), 2)
    assert not has_seats(_offer(segment, seats_left=0), 1)


def test_the_models_are_frozen_and_take_no_other_field() -> None:
    offer = _offer(_segment("1020", "RUH", "JED", datetime(2026, 11, 19, 8, 15)))
    with pytest.raises(ValidationError):
        offer.price = Money(amount=1)  # type: ignore[misc]
    with pytest.raises(ValidationError):
        RIYADH.code = "JED"  # type: ignore[misc]
    with pytest.raises(ValidationError):
        Money(amount=10, per_person=True)  # type: ignore[call-arg]
    with pytest.raises(ValidationError):
        Money(amount=10, currency="USD")  # type: ignore[arg-type]


def test_segment_times_are_local_and_fetched_at_is_aware_utc() -> None:
    with pytest.raises(ValidationError, match="local time"):
        _segment("1020", "RUH", "JED", datetime(2026, 11, 19, 8, 15, tzinfo=UTC))
    segment = _segment("1020", "RUH", "JED", datetime(2026, 11, 19, 8, 15))
    with pytest.raises(ValidationError, match="aware"):
        _offer(segment, fetched_at=datetime(2026, 11, 18, 9, 0))
    riyadh_time = datetime(2026, 11, 18, 12, 0, tzinfo=timezone(timedelta(hours=3)))
    assert _offer(segment, fetched_at=riyadh_time).fetched_at == AT
    assert _offer(segment, fetched_at=riyadh_time).fetched_at.utcoffset() == timedelta(0)


@pytest.mark.parametrize("number", ["1020", "1", "1234A"])
def test_a_flight_number_is_up_to_four_digits_and_a_letter(number: str) -> None:
    assert _segment(number, "RUH", "JED", datetime(2026, 11, 19, 8, 15)).number == number


@pytest.mark.parametrize("number", ["", "12345", "SV1020", "1020ab", "10 20"])
def test_a_malformed_flight_number_is_refused(number: str) -> None:
    with pytest.raises(ValidationError):
        _segment(number, "RUH", "JED", datetime(2026, 11, 19, 8, 15))


def test_a_bare_place_is_its_code_and_not_known() -> None:
    place = Place.bare("ZZZ")
    assert place.code == "ZZZ"
    assert place.airports == ("ZZZ",)
    assert (place.city_en, place.city_ar) == ("ZZZ", "ZZZ")
    assert not place.known


@pytest.mark.parametrize("said", ["Goa", "goa", "LH", "LHRX", "جدة", "علا", "LH1", " LHR", "LHR\n"])
def test_a_bare_place_refuses_anything_but_three_capital_letters(said: str) -> None:
    with pytest.raises(ValueError, match="three capital letters"):
        Place.bare(said)


def test_a_place_names_its_code_first_and_each_airport_once() -> None:
    with pytest.raises(ValidationError, match="first"):
        Place(code="LHR", airports=("LGW", "LHR"), city_en="London", city_ar="لندن")
    with pytest.raises(ValidationError, match="once"):
        Place(code="LHR", airports=("LHR", "LHR"), city_en="London", city_ar="لندن")
    with pytest.raises(ValidationError):
        Place(code="LHR", airports=(), city_en="London", city_ar="لندن")


def test_a_place_is_said_to_and_from_by_register() -> None:
    assert RIYADH.to_city("saudi") == "للرياض"
    assert LONDON.to_city("saudi") == "للندن"
    assert LONDON.to_city("msa") == "إلى لندن"
    assert LONDON.to_city("en") == "to London"
    assert LONDON.from_city("saudi") == "من لندن"
    assert LONDON.from_city("en") == "from London"
    assert LONDON.city("msa") == "لندن"
    assert SAUDIA.name("en") == "Saudia"
    assert SAUDIA.name("saudi") == "السعودية"


def test_a_query_key_joins_a_places_airports() -> None:
    query = OfferQuery(origin=RIYADH, destination=LONDON, day=date(2026, 11, 19))
    assert query.key() == "RUH-LHR+LGW+STN-2026-11-19-economy-1"
    two = OfferQuery(
        origin=RIYADH, destination=RIYADH, day=date(2026, 11, 19), cabin="business", adults=2
    )
    assert two.key() == "RUH-RUH-2026-11-19-business-2"


def test_a_span_gives_each_day_as_a_query_and_refuses_a_backward_span() -> None:
    span = SpanQuery(
        origin=RIYADH, destination=LONDON, first=date(2026, 11, 29), last=date(2026, 12, 1)
    )
    assert span.dates() == (date(2026, 11, 29), date(2026, 11, 30), date(2026, 12, 1))
    assert span.day(date(2026, 11, 30)).key() == "RUH-LHR+LGW+STN-2026-11-30-economy-1"
    with pytest.raises(ValidationError, match="last day"):
        SpanQuery(
            origin=RIYADH, destination=LONDON, first=date(2026, 12, 1), last=date(2026, 11, 29)
        )


def test_an_answer_holds_offers_only_when_ok() -> None:
    query = OfferQuery(origin=RIYADH, destination=LONDON, day=date(2026, 11, 19))
    offer = _offer(_segment("119", "RUH", "LHR", datetime(2026, 11, 19, 1, 40), minutes=445))
    assert DayOffers(query=query, status="ok", offers=(offer,), fetched_at=AT).offers == (offer,)
    assert DayOffers(query=query, status="no_flights", fetched_at=AT).offers == ()
    with pytest.raises(ValidationError, match="only when"):
        DayOffers(query=query, status="no_flights", offers=(offer,), fetched_at=AT)

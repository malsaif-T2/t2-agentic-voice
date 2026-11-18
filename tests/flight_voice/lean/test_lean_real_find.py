"""The lean tools on the real network, over a fake source and directory (no network): a day of
several airlines as the model reads it (each option's airline, flights, stops, the wait of a
connection, a road leg by bus, the carrier that flies it, the airlines counted only when two or
more fly, no seats or full-flight note where the source counts no seats, the party's price);
the airline filter run before the pool, by name in English or Arabic or by code, and its two
refusals; an unknown place; a failed source said as failed, never as no flights; no flights
with the nearest days not checked; a day past what the airlines show; a round trip whose way
back failed, then checked by a second search; a new search with more travelers keeping a pick
at its new price, or dropping it; the draft read again after the search's wait; a pick kept at
the price heard however the source's price moves after; and no booking on this line."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta
from typing import Any

from flight_voice.flight_data.model import Carrier, Layover, Money
from flight_voice.flight_data.port import Failure, FlightDataUnavailableError
from flight_voice.flight_data.queries import DayFare, DayFares, SpanQuery
from flight_voice.lean.agent import lean_tools
from flight_voice.lean.book import NOT_BOOKABLE, book_trip
from flight_voice.lean.find import LOST, RETURN_UNKNOWN
from flight_voice.lean.find_dates import TOO_FAR_REAL
from flight_voice.lean.find_legs import NOT_CHECKED, UNKNOWN_PLACE
from flight_voice.lean.results import SEARCH_DOWN
from flight_voice.lean.span import CHECKED_LAST
from flight_voice.tools.results import SEARCH_FAILED

from tests.flight_voice.flight_data.fake import (
    EMIRATES,
    FLYADEAL,
    JEDDAH,
    LONDON,
    RIYADH,
    SAUDIA,
    FakeFlightData,
    answered,
    nonstop,
    offer,
    query,
    segment,
)
from tests.flight_voice.lean.real_support import BACK, OUT, london_back, london_day, real_call
from tests.flight_voice.tools.tool_support import CALL_ID, card_passes, data, ids_pass, run


def _at(hour: int, minute: int = 0) -> datetime:
    """A time on the outbound day."""
    return datetime(OUT.year, OUT.month, OUT.day, hour, minute)


def _day(answer: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = answer["outbound"]
    return out


def test_a_day_of_several_airlines_is_given_as_plain_data() -> None:
    call = real_call()
    found = call.find(destination="London", depart=OUT.isoformat())
    answer = data(found)
    assert answer["route"] == "Riyadh to London" and answer["fares_are"] == "per person, as of now"
    day = _day(answer)
    assert day["count"] == 6 and "more" not in day
    assert [a["airline"] for a in day["airlines"]] == [
        "Saudia",
        "Qatar Airways",
        "Emirates",
        "British Airways",
    ]
    by_dubai = next(o for o in day["options"] if o["airline"] == "Emirates")
    assert by_dubai["id"] == "EK818+EK3-2026-12-03" and by_dubai["flight"] == "EK 818, EK 3"
    assert by_dubai["stops"] == 1 and by_dubai["aircraft"] == "Boeing 777-300ER"
    assert by_dubai["via"] == [{"city": "Dubai", "wait": {"hours": 2, "minutes": 5}}]
    assert day["cheapest_id"] == by_dubai["id"]
    assert all("seats_ok" not in o for o in day["options"])  # the source counts no seats
    assert "note" not in answer  # a full flight is never noted where seats are not counted
    assert found.card is not None and card_passes(found)
    assert len(found.card.rows) == 6
    assert "1 stop in Dubai, 2 h 5 min" in (found.card.rows[2].detail or "")


def test_a_bus_leg_and_another_carrier_flying_it_are_said() -> None:
    data_ = FakeFlightData()
    road = segment(SAUDIA, "3079", ("RUH", "ULH"), _at(22, 30), 60, bus=True)
    flown = segment(
        SAUDIA, "8607", ("ULH", "JED"), _at(23, 50) + timedelta(hours=6), 70, operated_by=FLYADEAL
    )
    wait = Layover(airport="ULH", minutes=440, overnight=True)
    data_.set(
        answered(query(RIYADH, JEDDAH, OUT), [offer(road, flown, price=1142, layovers=(wait,))])
    )
    answer = data(real_call(data_).find(destination="Jeddah", depart=OUT.isoformat()))
    (option,) = _day(answer)["options"]
    assert option["bus"] is True and option["operated_by"] == "flyadeal"
    assert option["next_day"] is True and option["via"][0]["overnight"] is True
    assert option["via"][0]["city"] == "Al-Ula" and "airlines" not in _day(answer)


def test_the_airline_filter_runs_before_the_pool() -> None:
    # Emirates flies only by Dubai that day: filtered first, its connections are listed.
    for said in ("Emirates", "الإمارات", "EK", "ek"):
        answer = data(real_call().find(destination="London", depart=OUT.isoformat(), airline=said))
        day = _day(answer)
        assert [o["airline"] for o in day["options"]] == ["Emirates"], said
        assert day["count"] == 1 and "airlines" not in day
    saudia = data(
        real_call().find(destination="London", depart=OUT.isoformat(), airline="السعودية")
    )
    assert {o["airline"] for o in _day(saudia)["options"]} == {"Saudia"}


def test_an_airline_that_does_not_fly_the_day_names_those_that_do() -> None:
    answer = data(real_call().find(destination="London", depart=OUT.isoformat(), airline="flynas"))
    assert answer["status"] == "no_flights_for_airline" and answer["airline"] == "flynas"
    assert answer["airlines"] == ["Saudia", "Qatar Airways", "Emirates", "British Airways"]
    gulf = Carrier(code="6S", name_en="Saudi Gulf Airlines", name_ar="السعودية الخليجية")
    data_ = FakeFlightData()
    saudi = Carrier(code="SV", name_en="Saudia", name_ar="السعودية", aliases=("Saudi Airlines",))
    data_.set(
        answered(
            query(RIYADH, JEDDAH, OUT),
            [
                nonstop(saudi, "1020", ("RUH", "JED"), _at(8), 110, 900),
                nonstop(gulf, "100", ("RUH", "JED"), _at(9), 110, 800),
            ],
        )
    )
    which = data(
        real_call(data_).find(destination="Jeddah", depart=OUT.isoformat(), airline="Saudi")
    )
    assert which == {"status": "which_airline", "airlines": ["Saudia", "Saudi Gulf Airlines"]}


def test_a_place_the_directory_does_not_know_is_asked_again() -> None:
    call = real_call()
    answer = data(call.find(destination="Narnia", depart=OUT.isoformat()))
    assert answer == {"status": "unknown_place", "which": "destination", "note": UNKNOWN_PLACE}
    bare = data(call.find(destination="ZZZ", depart=OUT.isoformat()))  # answered nothing
    assert bare["status"] == "unknown_place"
    data_ = FakeFlightData()
    elq = query(RIYADH, JEDDAH, OUT).model_copy(update={"destination": JEDDAH.bare("ELQ")})
    flight = nonstop(SAUDIA, "1611", ("RUH", "ELQ"), _at(7), 80, 450)
    data_.set(answered(elq, [flight], cities=(("ELQ", "Buraidah"),)))
    named = data(real_call(data_).find(destination="ELQ", depart=OUT.isoformat()))
    assert named["route"] == "Riyadh to Buraidah"


def test_a_failed_source_is_said_as_failed_never_as_no_flights() -> None:
    cases: tuple[tuple[Failure, str], ...] = (
        ("timeout", SEARCH_FAILED),
        ("rejected_key", SEARCH_DOWN),
    )
    for failure, said in cases:
        data_ = FakeFlightData()
        data_.set(FlightDataUnavailableError("day", failure), query(RIYADH, LONDON, OUT).key())
        call = real_call(data_)
        found = call.find(destination="London", depart=OUT.isoformat())
        assert not found.ok and said in str(found.data) and "no_flights" not in str(found.data)
        assert call.draft.destination is None


def test_no_flights_with_no_nearest_days_says_they_were_not_checked() -> None:
    answer = data(real_call(FakeFlightData()).find(destination="Jeddah", depart=OUT.isoformat()))
    assert answer == {
        "status": "no_flights",
        "day": OUT.isoformat(),
        "nearest": [],
        "note": NOT_CHECKED,
    }


def test_a_day_past_what_the_airlines_show_says_so() -> None:
    call = real_call()
    last = call.deps.data.last_day(call.deps.today())
    answer = data(call.find(destination="London", depart=(last + timedelta(days=1)).isoformat()))
    assert answer["status"] == "date_problem" and answer["problem"] == "beyond_window"
    assert answer["note"] == TOO_FAR_REAL and answer["last_day"] == last.isoformat()


def test_a_way_back_that_failed_is_unknown_then_checked_by_a_second_search() -> None:
    data_ = FakeFlightData()
    data_.set(answered(query(RIYADH, LONDON, OUT), london_day()))
    back_key = query(LONDON, RIYADH, BACK).key()
    data_.set(FlightDataUnavailableError("day", "timeout"), back_key)
    call = real_call(data_)
    days = {"destination": "London", "depart": OUT.isoformat(), "return_date": BACK.isoformat()}
    answer = data(call.find(**days))
    assert answer["return"] == {
        "status": "unknown",
        "day": {"date": BACK.isoformat(), "weekday": "Thursday"},
        "note": RETURN_UNKNOWN,
    }
    assert answer["fares_are"] == "per person, each way, as of now"
    assert data(call.choose(list_leg="return")) == {"status": "unknown", "note": RETURN_UNKNOWN}
    picked = data(call.choose(outbound_id=_day(answer)["options"][0]["id"]))
    assert picked["missing"] == ["return"] and picked["note"] == RETURN_UNKNOWN
    data_.set(answered(query(LONDON, RIYADH, BACK), london_back()))
    again = data(call.find(**days))
    assert again["return"]["count"] == 2 and "outbound" in again["chosen"]


def test_more_travelers_keep_a_pick_at_its_new_price_or_drop_it() -> None:
    data_ = FakeFlightData()
    data_.set(answered(query(RIYADH, LONDON, OUT), london_day()))
    call = real_call(data_)
    found = data(call.find(destination="London", depart=OUT.isoformat()))
    pick = _day(found)["options"][0]["id"]
    call.choose(outbound_id=pick)
    data_.set(answered(query(RIYADH, LONDON, OUT, adults=2), london_day(adults=2, scale=2)))
    two = data(call.find(destination="London", depart=OUT.isoformat(), travelers=2))
    assert two["chosen"] == {"outbound": pick} and two["fares_are"] == "for all of you, as of now"
    assert call.total() == 6300  # the party's price, as the source gave it
    gone = [o for o in london_day(adults=3, scale=3) if o.id != pick]
    data_.set(answered(query(RIYADH, LONDON, OUT, adults=3), gone))
    three = data(call.find(destination="London", depart=OUT.isoformat(), travelers=3))
    assert three["lost"] == [{"leg": "outbound", "departs": "01:40"}] and LOST in three["note"]
    assert call.draft.chosen_outbound is None


def test_the_draft_is_read_again_after_the_search() -> None:
    call = real_call()
    days = {"destination": "London", "depart": OUT.isoformat(), "return_date": BACK.isoformat()}
    first = data(call.find(**days))
    pick = _day(first)["options"][1]["id"]
    source = call.deps.data
    assert isinstance(source, FakeFlightData)

    async def meanwhile() -> None:  # another tool chooses while the search waits
        held = call.trips.get(CALL_ID)
        listed = held.listed_outbound
        assert listed is not None
        chosen = next(o for o in listed.offers if o.id == pick)
        call.trips.put(CALL_ID, held.choose("outbound", chosen))
        await asyncio.sleep(0)

    source.during = meanwhile
    again = data(call.find(**days))
    assert again["chosen"] == {"outbound": pick} and again["return"]["count"] == 2


def test_a_pick_keeps_the_price_heard_however_the_source_moves_after() -> None:
    data_ = FakeFlightData()
    data_.set(answered(query(RIYADH, LONDON, OUT), london_day()))
    call = real_call(data_)
    found = data(call.find(destination="London", depart=OUT.isoformat()))
    heard = _day(found)["options"][0]
    data_.set(answered(query(RIYADH, LONDON, OUT), london_day(scale=2)))
    picked = data(call.choose(outbound_id=heard["id"]))
    assert picked["outbound"]["price"] == heard["price"] == picked["total"] == call.total()
    assert data_.calls["day"] == 1  # choosing asks the source nothing


def test_the_real_line_does_not_book() -> None:
    call = real_call()
    assert [t.name for t in lean_tools(call.deps)] == [
        "find_flights",
        "choose_flights",
        "traveler_profile",
    ]
    assert data(run(book_trip(call.deps), "en")) == NOT_BOOKABLE
    (choose,) = (t for t in lean_tools(call.deps) if t.name == "choose_flights")
    assert "book_trip" not in choose.description


def test_a_price_said_with_its_basis_passes_the_id_rule() -> None:
    for travelers in (1, 2):
        data_ = FakeFlightData()
        data_.set(answered(query(RIYADH, LONDON, OUT, adults=travelers), london_day(travelers)))
        found = real_call(data_).find(
            destination="London", depart=OUT.isoformat(), travelers=travelers
        )
        answer = data(found)
        price = _day(answer)["options"][0]["price"]
        said = f"The cheapest leaves at 01:40 at {price}, {answer['fares_are']}."
        assert ids_pass([said], found.texts()), said


def test_a_span_gives_the_days_checked_and_those_that_could_not_be() -> None:
    first, last = OUT, OUT + timedelta(days=4)
    span = SpanQuery(origin=RIYADH, destination=LONDON, first=first, last=last)
    fares = DayFares(
        query=span,
        status="ok",
        days=(
            DayFare(day=first, lowest=Money(amount=2480), flights=6),
            DayFare(day=first + timedelta(days=1), known=False),
            DayFare(day=first + timedelta(days=2), lowest=Money(amount=2300), flights=4),
            DayFare(day=first + timedelta(days=3)),
        ),
        checked_last=first + timedelta(days=3),
    )
    data_ = FakeFlightData(spans={"RUH-LHR": fares})
    found = real_call(data_).find(
        destination="London", depart={"first": first.isoformat(), "last": last.isoformat()}
    )
    answer = data(found)
    assert answer["status"] == "days" and "departs" not in answer
    assert [d["date"] for d in answer["unknown_days"]] == [(first + timedelta(days=1)).isoformat()]
    assert answer["cheapest_days"] == [(first + timedelta(days=2)).isoformat(), first.isoformat()]
    assert answer["checked_last"] == (first + timedelta(days=3)).isoformat()
    assert CHECKED_LAST in answer["note"] and "To book" not in answer["note"]
    assert found.card is not None and card_passes(found)
    failed = FakeFlightData(spans={"RUH-LHR": FlightDataUnavailableError("days", "timeout")})
    down = real_call(failed).find(
        destination="London", depart={"first": first.isoformat(), "last": last.isoformat()}
    )
    assert not down.ok and SEARCH_FAILED in str(down.data)


def test_the_arabic_reply_names_airlines_and_cities_in_arabic() -> None:
    answer = data(real_call(tag="ar-SA").find(destination="لندن", depart=OUT.isoformat()))
    assert answer["fares_are"] == "للشخص، رايح بس، بسعر الحين"
    assert answer["fares_are_msa"] == "للشخص، ذهاب فقط، بسعر الآن"
    day = _day(answer)
    assert day["airlines"][0]["airline"] == "السعودية"
    by_dubai = next(o for o in day["options"] if o["stops"] == 1 and o["via"][0]["city"] == "دبي")
    assert by_dubai["airline"] == "طيران الإمارات"
    assert json.dumps(answer, ensure_ascii=False).count("للشخص") == 2  # the basis and its MSA


def test_a_busy_day_lists_at_most_six_and_keeps_each_airline() -> None:
    more = (
        *london_day(),
        nonstop(SAUDIA, "125", ("RUH", "LHR"), _at(16), 445, 3600),
        nonstop(SAUDIA, "127", ("RUH", "LHR"), _at(19), 445, 3700),
        nonstop(EMIRATES, "820", ("RUH", "LHR"), _at(20), 430, 3800),
    )
    data_ = FakeFlightData()
    data_.set(answered(query(RIYADH, LONDON, OUT), more))
    day = _day(data(real_call(data_).find(destination="London", depart=OUT.isoformat())))
    assert len(day["options"]) == 6 and day["count"] == 9 and day["more"] == 3
    assert {"Emirates", "Saudia", "Qatar Airways", "British Airways"} <= {
        o["airline"] for o in day["options"]
    }

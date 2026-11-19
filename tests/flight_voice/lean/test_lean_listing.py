"""Which offers a leg lists (flight_voice/lean/listing.py): the pool keeps every nonstop and a
connection only on a day with no nonstop, or when it is at least 100 SAR cheaper and at most
twice the fastest nonstop's time; a listing holds at most six, keeping the cheapest, each
airline's cheapest, the earliest, the latest and each part of the day; always in departure
order, ties by id; and each airline's count and cheapest when two or more fly."""

from __future__ import annotations

from datetime import datetime

from flight_voice.flight_data.model import Layover, Offer
from flight_voice.lean.listing import by_airline, listed, pool

from tests.flight_voice.flight_data.fake import (
    EMIRATES,
    FLYADEAL,
    FLYNAS,
    QATAR,
    SAUDIA,
    nonstop,
    offer,
    segment,
)


def _at(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 11, 19, hour, minute)


def _connection(price: int, minutes: int, departs: datetime) -> Offer:
    first = segment(SAUDIA, "3079", ("RUH", "ULH"), departs, 60, bus=True)
    second = segment(SAUDIA, "8607", ("ULH", "JED"), departs.replace(hour=departs.hour + 2), 60)
    wait = minutes - 120
    return offer(first, second, price=price, layovers=(Layover(airport="ULH", minutes=wait),))


def test_a_connection_joins_only_when_much_cheaper_and_not_much_slower() -> None:
    fast = nonstop(FLYADEAL, "111", ("RUH", "JED"), _at(8), 115, 899)
    dear_bus = _connection(1142, 230, _at(9))  # dearer than the nonstop: dropped
    assert [o.id for o in pool([fast, dear_bus])] == [fast.id]
    cheap_slow = _connection(700, 240, _at(9))  # 199 cheaper but more than twice as long
    assert pool([fast, cheap_slow]) == (fast,)
    cheap_fit = _connection(790, 230, _at(9))  # 109 cheaper, within twice the time
    assert pool([fast, cheap_fit]) == (fast, cheap_fit)
    almost = _connection(800, 230, _at(9))  # 99 cheaper: not enough
    assert pool([fast, almost]) == (fast,)
    assert pool([dear_bus]) == (dear_bus,)  # no nonstop that day


def test_at_most_six_are_listed_keeping_each_airline_the_ends_and_each_part_of_day() -> None:
    day = [
        nonstop(SAUDIA, "1000", ("RUH", "JED"), _at(1, 30), 110, 900),  # the earliest, night
        nonstop(SAUDIA, "1002", ("RUH", "JED"), _at(6), 110, 500),  # the cheapest
        nonstop(SAUDIA, "1004", ("RUH", "JED"), _at(7), 110, 520),
        nonstop(SAUDIA, "1006", ("RUH", "JED"), _at(8), 110, 530),
        nonstop(SAUDIA, "1008", ("RUH", "JED"), _at(9), 110, 540),
        nonstop(FLYNAS, "201", ("RUH", "JED"), _at(10), 110, 650),  # flynas' cheapest
        nonstop(FLYNAS, "203", ("RUH", "JED"), _at(11), 110, 700),
        nonstop(SAUDIA, "1010", ("RUH", "JED"), _at(14), 110, 800),  # the afternoon's
        nonstop(SAUDIA, "1012", ("RUH", "JED"), _at(15), 110, 820),
        nonstop(FLYADEAL, "301", ("RUH", "JED"), _at(23, 30), 110, 990),  # the latest
    ]
    kept = listed(day)
    ids = [o.id for o in kept]
    assert len(kept) == 6
    for must in ("SV1002", "XY201", "F3301", "SV1000", "SV1010"):
        assert any(i.startswith(must) for i in ids), must
    assert [o.departs for o in kept] == sorted(o.departs for o in kept)
    assert listed(day[:4]) == tuple(day[:4])  # a short day lists whole


def test_ties_in_time_are_broken_by_id_and_the_order_is_the_same_every_time() -> None:
    same = [
        nonstop(c, n, ("RUH", "JED"), _at(9), 110, 600) for c, n in ((QATAR, "9"), (EMIRATES, "8"))
    ]
    assert [o.id for o in listed(same)] == sorted(o.id for o in same)
    assert listed(list(reversed(same))) == listed(same)


def test_each_airline_is_counted_when_two_or_more_fly() -> None:
    day = [
        nonstop(SAUDIA, "1020", ("RUH", "JED"), _at(8), 110, 900),
        nonstop(FLYADEAL, "111", ("RUH", "JED"), _at(9), 110, 699),
        nonstop(SAUDIA, "1022", ("RUH", "JED"), _at(10), 110, 850),
    ]
    counted = by_airline(day, "en")
    assert counted is not None
    assert [(a.airline, a.flights, a.cheapest) for a in counted] == [
        ("Saudia", 2, 850),
        ("flyadeal", 1, 699),
    ]
    arabic = by_airline(day, "ar-SA")
    assert arabic is not None and arabic[0].airline == "السعودية"
    assert by_airline(day[:1], "en") is None


def test_the_priciest_is_always_listed() -> None:
    # Plan 011's round 2: "the most expensive" of a day must be among the flights to choose.
    day = [
        nonstop(SAUDIA, f"10{n:02d}", ("RUH", "JED"), _at(6 + n), 110, 500 + 10 * n)
        for n in range(9)
    ]
    dear = nonstop(SAUDIA, "1100", ("RUH", "JED"), _at(16, 30), 110, 2400)
    kept = listed([*day, dear, nonstop(SAUDIA, "1102", ("RUH", "JED"), _at(17), 110, 560)])
    assert len(kept) == 6 and dear in kept

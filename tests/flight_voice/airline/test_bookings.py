"""The mock airline's bookings store: seeded with the past trips and put back by `reset`; a
write priced again, refused on any change; its modes; the lookup; and every read scoped to the
traveler it is given (adversarial: another traveler's ID sees and changes nothing)."""

from __future__ import annotations

import asyncio
from datetime import date

import pytest
from flight_voice.airline.bookings import (
    MODES,
    SEED,
    BookingRefused,
    BookingStore,
    BookingTimeoutError,
    Leg,
    LookupUnavailableError,
    Mode,
    NewBooking,
    priced,
)
from flight_voice.airline.profile import PAST_TRIPS, TRAVELER

TODAY = date(2026, 11, 16)
OUT = Leg(flight=401, day=date(2026, 12, 17))
BACK = Leg(flight=404, day=date(2026, 12, 20))
# T2 401 at 3,560 and T2 404 at 2,960 in economy (test_schedule's and test_fares' days).
TOTAL = 3560 + 2960


def _store(mode: Mode = "answer", *, lookup: bool = True) -> BookingStore:
    return BookingStore(today=lambda: TODAY, mode=mode, lookup=lookup, late_s=0.0)


def _new(request_id: str = "req-1", /, **changes: object) -> NewBooking:
    fields: dict[str, object] = {
        "request_id": request_id,
        "traveler_id": TRAVELER.id,
        "legs": (OUT, BACK),
        "cabin": "economy",
        "travelers": 1,
        "total_sar": TOTAL,
    }
    return NewBooking.model_validate(fields | changes)


def test_the_store_is_seeded_with_the_five_past_trips() -> None:
    store = _store()
    listed = store.listed(TRAVELER.id)
    assert [b.reference for b in listed] == [t.reference for t in PAST_TRIPS]
    assert all(b.flown and b.request_id is None for b in listed)
    assert [len(b.legs) for b in SEED] == [2, 2, 2, 1, 2]
    assert SEED[0].legs == (
        Leg(flight=201, day=date(2026, 10, 8)),
        Leg(flight=202, day=date(2026, 10, 11)),
    )


def test_a_write_books_the_trip_priced_as_read_back() -> None:
    store = _store()
    made = asyncio.run(store.create(_new()))
    assert (made.origin, made.destination) == ("RUH", "LHR")
    assert (made.depart, made.return_date, made.total_sar) == (OUT.day, BACK.day, TOTAL)
    assert len(made.reference) == 6 and made.reference.isdigit()
    assert made.reference not in {t.reference for t in PAST_TRIPS}
    assert not made.flown and made.request_id == "req-1"
    assert store.listed(TRAVELER.id)[0] == made
    assert store.writes == ["req-1"]


def test_a_one_way_write_and_two_travelers() -> None:
    made = asyncio.run(_store().create(_new(legs=(OUT,), travelers=2, total_sar=2 * 3560)))
    assert made.return_date is None and made.travelers == 2 and made.total_sar == 7120


def test_the_same_request_id_books_once() -> None:
    store = _store()
    first = asyncio.run(store.create(_new()))
    again = asyncio.run(store.create(_new()))
    assert again == first
    assert len([b for b in store.listed(TRAVELER.id) if not b.flown]) == 1
    assert store.writes == ["req-1", "req-1"]


def test_each_new_request_gets_its_own_reference() -> None:
    store = _store()
    refs = {asyncio.run(store.create(_new(f"req-{n}"))).reference for n in range(20)}
    assert len(refs) == 20


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"total_sar": TOTAL - 10}, "price_changed"),
        ({"legs": (OUT,), "cabin": "business", "total_sar": 3560}, "price_changed"),
        ({"legs": (Leg(flight=401, day=date(2026, 11, 10)),)}, "date_passed"),
        ({"legs": (Leg(flight=999, day=OUT.day),)}, "no_such_flight"),
        ({"legs": (Leg(flight=601, day=date(2026, 11, 17)),)}, "no_such_flight"),  # a Tuesday
        ({"legs": (Leg(flight=401, day=date(2027, 3, 28)),)}, "no_such_flight"),
        ({"legs": (OUT, Leg(flight=202, day=BACK.day))}, "no_such_flight"),  # back from Dubai
        ({"legs": (OUT, Leg(flight=404, day=date(2026, 12, 16)))}, "no_such_flight"),
        ({"legs": (Leg(flight=403, day=OUT.day),), "cabin": "first"}, "no_seats"),
        ({"legs": (Leg(flight=201, day=OUT.day),), "cabin": "first"}, "no_seats"),
        ({"legs": (OUT,), "cabin": "business", "travelers": 9, "total_sar": 1}, "no_seats"),
    ],
)
def test_a_write_that_is_not_the_trip_read_back_is_refused(
    changes: dict[str, object], reason: str
) -> None:
    store = _store()
    with pytest.raises(BookingRefused) as refused:
        asyncio.run(store.create(_new(**changes)))
    assert refused.value.reason == reason
    assert [b for b in store.listed(TRAVELER.id) if not b.flown] == []


def test_priced_sums_each_leg_times_the_travelers() -> None:
    assert priced((OUT, BACK), "economy", 1, TODAY) == TOTAL
    assert priced((OUT, BACK), "economy", 3, TODAY) == 3 * TOTAL
    assert priced((OUT,), "business", 1, TODAY) == 11390


def test_refuse_mode_books_nothing() -> None:
    store = _store(mode="refuse")
    with pytest.raises(BookingRefused) as refused:
        asyncio.run(store.create(_new()))
    assert refused.value.reason == "refused"
    assert store.listed(TRAVELER.id) == _store().listed(TRAVELER.id)
    assert store.writes == ["req-1"]


def test_timeout_mode_waits_then_fails_having_booked_nothing() -> None:
    store = _store(mode="timeout")
    with pytest.raises(BookingTimeoutError):
        asyncio.run(store.create(_new()))
    assert asyncio.run(store.find("req-1", TRAVELER.id)) is None


def test_late_mode_books_at_once_so_a_lookup_finds_it_before_the_answer() -> None:
    store = BookingStore(today=lambda: TODAY, mode="late", late_s=0.2)

    async def scenario() -> tuple[object, object]:
        write = asyncio.create_task(store.create(_new()))
        await asyncio.sleep(0.05)
        found = await store.find("req-1", TRAVELER.id)
        return found, await write

    found, made = asyncio.run(scenario())
    assert found is not None and found == made


def test_the_lookup_can_be_off() -> None:
    with pytest.raises(LookupUnavailableError):
        asyncio.run(_store(lookup=False).find("req-1", TRAVELER.id))


def test_reset_puts_the_seed_back() -> None:
    store = _store()
    asyncio.run(store.create(_new()))
    store.reset()
    assert store.listed(TRAVELER.id) == _store().listed(TRAVELER.id) and store.writes == []
    assert set(MODES) == {"answer", "refuse", "timeout", "late"}


def test_another_travelers_id_sees_nothing_and_takes_nothing() -> None:
    """The store answers only for the traveler ID it is given: another ID lists nothing, finds
    nothing, and a write with this traveler's request ID under another ID is refused."""
    store = _store()
    asyncio.run(store.create(_new()))
    assert store.listed("T-0002") == ()
    assert asyncio.run(store.find("req-1", "T-0002")) is None
    assert asyncio.run(store.find("req-1", TRAVELER.id)) is not None
    with pytest.raises(BookingRefused):
        asyncio.run(store.create(_new(traveler_id="T-0002")))
    other = asyncio.run(store.create(_new("req-2", traveler_id="T-0002")))
    assert store.listed("T-0002") == (other,)
    assert other not in store.listed(TRAVELER.id)

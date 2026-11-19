"""A flight source and a directory for the lean tools' tests of the real network, with no
network: `FakeFlightData` answers each day by its query's key (`OfferQuery.key()`), raising
what it is told to raise and counting its calls; `FakePlaces` names a few cities and takes a
bare code as the model passes one. Builders make the carriers, segments and offers."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable
from datetime import UTC, date, datetime, timedelta
from typing import Any, Final

from flight_voice.flight_data.fanout import span_of
from flight_voice.flight_data.model import Carrier, Layover, Money, Offer, Place, Segment, offer_id
from flight_voice.flight_data.port import FlightDataUnavailableError
from flight_voice.flight_data.queries import DayFares, DayOffers, OfferQuery, SpanQuery
from t2_agentic_voice.languages import normalize_arabic

AT: Final = datetime(2026, 11, 18, 9, 0, tzinfo=UTC)
SAUDIA: Final = Carrier(code="SV", name_en="Saudia", name_ar="السعودية", aliases=("السعودي",))
FLYNAS: Final = Carrier(code="XY", name_en="flynas", name_ar="طيران ناس", aliases=("fly nas",))
FLYADEAL: Final = Carrier(code="F3", name_en="flyadeal", name_ar="طيران أديل")
EMIRATES: Final = Carrier(code="EK", name_en="Emirates", name_ar="طيران الإمارات")
BRITISH: Final = Carrier(code="BA", name_en="British Airways", name_ar="الخطوط البريطانية")
QATAR: Final = Carrier(code="QR", name_en="Qatar Airways", name_ar="القطرية")
RIYADH: Final = Place(code="RUH", airports=("RUH",), city_en="Riyadh", city_ar="الرياض")
JEDDAH: Final = Place(code="JED", airports=("JED",), city_en="Jeddah", city_ar="جدة")
DUBAI: Final = Place(code="DXB", airports=("DXB", "DWC"), city_en="Dubai", city_ar="دبي")
DOHA: Final = Place(code="DOH", airports=("DOH",), city_en="Doha", city_ar="الدوحة")
ULA: Final = Place(code="ULH", airports=("ULH",), city_en="Al-Ula", city_ar="العلا")
LONDON: Final = Place(
    code="LHR", airports=("LHR", "LGW", "STN"), city_en="London", city_ar="لندن", country="GB"
)
PLACES: Final = (RIYADH, JEDDAH, DUBAI, DOHA, ULA, LONDON)


def segment(
    carrier: Carrier,
    number: str,
    route: tuple[str, str],
    departs: datetime,
    minutes: int,
    **more: Any,
) -> Segment:
    """One flight, `minutes` long, landing that many minutes later in local time."""
    return Segment(
        carrier=carrier,
        number=number,
        origin=route[0],
        destination=route[1],
        departs=departs,
        arrives=departs + timedelta(minutes=minutes),
        minutes=minutes,
        **more,
    )


def offer(*segments: Segment, price: int, adults: int = 1, **more: Any) -> Offer:
    """An offer of `segments` at `price` for all its `adults`: its whole time the flights' and
    the layovers' minutes."""
    layovers: tuple[Layover, ...] = more.pop("layovers", ())
    minutes = sum(s.minutes for s in segments) + sum(w.minutes for w in layovers)
    return Offer(
        id=offer_id(segments),
        segments=segments,
        layovers=layovers,
        minutes=more.pop("minutes", minutes),
        cabin=more.pop("cabin", "economy"),
        adults=adults,
        price=Money(amount=price),
        fetched_at=AT,
        **more,
    )


def nonstop(
    carrier: Carrier,
    number: str,
    route: tuple[str, str],
    departs: datetime,
    minutes: int,
    price: int,
    **more: Any,
) -> Offer:
    """A nonstop offer of one flight."""
    aircraft = more.pop("aircraft", None)
    return offer(
        segment(carrier, number, route, departs, minutes, aircraft=aircraft), price=price, **more
    )


def answered(q: OfferQuery, offers: Iterable[Offer] = (), **more: Any) -> DayOffers:
    """The source's answer to `q`: `ok` with its offers in departure order, else `no_flights`."""
    held = tuple(sorted(offers, key=lambda o: (o.departs, o.id)))
    status = more.pop("status", "ok" if held else "no_flights")
    return DayOffers(query=q, status=status, offers=held, fetched_at=AT, **more)


def query(origin: Place, destination: Place, day: date, **more: Any) -> OfferQuery:
    return OfferQuery(origin=origin, destination=destination, day=day, **more)


Answer = DayOffers | FlightDataUnavailableError


class FakeFlightData:
    """Answers by query key (`answers`); a key with none is `no_flights`; an error is raised.
    `calls` counts each method's calls; `during`, when set, is awaited inside each `day`, as a
    slow source lets another tool run meanwhile."""

    name = "fake"
    span_days = 14

    def __init__(
        self,
        answers: dict[str, Answer] | None = None,
        *,
        spans: dict[str, DayFares | FlightDataUnavailableError] | None = None,
        near: tuple[date, ...] = (),
    ) -> None:
        self.answers: dict[str, Answer] = dict(answers or {})
        self.spans = dict(spans or {})
        self.near = near
        self.calls: dict[str, int] = {"day": 0, "days": 0, "nearest": 0}
        self.during: Callable[[], Awaitable[None]] | None = None

    def last_day(self, today: date) -> date:
        return today + timedelta(days=330)

    def set(self, answer: Answer, key: str | None = None) -> None:
        """`answer` given from now for its query's key (or `key`)."""
        if key is None:
            assert isinstance(answer, DayOffers)
            key = answer.query.key()
        self.answers[key] = answer

    async def day(self, q: OfferQuery) -> DayOffers:
        self.calls["day"] += 1
        if self.during is not None:
            await self.during()
        found = self.answers.get(q.key())
        if isinstance(found, FlightDataUnavailableError):
            raise found
        return found if found is not None else answered(q)

    async def days(self, q: SpanQuery) -> DayFares:
        self.calls["days"] += 1
        if q.each_day:  # day by day, as the live source reads such a span
            return await span_of(self.day, q, span_days=self.span_days, concurrency=4, deadline_s=5)
        found = self.spans.get(f"{q.origin.code}-{q.destination.code}")
        if isinstance(found, FlightDataUnavailableError):
            raise found
        assert found is not None, "no span answer given"
        return found

    async def nearest(self, q: OfferQuery, today: date) -> tuple[date, ...]:
        self.calls["nearest"] += 1
        return self.near

    async def aclose(self) -> None:
        pass


class FakePlaces:
    """A few cities by their English, Arabic or code names, Riyadh the home; a bare code passed
    as three capital letters is a place the directory lacks."""

    served = None
    home = RIYADH

    def __init__(self, places: Iterable[Place] = PLACES) -> None:
        self._by: dict[str, Place] = {}
        for place in places:
            for name in (place.city_en, place.city_ar, *place.airports):
                self._by[normalize_arabic(name).lower()] = place

    def find(self, said: str) -> Place | None:
        found = self._by.get(normalize_arabic(said).strip().lower())
        if found is not None:
            return found
        try:
            return Place.bare(said)
        except ValueError:
            return None

    def get(self, code: str) -> Place | None:
        return self._by.get(code.lower())

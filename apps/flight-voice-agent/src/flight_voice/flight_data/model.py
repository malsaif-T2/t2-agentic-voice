"""The flights a source answers, as the lean agent reads them: places, carriers, the segments of
an offer, its layovers and its price in Saudi riyals, the same for every source (the mock, the
recorded answers, SerpApi).

Times are each airport's local time as the source gives it, with no zone (no zone database
here): `departs` and `arrives` are naive, and `minutes` says how long a flight takes. An
offer's id follows its carrier's flight numbers and its first day (`SV1020-2026-11-19`,
`SV3079+SV8607-2026-11-19`), so the same flights searched again give the same id. Its `price` is
for all its `adults`, for that leg alone, never per person worked out here.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from datetime import UTC, date, datetime
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from flight_voice.airline.airports import Register
from flight_voice.airline.schedule import Cabin

__all__ = [
    "IATA",
    "Cabin",
    "Carrier",
    "CarrierCode",
    "Layover",
    "Money",
    "Offer",
    "Place",
    "Register",
    "Segment",
    "aware_utc",
    "has_seats",
    "offer_id",
]

IATA = Annotated[str, Field(pattern=r"^[A-Z]{3}$")]
# Two letters or digits: "SV", "F3", "6E", and the mock's "T2".
CarrierCode = Annotated[str, Field(pattern=r"^[A-Z0-9]{2}$")]
_BARE = re.compile(r"[A-Z]{3}")


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Place(_Frozen):
    """A city, or one airport, as the caller names it: `code` is its main airport (said, logged,
    used in keys), first of `airports`, which are searched together (London: LHR, LGW, STN).
    `known` is false for a bare code the directory lacks, whose names are the code itself."""

    code: IATA
    airports: tuple[IATA, ...] = Field(min_length=1, max_length=4)
    city_en: str = Field(min_length=1)
    city_ar: str = Field(min_length=1)
    name_en: str | None = None
    name_ar: str | None = None
    country: str | None = Field(default=None, pattern=r"^[A-Z]{2}$")
    aliases: tuple[str, ...] = ()
    known: bool = True

    @model_validator(mode="after")
    def _code_first(self) -> Self:
        if self.airports[0] != self.code:
            raise ValueError("a place's code is the first of its airports")
        if len(set(self.airports)) != len(self.airports):
            raise ValueError("a place lists each airport once")
        return self

    def city(self, register: Register) -> str:
        """The city's name alone, in the register's script."""
        return self.city_en if register == "en" else self.city_ar

    def to_city(self, register: Register) -> str:
        """ "To" the city: «للندن» in Saudi (a name with «ال» takes «لل»: «للرياض»), «إلى لندن»
        in MSA, "to London" in English."""
        if register == "en":
            return f"to {self.city_en}"
        if register == "msa":
            return f"إلى {self.city_ar}"
        bare = self.city_ar.removeprefix("ال")
        return f"لل{bare}" if bare != self.city_ar else f"ل{self.city_ar}"

    def from_city(self, register: Register) -> str:
        """ "From" the city: «من لندن» in both Arabic registers, "from London" in English."""
        return f"from {self.city_en}" if register == "en" else f"من {self.city_ar}"

    @classmethod
    def bare(cls, code: str) -> Place:
        """A code the directory lacks, as the model passes it: exactly three capital letters,
        its city named by the code itself and `known` false. Anything else is refused, so a word
        a caller said never becomes an airport."""
        if not _BARE.fullmatch(code):
            raise ValueError("a bare place is exactly three capital letters")
        return cls(code=code, airports=(code,), city_en=code, city_ar=code, known=False)


class Carrier(_Frozen):
    """An airline: its code (the flight number's prefix), its names in English and Arabic, and
    the other names a caller may give it."""

    code: CarrierCode
    name_en: str = Field(min_length=1)
    name_ar: str = Field(min_length=1)
    aliases: tuple[str, ...] = ()

    def name(self, register: Register) -> str:
        """The airline's name in the register's script."""
        return self.name_en if register == "en" else self.name_ar


class Segment(_Frozen):
    """One flight of an offer: its marketing carrier (from the flight number's prefix), its
    number, its airports, its local times (naive), how long it takes, its aircraft, whether it
    is a road leg by bus (Saudia's RUH-ELQ), and the carrier that flies it when another does."""

    carrier: Carrier
    number: str = Field(pattern=r"^\d{1,4}[A-Z]?$")
    origin: IATA
    destination: IATA
    departs: datetime
    arrives: datetime
    minutes: int = Field(gt=0)
    aircraft: str | None = None
    bus: bool = False
    operated_by: Carrier | None = None

    @field_validator("departs", "arrives")
    @classmethod
    def _local(cls, value: datetime) -> datetime:
        if value.tzinfo is not None:
            raise ValueError("a segment's times are the airport's local time, with no zone")
        return value

    @property
    def code(self) -> str:
        """The flight's code as an id holds it: "SV1020"."""
        return f"{self.carrier.code}{self.number}"

    @property
    def flight(self) -> str:
        """The flight as it is written: "SV 1020"."""
        return f"{self.carrier.code} {self.number}"


class Layover(_Frozen):
    """A wait between two segments: the airport, how long, whether it runs overnight, and the
    airport's name as the source gives it."""

    airport: IATA
    minutes: int = Field(ge=0)
    overnight: bool = False
    name: str | None = None


class Money(_Frozen):
    """An amount in whole Saudi riyals (SerpApi's itinerary price is a whole number)."""

    amount: int = Field(ge=0)
    currency: Literal["SAR"] = "SAR"


def aware_utc(value: datetime) -> datetime:
    """`value` in UTC; a time with no zone is refused (when a source answered is an instant)."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("fetched_at is an aware time")
    return value.astimezone(UTC)


def offer_id(segments: Iterable[Segment]) -> str:
    """The id of an offer of these flights: their codes joined by "+", then "-" and the first
    departure's local date ("SV3079+SV8607-2026-11-19"). At most 34 characters for 3
    segments."""
    flights = tuple(segments)
    if not flights:
        raise ValueError("an offer has at least one segment")
    return "+".join(s.code for s in flights) + "-" + flights[0].departs.date().isoformat()


class Offer(_Frozen):
    """One way to fly a leg on a day: its segments in order, the layovers between them, the
    whole time (flights plus layovers), the cabin, the travelers, the price for all of them for
    this leg alone, the seats left (None when the source does not say; SerpApi never does) and
    when the source answered (aware, in UTC). Its id is `offer_id(segments)`."""

    id: str = Field(max_length=40)
    segments: tuple[Segment, ...] = Field(min_length=1, max_length=3)
    layovers: tuple[Layover, ...] = ()
    minutes: int = Field(gt=0)
    cabin: Cabin
    adults: int = Field(ge=1, le=9)
    price: Money
    seats_left: int | None = Field(default=None, ge=0)
    fetched_at: datetime

    @field_validator("fetched_at")
    @classmethod
    def _utc(cls, value: datetime) -> datetime:
        return aware_utc(value)

    @model_validator(mode="after")
    def _its_id(self) -> Self:
        if self.id != offer_id(self.segments):
            raise ValueError("an offer's id is its flights' codes and its first day")
        return self

    @property
    def carrier(self) -> Carrier:
        """The first segment's marketing carrier."""
        return self.segments[0].carrier

    @property
    def carriers(self) -> tuple[Carrier, ...]:
        """Each marketing carrier once, in the order of the segments."""
        seen: dict[str, Carrier] = {}
        for segment in self.segments:
            seen.setdefault(segment.carrier.code, segment.carrier)
        return tuple(seen.values())

    @property
    def stops(self) -> int:
        """The connections on the way: 0 for a nonstop."""
        return len(self.segments) - 1

    @property
    def nonstop(self) -> bool:
        return self.stops == 0

    @property
    def origin(self) -> str:
        return self.segments[0].origin

    @property
    def destination(self) -> str:
        return self.segments[-1].destination

    @property
    def departs(self) -> datetime:
        """The first departure, in its airport's local time."""
        return self.segments[0].departs

    @property
    def arrives(self) -> datetime:
        """The last arrival, in its airport's local time."""
        return self.segments[-1].arrives

    @property
    def day(self) -> date:
        """The local day the offer leaves."""
        return self.departs.date()

    @property
    def next_day(self) -> bool:
        """Whether it lands on a later local date than it leaves."""
        return self.arrives.date() > self.departs.date()

    @property
    def flights(self) -> tuple[str, ...]:
        """Its flights as they are written: ("SV 3079", "SV 8607")."""
        return tuple(s.flight for s in self.segments)

    @property
    def bus(self) -> bool:
        """Whether any segment is a road leg by bus."""
        return any(s.bus for s in self.segments)


def has_seats(offer: Offer, travelers: int) -> bool:
    """Whether the offer seats `travelers`: true when the source does not count seats."""
    return offer.seats_left is None or offer.seats_left >= travelers

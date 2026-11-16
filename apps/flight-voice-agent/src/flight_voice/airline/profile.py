"""The demo traveler, the caller of every call (a fictional person): their tier, home airport and
preferred cabin, the five trips they flew before today, and the counts a caller may ask about,
worked out in code so the talker never counts (`insights`).

Each past trip's reference is six digits, so the output guard's ID rule keeps it unsaid unless
a result of the call holds it. Arabic is written plainly, as Ole5's data modules do.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from datetime import date
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field

from flight_voice.airline.airports import HOME, Code
from flight_voice.airline.schedule import Cabin

Tier = Literal["Blue", "Silver", "Gold"]
TIER_AR: Final[dict[Tier, str]] = {"Blue": "أزرق", "Silver": "فضي", "Gold": "ذهبي"}


class Traveler(BaseModel):
    """The traveler a call books for: who they are, and the defaults of their trips."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    name_en: str
    name_ar: str
    first_en: str
    first_ar: str
    tier: Tier
    home: Code = HOME
    preferred_cabin: Cabin = "economy"

    @property
    def tier_ar(self) -> str:
        """The tier's name in Arabic."""
        return TIER_AR[self.tier]


class Trip(BaseModel):
    """A trip as the traveler's history holds it: its reference, route, dates, travelers,
    cabin and total in Saudi riyals."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    reference: str = Field(pattern=r"^\d{6}$")
    origin: Code
    destination: Code
    depart: date
    return_date: date | None = None
    travelers: int = Field(ge=1, le=9)
    cabin: Cabin
    total_sar: int = Field(ge=0)

    @property
    def city(self) -> Code:
        """The trip's city that is not the traveler's home."""
        return self.destination if self.origin == HOME else self.origin


TRAVELER: Final = Traveler(
    id="T-0001",
    name_en="Khalid Al-Harbi",
    name_ar="خالد الحربي",
    first_en="Khalid",
    first_ar="خالد",
    tier="Gold",
)

PAST_TRIPS: Final = (
    Trip(
        reference="482913",
        origin="RUH",
        destination="DXB",
        depart=date(2026, 10, 8),
        return_date=date(2026, 10, 11),
        travelers=1,
        cabin="economy",
        total_sar=1380,
    ),
    Trip(
        reference="517204",
        origin="RUH",
        destination="LHR",
        depart=date(2026, 9, 3),
        return_date=date(2026, 9, 14),
        travelers=1,
        cabin="business",
        total_sar=15640,
    ),
    Trip(
        reference="390655",
        origin="RUH",
        destination="JED",
        depart=date(2026, 8, 20),
        return_date=date(2026, 8, 23),
        travelers=2,
        cabin="economy",
        total_sar=1720,
    ),
    Trip(
        reference="604118",
        origin="RUH",
        destination="CAI",
        depart=date(2026, 6, 12),
        travelers=1,
        cabin="economy",
        total_sar=1040,
    ),
    Trip(
        reference="275930",
        origin="RUH",
        destination="DXB",
        depart=date(2026, 3, 19),
        return_date=date(2026, 3, 22),
        travelers=1,
        cabin="economy",
        total_sar=1450,
    ),
)


class CityCount(BaseModel):
    """How many trips went to a city, and when the last one left."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    city: Code
    trips: int
    last_depart: date


class Insights(BaseModel):
    """The counts a caller may ask about, worked out in code: trips in all, by city (most
    first, then by the last trip, newest first), the most visited city and the cabin used most."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    trips: int
    by_city: tuple[CityCount, ...]
    most_visited: Code | None
    cabin_most_used: Cabin | None


def insights(trips: Iterable[Trip]) -> Insights:
    """The counts of `trips`. A tie for the most visited city or the cabin used most goes to
    the one flown last."""
    kept = sorted(trips, key=lambda t: t.depart, reverse=True)
    counts = Counter(t.city for t in kept)
    last: dict[Code, date] = {}
    for trip in kept:
        last.setdefault(trip.city, trip.depart)
    by_city = tuple(
        CityCount(city=c, trips=n, last_depart=last[c])
        for c, n in sorted(counts.items(), key=lambda item: (-item[1], -last[item[0]].toordinal()))
    )
    cabins = Counter(t.cabin for t in kept)
    cabin = cabins.most_common(1)[0][0] if cabins else None  # the first seen wins a tie
    return Insights(
        trips=len(kept),
        by_city=by_city,
        most_visited=by_city[0].city if by_city else None,
        cabin_most_used=cabin,
    )

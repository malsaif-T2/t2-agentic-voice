"""What the booking holds (`BookingDraft`) and what it gives back (`BookingMade`).

**The talker fills none of the draft.** It calls `book_trip` with `{}`: every field is hidden
from the schema it sees (pydantic's `SkipJsonSchema`), each with a default, and the action's
`validate` always replaces every one of them from the call's trip draft (`filled`), so a value
the talker sends under a field's name never survives to the read-back or the write. The fields
are the trip's legs (each flight and its day), one way or not, the travelers, the cabin (a fixed
value with its `Spoken` labels), the total priced at the read-back, and the read-back's said
parts in each wording the call may read it in: Saudi (`*_ar_sa`), MSA (`*_ar`) and English
(`*_en`), each rendered in code from the airline's data (said/numbers.py, said/words.py),
never from the talker's words.

**The write books from the draft's own fields**, what was read back, never from the live trip
draft (`legs`). **The result** holds the booking's reference, which `done` never says (the
caller hears it only when they ask), its total, and the city and day `done` says in each
wording.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Final

from pydantic import BaseModel, ConfigDict, Field
from pydantic.json_schema import SkipJsonSchema
from t2_agentic_voice import Spoken

from flight_voice.airline.airports import AIRPORTS, Code, Register
from flight_voice.airline.bookings import Booking, Leg
from flight_voice.airline.schedule import CABINS, Cabin, find_flight
from flight_voice.said import words
from flight_voice.said.numbers import speak_amount, speak_date, speak_time, speak_travelers
from flight_voice.trip import TripDraft

# The name the talker calls the booking by.
BOOK_TRIP: Final = "book_trip"
# Each cabin as the read-back says it; MSA says the Saudi label, which it says alike.
CABIN_LABELS: Final = {
    cabin: {"ar-SA": words.cabin(cabin, "saudi"), "en": words.cabin(cabin, "en")}
    for cabin in CABINS
}
SpokenCabin = Annotated[Cabin, Spoken(CABIN_LABELS)]
# The wordings a line is read in, by the suffix of the fields that hold it, and their registers.
WORDINGS: Final[dict[str, Register]] = {"ar_sa": "saudi", "ar": "msa", "en": "en"}
_SAID: Final = ("trip_kind", "route", "outbound", "return", "party", "total")


class NotFilledError(ValueError):
    """The draft was never filled from a trip: no write may go out from it."""


class BookingDraft(BaseModel):
    """A booking, filled by `validate` from the trip draft (the module's docstring)."""

    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

    outbound_flight: SkipJsonSchema[int] = 0
    outbound_date: SkipJsonSchema[date | None] = None
    return_flight: SkipJsonSchema[int | None] = None
    return_date: SkipJsonSchema[date | None] = None
    one_way: SkipJsonSchema[bool] = False
    travelers: SkipJsonSchema[int] = Field(default=1, ge=1, le=9)
    cabin: SkipJsonSchema[SpokenCabin] = "economy"
    total_sar: SkipJsonSchema[int] = Field(default=0, ge=0)
    trip_kind_ar_sa: SkipJsonSchema[str] = ""
    trip_kind_ar: SkipJsonSchema[str] = ""
    trip_kind_en: SkipJsonSchema[str] = ""
    route_ar_sa: SkipJsonSchema[str] = ""
    route_ar: SkipJsonSchema[str] = ""
    route_en: SkipJsonSchema[str] = ""
    outbound_ar_sa: SkipJsonSchema[str] = ""
    outbound_ar: SkipJsonSchema[str] = ""
    outbound_en: SkipJsonSchema[str] = ""
    return_ar_sa: SkipJsonSchema[str] = ""
    return_ar: SkipJsonSchema[str] = ""
    return_en: SkipJsonSchema[str] = ""
    party_ar_sa: SkipJsonSchema[str] = ""
    party_ar: SkipJsonSchema[str] = ""
    party_en: SkipJsonSchema[str] = ""
    total_ar_sa: SkipJsonSchema[str] = ""
    total_ar: SkipJsonSchema[str] = ""
    total_en: SkipJsonSchema[str] = ""

    def legs(self) -> tuple[Leg] | tuple[Leg, Leg]:
        """The legs the read-back said: out, and back on a round trip; `NotFilledError` for a
        draft no trip filled."""
        if not self.outbound_flight or self.outbound_date is None or not self.total_sar:
            raise NotFilledError("the booking's draft was never filled from a trip")
        out = Leg(flight=self.outbound_flight, day=self.outbound_date)
        if self.one_way:
            return (out,)
        if self.return_flight is None or self.return_date is None:
            raise NotFilledError("the booking's draft was never filled from a trip")
        return (out, Leg(flight=self.return_flight, day=self.return_date))


def _departs(leg: Leg) -> tuple[Code, Code, str, str, str]:
    """The leg's origin, destination and its departure time in each register."""
    flight = find_flight(leg.flight)
    if flight is None:
        raise NotFilledError("a chosen flight is not in the timetable")
    at = flight.departs
    saudi, msa, english = speak_time(at, "saudi"), speak_time(at, "msa"), speak_time(at, "en")
    return flight.origin, flight.destination, saudi, msa, english


def _outbound(leg: Leg) -> dict[str, str]:
    _, _, saudi, msa, english = _departs(leg)
    return {
        "ar_sa": f"{speak_date(leg.day, 'saudi')} تطلع {saudi}",
        "ar": f"يوم {speak_date(leg.day, 'msa')} تقلع {msa}",
        "en": f"{speak_date(leg.day, 'en')} at {english}",
    }


def _back(leg: Leg | None) -> dict[str, str]:
    """The return as the read-back says it after the outbound, or nothing on a one-way trip."""
    if leg is None:
        return dict.fromkeys(WORDINGS, "")
    origin, _, saudi, msa, english = _departs(leg)
    start = AIRPORTS[origin]
    saudi_day, msa_day, english_day = (speak_date(leg.day, r) for r in ("saudi", "msa", "en"))
    return {
        "ar_sa": f"، والرجعة {saudi_day} تطلع {start.from_city('saudi')} {saudi}",
        "ar": f"، والعودة يوم {msa_day} تقلع {start.from_city('msa')} {msa}",
        "en": f", back on {english_day} at {english} {start.from_city('en')}",
    }


def filled(trip: TripDraft, total: int) -> BookingDraft:
    """The booking of `trip`, every leg chosen and priced at `total` (the module's docstring);
    `NotFilledError` for a trip with a leg not chosen."""
    if trip.destination is None or trip.missing():
        raise NotFilledError("the trip has a leg not chosen")
    out, back = trip.chosen_outbound, None if trip.one_way else trip.chosen_return
    if out is None:
        raise NotFilledError("the trip has a leg not chosen")
    parts: dict[str, dict[str, str]] = {
        "trip_kind": {s: words.trip_kind(trip.one_way, r) for s, r in WORDINGS.items()},
        "route": {s: words.route(trip.origin, trip.destination, r) for s, r in WORDINGS.items()},
        "outbound": _outbound(out),
        "return": _back(back),
        "party": {s: speak_travelers(trip.travelers, r) for s, r in WORDINGS.items()},
        "total": {s: speak_amount(total, r) for s, r in WORDINGS.items()},
    }
    said = {f"{name}_{suffix}": parts[name][suffix] for name in _SAID for suffix in WORDINGS}
    return BookingDraft(
        outbound_flight=out.flight,
        outbound_date=out.day,
        return_flight=None if back is None else back.flight,
        return_date=None if back is None else back.day,
        one_way=trip.one_way,
        travelers=trip.travelers,
        cabin=trip.cabin,
        total_sar=total,
        **said,
    )


class BookingMade(BaseModel):
    """A booking the airline made: its reference, its total, and the city it goes to and the
    day it leaves, as `done` says them in each wording."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    reference: str
    total_sar: int
    city_ar_sa: str
    city_ar: str
    city_en: str
    when_ar_sa: str
    when_ar: str
    when_en: str

    @classmethod
    def of(cls, booking: Booking) -> BookingMade:
        """The result for `booking`."""
        end = AIRPORTS[booking.destination]
        return cls(
            reference=booking.reference,
            total_sar=booking.total_sar,
            city_ar_sa=end.to_city("saudi"),
            city_ar=end.to_city("msa"),
            city_en=end.to_city("en"),
            when_ar_sa=f"يوم {speak_date(booking.depart, 'saudi')}",
            when_ar=f"يوم {speak_date(booking.depart, 'msa')}",
            when_en=f"on {speak_date(booking.depart, 'en')}",
        )

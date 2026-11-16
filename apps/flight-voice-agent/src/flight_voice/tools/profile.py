"""`traveler_profile`: the caller's travel profile, with every count already worked out.

The traveler is the call's verified caller (`from_caller("attributes.traveler_id")`), hidden
from the talker: nothing said in the call changes whose profile is read (invariant 3). The
result gives the tier, the home airport, the preferred cabin, the trips flown and the bookings
made since, each with its city, kind, dates, travelers, cabin, total and reference, and the
counts a caller may ask about (trips in all, by city, the most visited city, the cabin used
most), so the talker never counts. The `say` keeps a past trip said as one they flew, and a
reference unsaid unless asked.

It has no `reports_on`: the profile is full of six-digit references and totals, so as a status
result it would let "I've booked it" pass beside a past reference with no booking made (D-081).
A profile that does not load is a `ToolError` that says so, never "no trips".
"""

from __future__ import annotations

from typing import Final, Literal

from t2_agentic_voice import CallContext, Tool, ToolError, ToolResult, from_caller, tool

from flight_voice.airline.airports import airport
from flight_voice.airline.bookings import Booking
from flight_voice.airline.profile import Tier
from flight_voice.airline.system import Airline, AirlineUnavailableError
from flight_voice.said import Tag, arabic, register, words
from flight_voice.tools.results import PROFILE_FAILED, SAY, _Result, result, said

TRAVELER_PROFILE: Final = "traveler_profile"
DESCRIPTION: Final = (
    "Read the caller's travel profile: tier, home airport, preferred cabin, past trips and "
    "bookings made today, with counts already worked out. Call it for any question about their "
    "past trips, bookings or tier, and when they want the same trip as last time."
)
TRAVELER_FIELD: Final = "attributes.traveler_id"
PROFILE_UNKNOWN: Final = (
    "No travel profile is known for this caller. Tell the caller you cannot open their travel "
    "history on this line. Do not say they have no trips or no bookings."
)


class TripSaid(_Result):
    """A trip flown or booked: its reference, its city and kind said, its dates by their ISO
    form with the departure's month said, its travelers, cabin and total."""

    reference: str
    city_said: str
    trip_kind_said: str
    trip_kind_said_msa: str | None = None
    depart: str
    month_said: str
    return_date: str | None = None
    travelers: int
    cabin: str
    total_sar: int


class CityTrips(_Result):
    """How many trips went to a city, and when the last one left."""

    city_said: str
    trips: int
    last_depart: str
    last_month_said: str


class ProfileAnswer(_Result):
    """The caller's profile (the module's docstring)."""

    status: Literal["ok"] = "ok"
    first_name: str
    tier: Tier
    tier_said: str
    home_said: str
    preferred_cabin_said: str
    trips_flown: int
    by_city: tuple[CityTrips, ...]
    most_visited_said: str | None = None
    cabin_most_used_said: str | None = None
    flown: tuple[TripSaid, ...]
    booked: tuple[TripSaid, ...]
    say: str = SAY["profile"]


def trip_said(trip: Booking, tag: Tag) -> TripSaid:
    """A trip as the profile gives it, in the reply's language."""
    r = register(tag)
    kind, kind_msa = said(lambda g: words.trip_kind(trip.return_date is None, g), tag)
    return TripSaid(
        reference=trip.reference,
        city_said=airport(trip.city).city(r),
        trip_kind_said=kind,
        trip_kind_said_msa=kind_msa,
        depart=trip.depart.isoformat(),
        month_said=words.month(trip.depart.month, r),
        return_date=None if trip.return_date is None else trip.return_date.isoformat(),
        travelers=trip.travelers,
        cabin=words.cabin(trip.cabin, r),
        total_sar=trip.total_sar,
    )


def traveler_profile(airline: Airline) -> Tool:
    """The verified caller's profile over `airline` (the module's docstring)."""

    @tool(
        name=TRAVELER_PROFILE,
        description=DESCRIPTION,
        bind={"traveler": from_caller(TRAVELER_FIELD)},
    )
    async def read(ctx: CallContext, traveler: str) -> ToolResult:
        tag: Tag = ctx.language
        r = register(tag)
        try:
            found = await airline.profile(traveler)
        except AirlineUnavailableError:
            raise ToolError(PROFILE_FAILED) from None
        if found is None:
            raise ToolError(PROFILE_UNKNOWN)
        who, counts = found.traveler, found.insights
        most = counts.most_visited
        used = counts.cabin_most_used
        answer = ProfileAnswer(
            first_name=who.first_ar if arabic(tag) else who.first_en,
            tier=who.tier,
            tier_said=who.tier_ar if arabic(tag) else who.tier,
            home_said=airport(who.home).city(r),
            preferred_cabin_said=words.cabin(who.preferred_cabin, r),
            trips_flown=counts.trips,
            by_city=tuple(
                CityTrips(
                    city_said=airport(c.city).city(r),
                    trips=c.trips,
                    last_depart=c.last_depart.isoformat(),
                    last_month_said=words.month(c.last_depart.month, r),
                )
                for c in counts.by_city
            ),
            most_visited_said=None if most is None else airport(most).city(r),
            cabin_most_used_said=None if used is None else words.cabin(used, r),
            flown=tuple(trip_said(t, tag) for t in found.flown),
            booked=tuple(trip_said(t, tag) for t in found.booked),
        )
        return result(answer)

    return read

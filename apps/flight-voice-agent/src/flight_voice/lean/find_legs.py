"""One leg of `find_flights` from a source's answer (`DayOffers`): the airline the caller asked
for, then the pool and the listing (listing.py), as the model and the draft hold them.

**The airline filter** runs first, over all the day's offers: the name the model passed (in any
language, or the airline's code) is matched against each airline flying that day, its code, its
names and its aliases, the generic words ("air", "airlines", «طيران», «الخطوط» …) set aside; an
exact match wins. No airline matched is `no_flights_for_airline`, with the airlines that do fly
the day; two or more `which_airline`, with them. Then the pool and the listing, so `count`,
`airlines` and `more` are over the pool, never over the raw answer.

The refusals are here too: a day with no flight (`no_flights`, with the nearest days that have
one, or a note when they were not checked), a route the mock does not serve (`not_served`, with
the cities it serves), and a place the directory does not know (`unknown_place`).
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Final, Literal

from pydantic import JsonValue
from t2_agentic_voice import ToolResult
from t2_agentic_voice.languages import normalize_arabic

from flight_voice.flight_data.model import Carrier, Offer, Place
from flight_voice.flight_data.port import FlightData, FlightDataUnavailableError, Places
from flight_voice.flight_data.queries import DayOffers, OfferQuery
from flight_voice.lean.draft import Listed
from flight_voice.lean.listing import by_airline, listed, pool
from flight_voice.lean.results import LegList, day_of, lean_result, leg_list, option_of
from flight_voice.said import Tag, register

__all__ = [
    "NOT_CHECKED",
    "NOT_SERVED",
    "UNKNOWN_PLACE",
    "Built",
    "both_legs",
    "built",
    "named",
    "nearest",
    "no_flights",
    "not_served",
    "refused_answer",
    "unknown_place",
]

NOT_SERVED: Final = "Every flight starts or ends in Riyadh."
NOT_CHECKED: Final = "The nearest days were not checked: offer another day."
UNKNOWN_PLACE: Final = "Ask the caller for the city again, or its airport."
# Words an airline's name may hold that name no airline alone, normalized.
_GENERIC: Final = frozenset(
    normalize_arabic(w)
    for w in ("طيران", "الخطوط", "خطوط", "air", "airlines", "airline", "airways", "flight", "fly")
)
_WORD: Final = re.compile(r"\w+")


@dataclass(frozen=True)
class Built:
    """One leg as the model reads it (`data`) and as the draft keeps it (`listed`)."""

    data: LegList
    listed: Listed


def _words(text: str) -> tuple[str, ...]:
    return tuple(_WORD.findall(normalize_arabic(text).lower()))


def _names(carrier: Carrier) -> tuple[str, ...]:
    return (carrier.code, carrier.name_en, carrier.name_ar, *carrier.aliases)


def _match(carrier: Carrier, said: str) -> Literal["exact", "near"] | None:
    """How `said` names `carrier`: exactly (a name or the code, whole), near (its words beyond
    the generic ones, of three letters or more, all in one of its names), or not at all."""
    wanted = _words(said)
    if any(_words(name) == wanted for name in _names(carrier)):
        return "exact"
    core = [w for w in wanted if w not in _GENERIC]
    if not core or any(len(w) < 3 for w in core):
        return None
    for name in _names(carrier):
        held = [w for w in _words(name) if w not in _GENERIC]
        if held == core or set(core) <= set(held):
            return "near"
    return None


def _carriers(offers: Iterable[Offer]) -> dict[str, Carrier]:
    found: dict[str, Carrier] = {}
    for offer in sorted(offers, key=lambda o: (o.departs, o.id)):
        for carrier in offer.carriers:
            found.setdefault(carrier.code, carrier)
    return found


def by_name(
    offers: Sequence[Offer], airline: str, tag: Tag
) -> tuple[Offer, ...] | dict[str, JsonValue]:
    """The offers of the airline `airline` names, or the refusal as data (the module's
    docstring)."""
    flying = _carriers(offers)
    matched = {code: _match(c, airline) for code, c in flying.items()}
    exact = [code for code, how in matched.items() if how == "exact"]
    near = [code for code, how in matched.items() if how == "near"]
    chosen = exact or near
    r = register(tag)
    names: list[JsonValue] = [flying[c].name(r) for c in (chosen if chosen else flying)]
    if not chosen:
        return {"status": "no_flights_for_airline", "airline": airline, "airlines": names}
    if len(chosen) > 1:
        return {"status": "which_airline", "airlines": names}
    (code,) = chosen
    return tuple(o for o in offers if code in {c.code for c in o.carriers})


def built(
    answer: DayOffers, *, airline: str | None, tag: Tag, travelers: int, places: Places
) -> Built | dict[str, JsonValue]:
    """One leg from `answer` (status ok), narrowed to `airline` when given: the module's
    docstring; the airline filter's refusal as data."""
    offers: Sequence[Offer] = answer.offers
    if airline is not None:
        narrowed = by_name(offers, airline, tag)
        if isinstance(narrowed, dict):
            return narrowed
        offers = narrowed
    held = pool(offers)
    shown = listed(held)
    options = tuple(option_of(o, tag, travelers, places.get) for o in shown)
    data = leg_list(answer.query.day, options, tag, count=len(held), airlines=by_airline(held, tag))
    return Built(data, Listed(day=answer.query.day, offers=shown, pool=held, airline=airline))


def no_flights(day: date, nearest: Sequence[date], tag: Tag) -> ToolResult:
    """A day with no flight, and the nearest days that have one; a note when none was
    checked."""
    near: list[JsonValue] = [day_of(n, tag).model_dump() for n in nearest]
    answer: dict[str, JsonValue] = {"status": "no_flights", "day": day.isoformat(), "nearest": near}
    return lean_result(answer if nearest else answer | {"note": NOT_CHECKED})


def not_served(places: Places, tag: Tag) -> ToolResult:
    """A city or a route the mock does not fly, with the cities it serves."""
    r = register(tag)
    cities = [p.city(r) for code in places.served or () if (p := places.get(code)) is not None]
    joint = " and " if r == "en" else " و"
    served = (", " if r == "en" else "، ").join(cities[:-1]) + joint + cities[-1]
    return lean_result({"status": "not_served", "served": served, "note": NOT_SERVED})


def unknown_place(which: Literal["origin", "destination"]) -> ToolResult:
    """A place the directory does not know: ask again."""
    return lean_result({"status": "unknown_place", "which": which, "note": UNKNOWN_PLACE})


def refused_answer(answer: DayOffers, places: Places, tag: Tag) -> ToolResult | None:
    """The source's refusal of the route or the cabin, said; None when it answered flights."""
    if answer.status == "not_served":
        return not_served(places, tag)
    if answer.status == "cabin_not_sold":
        offered: list[JsonValue] = list(answer.cabins or ())
        cabin = answer.query.cabin
        return lean_result({"status": "cabin_not_offered", "cabin": cabin, "offered": offered})
    return None


def named(place: Place, answer: DayOffers) -> Place:
    """A bare place named by the provider's city for it, never by its letters."""
    if place.known:
        return place
    city = dict(answer.cities).get(place.code)
    return place if city is None else place.model_copy(update={"city_en": city, "city_ar": city})


async def nearest(data: FlightData, q: OfferQuery, today: date) -> tuple[date, ...]:
    """The nearest days with a flight, or none when the source could not say."""
    try:
        return await data.nearest(q, today)
    except FlightDataUnavailableError:
        return ()


def both_legs(
    answers: tuple[DayOffers, DayOffers | FlightDataUnavailableError | None],
    airline: str | None,
    tag: Tag,
    travelers: int,
    places: Places,
) -> tuple[Built, Built | None] | dict[str, JsonValue]:
    """Both legs built, narrowed to `airline`; the way back unnarrowed when the airline does
    not fly it; the outbound's refusal as data; the way back None when it was not checked."""
    out, home = answers
    went = built(out, airline=airline, tag=tag, travelers=travelers, places=places)
    if isinstance(went, dict):
        return went
    if not isinstance(home, DayOffers):
        return went, None
    came = built(home, airline=airline, tag=tag, travelers=travelers, places=places)
    if isinstance(came, dict):
        came = built(home, airline=None, tag=tag, travelers=travelers, places=places)
    return went, None if isinstance(came, dict) else came

"""The lean tools' cards, drawn from the offers the call was given, as the scripted cards are
(tools/cards.py, whose helpers these reuse): a row per offer, its times as its title (the
flight beside them when two rows share their times), its length, stops, airline and flights as
its detail, its price as its value, and its mark (`unavailable` when it is known to lack seats,
`chosen` when picked, `best` on the cheapest). Each card names its segment of the page: a leg's
listing its leg's, the trip its review.

Every number a card shows is in its result's data (the output guard's ID rule), and a word sits
between two numbers. Arabic cards write times, lengths and prices in Arabic-Indic digits; a
flight's code and its aircraft keep their Latin letters and digits.
"""

from __future__ import annotations

from datetime import date
from typing import Final, Literal

from t2_agentic_voice import Card, CardRow

from flight_voice.flight_data.model import Cabin, Place
from flight_voice.lean.draft import LEGS, LeanDraft, LegKind
from flight_voice.lean.results import LeanOption, cheapest_id
from flight_voice.said import Tag, arabic, register, words
from flight_voice.tools import cards

# A card holds at most this many rows (the library's `MAX_ROWS`).
MAX_ROWS: Final = 8
_DOT: Final = " · "


def route_title(start: Place, end: Place, tag: Tag) -> str:
    """A route as a card's title writes it: "Riyadh to London", «الرياض إلى لندن»."""
    if arabic(tag):
        return f"{start.city_ar} إلى {end.city_ar}"
    return f"{start.city_en} to {end.city_en}"


def leg_title(leg: LegKind, route: tuple[Place, Place], days: str, cabin: Cabin, tag: Tag) -> str:
    """A leg's segment title: the leg, its route, its day (or days) and the cabin."""
    named = cards.LEGS["ar" if arabic(tag) else "en"][leg]
    where = route_title(*route, tag)
    return f"{named}: {where}{_DOT}{days}{_DOT}{words.cabin(cabin, register(tag))}"


def times(option: LeanOption, tag: Tag) -> str:
    """An offer's local times at each end, joined by a word, with "next day" when it lands a
    later day."""
    if arabic(tag):
        joined = cards.indic(f"{option.departs} إلى {option.arrives}")
        return joined + (" من اليوم التالي" if option.next_day else "")
    return f"{option.departs} to {option.arrives}" + (" next day" if option.next_day else "")


def _stops(option: LeanOption, tag: Tag) -> str:
    if arabic(tag):
        if not option.stops:
            return "مباشرة"
        counted = "توقف واحد" if option.stops == 1 else f"{cards.indic(str(option.stops))} توقفات"
        where = " و".join(v.city for v in option.via or ())
        waits = " و".join(cards.length(v.wait, tag) for v in option.via or ())
        made = f"{counted} في {where}، {waits}" if where else counted
        return made + ("، جزء منها بالباص" if option.bus else "")
    if not option.stops:
        return "nonstop"
    noun = "stop" if option.stops == 1 else "stops"
    where = " and ".join(v.city for v in option.via or ())
    waits = " and ".join(cards.length(v.wait, tag) for v in option.via or ())
    made = f"{option.stops} {noun} in {where}, {waits}" if where else f"{option.stops} {noun}"
    return made + (", partly by bus" if option.bus else "")


def flown(option: LeanOption, tag: Tag) -> str:
    """An offer's length, stops, airline, flights and aircraft: "1 h 55 min, nonstop, flyadeal
    flight F3 111", "7 h 5 min, nonstop, T2 Air flight T2 401 on a 787-9"."""
    length = cards.length(option.duration, tag)
    if arabic(tag):
        made = f"{length}، {_stops(option, tag)}، {option.airline} رحلة {option.flight}"
        return made + (f" على {option.aircraft}" if option.aircraft else "")
    made = f"{length}, {_stops(option, tag)}, {option.airline} flight {option.flight}"
    if not option.aircraft:
        return made
    article = "an" if option.aircraft[:1].upper() in "AEIOU" else "a"
    return f"{made} on {article} {option.aircraft}"


def offer_row(
    option: LeanOption,
    tag: Tag,
    *,
    chosen: bool = False,
    best: bool = False,
    title: str | None = None,
    detail: str | None = None,
) -> CardRow:
    """One offer as a card's row (the module's docstring)."""
    mark: Literal["best", "chosen", "unavailable"] | None = (
        "unavailable"
        if option.seats_ok is False
        else ("chosen" if chosen else ("best" if best else None))
    )
    return CardRow(
        title=times(option, tag) if title is None else title,
        detail=flown(option, tag) if detail is None else detail,
        value=cards.money(option.price, tag),
        mark=mark,
    )


def _titles(options: tuple[LeanOption, ...], tag: Tag) -> list[str]:
    """Each option's title: its times, with its flight beside them when another shares them."""
    plain = [times(o, tag) for o in options]
    return [
        f"{t}{_DOT}{o.flight}" if plain.count(t) > 1 else t
        for t, o in zip(plain, options, strict=True)
    ]


def options_card(
    leg: LegKind,
    options: tuple[LeanOption, ...],
    route: tuple[Place, Place],
    day: date,
    cabin: Cabin,
    tag: Tag,
    *,
    kept: LeanOption | None = None,
) -> Card:
    """A leg's options on `day`, in its segment: its title, then a row per option (at most the
    card's rows but one), and `kept`, the other leg's pick, beside them marked chosen."""
    shown = options[: MAX_ROWS - 1]
    best = cheapest_id(shown)
    rows = tuple(
        offer_row(o, tag, best=o.id == best, title=t)
        for o, t in zip(shown, _titles(shown, tag), strict=True)
    )
    if kept is not None:
        rows += (offer_row(kept, tag, chosen=True),)
    title = leg_title(leg, route, cards.day_title(day, tag), cabin, tag)
    return Card(title=title, rows=rows, slot=leg)


def trip_card(draft: LeanDraft, chosen: dict[LegKind, LeanOption], tag: Tag) -> Card | None:
    """The trip planned so far, in the review segment: a row for each chosen leg (`chosen`, the
    offers as the model read them), the travelers and the cabin, then the total once every leg
    is chosen; none while nothing is planned."""
    if draft.destination is None:
        return None
    rows: list[CardRow] = []
    sep = "، " if arabic(tag) else ", "
    named = cards.LEGS["ar" if arabic(tag) else "en"]
    for leg in LEGS:
        offer, option = draft.chosen(leg), chosen.get(leg)
        if offer is None or option is None or (leg == "return" and draft.one_way):
            continue
        detail = f"{named[leg]}: {cards.day_title(offer.day, tag)}{sep}{flown(option, tag)}"
        rows.append(offer_row(option, tag, chosen=True, detail=detail))
    rows.append(CardRow(title=cards.party(draft.travelers, draft.cabin, tag)))
    total = draft.total()
    if total is not None:
        label = "المجموع" if arabic(tag) else "Total"
        rows.append(CardRow(title=label, value=cards.money(total, tag)))
    r = register(tag)
    route = route_title(draft.origin, draft.destination, tag)
    kind = words.trip_kind(draft.one_way, r)
    mine = cards.TRIP_AR if arabic(tag) else cards.TRIP_EN
    title = f"{mine}: {route}{_DOT}{kind}{_DOT}{words.cabin(draft.cabin, r)}"
    return Card(title=title, rows=tuple(rows), slot="review")

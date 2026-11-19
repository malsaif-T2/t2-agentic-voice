"""A span's days as find_flights gives them (span.py): each day that has a flight
(`SpanDay`), read from the source's answer (`read_days`): its weekday, its flights (left out
when the source did not count them) and its lowest price; and for a span asked `each_day`, each
day searched (`searched_day`), over the flights a day's search lists from (listing.py's pool):
its flights, its lowest and highest prices, its first and last departures and the airlines
flying it, the first of each in departure order.
"""

from __future__ import annotations

from datetime import date

from flight_voice.flight_data.model import Offer
from flight_voice.flight_data.queries import DayFares
from flight_voice.lean.listing import pool
from flight_voice.lean.results import Day, _Data, day_of
from flight_voice.said import Tag, register

__all__ = ["SpanDay", "read_days", "searched_day"]


class SpanDay(_Data):
    """A day of a span that has a flight: its weekday, its flights (left out when the source
    did not count them, as a fare calendar does not) and its lowest price; when each day was
    searched, its highest price, first and last departures and airlines too."""

    date: str
    weekday: str
    flights: int | None = None
    lowest_price: int
    highest_price: int | None = None
    first_departs: str | None = None
    last_departs: str | None = None
    airlines: tuple[str, ...] | None = None


def searched_day(day: date, offers: tuple[Offer, ...], tag: Tag) -> SpanDay | None:
    """A day searched, over the flights its search lists from; None when it has none."""
    held = pool(offers)
    if not held:
        return None
    r = register(tag)
    prices = [o.price.amount for o in held]
    return SpanDay(
        date=day.isoformat(),
        weekday=day_of(day, tag).weekday,
        flights=len(held),
        lowest_price=min(prices),
        highest_price=max(prices),
        first_departs=held[0].departs.strftime("%H:%M"),
        last_departs=held[-1].departs.strftime("%H:%M"),
        airlines=tuple(dict.fromkeys(o.carrier.name(r) for o in held)),
    )


def read_days(
    found: DayFares, tag: Tag, each_day: bool = False
) -> tuple[list[SpanDay], list[Day], list[Day]]:
    """The span's days with a flight, with none, and not checked; each searched day's flights
    summed up when `each_day`."""
    days: list[SpanDay] = []
    empty: list[Day] = []
    unknown: list[Day] = []
    for each in found.days:
        if not each.known:
            unknown.append(day_of(each.day, tag))
        elif each_day and each.offers is not None:
            searched = searched_day(each.day, each.offers, tag)
            if searched is None:
                empty.append(day_of(each.day, tag))
            else:
                days.append(searched)
        elif each.lowest is None:
            empty.append(day_of(each.day, tag))
        else:
            days.append(
                SpanDay(
                    date=each.day.isoformat(),
                    weekday=day_of(each.day, tag).weekday,
                    flights=each.flights,
                    lowest_price=each.lowest.amount,
                )
            )
    return days, empty, unknown

"""The fixed strings a flight result's `say` holds (`SAY`), each telling the talker what to say
next, in English, never built from the caller's words or any free text; results.py gives them
with its models.

A day's listing is said briefly (the owner's ruling): one or two flights each by its departure
time and fare; three or four by how many there are, the first and last departure times and the
cheapest by its time and fare (`_brief`), the others only when the caller asks. The fare's
basis ("per person, one way") is said once a call, on the first listing. A first outbound
listing is said from its day and its weekday, in place of the caller's request said back
(`listed`); a return listing, after the choice said back, is not (`return_listed`). A listing
after one of another day in the call is said from its day (`relisted`). A full flight is said
by its departure time as full, never with its fare nor as the cheapest (`_full`). After a full
flight or a day with no seat, the talker offers what the result gives and changes nothing the
caller did not ask for; a pick that names no flight listed has them said as briefly as their
listing, a full one as full (`_unclear`); a change that lost a leg's flight names that flight by
its departure time, and lists that leg's flights as briefly. A span of days is said by its
first and last days, the daily times and its two cheapest days (`days`).
"""

from __future__ import annotations

from typing import Final


def _brief(fare: str) -> str:
    return (
        "how many flights there are (count), the first and last departure times (first_departs, "
        f"last_departs), and the cheapest by its departure time and {fare}; say the other flights "
        "only when the caller asks for them."
    )


_EACH: Final = "these flights, each by its departure time and fare, the cheapest marked."
_ONCE: Final = " Say once that fares are one way, per person."
_NOT_AGAIN: Final = " Do not say again that fares are one way, per person."
_ASK: Final = " Then ask which one they want. Do not say flight numbers."
_DAY: Final = "Say the day with its weekday first, in place of saying their request back, then "
_NEW_DAY: Final = "Say the new day with its weekday first, then "
_FULL: Final = (
    " A flight with seats_ok false is full in this cabin: say it by its departure time as full, "
    "with no fare, and never as the cheapest."
)
# What the caller is offered after a full flight or a day with no seat, then nothing changed.
_WAIT: Final = " Then wait for their answer; call change_trip only for a cabin the caller asks for."
_RELIST: Final = "Say what changed in a few words, then "
_LOST: Final = (
    "Say what changed, then that the flight chosen for that leg, the one leaving at "
    "lost_departs, has no seats for it now, then that leg's flights: "
)
_EACH_NEW: Final = "each by its departure time and new fare."
_WHICH: Final = " Then ask which one they want."
_SPAN: Final = (
    "Say the span by its first and last days with their weekdays, then that we fly there every "
    "day of it"
)
_TIMES: Final = (
    " at these times (departs; for three or four a day, how many and the first and last), then "
    "the two cheapest days (marked) with their fares, and ask which day they would like to "
    "leave. Do not list flights yet."
)


def _unclear() -> dict[str, str]:
    """A pick's `unclear_choice` says: the flights it could mean, each by its time and fare, or,
    when it named none of three or four listed, those as briefly as their listing; each with its
    full variant."""
    each = "Say the flights the caller could mean, each by its departure time and fare."
    none = "Say none of the flights listed is the one they named, then "
    return {
        "unclear_choice_full": each + _FULL + _WHICH,
        "unclear_choice_brief": none + _brief("fare") + _WHICH,
        "unclear_choice_brief_full": none + _brief("fare") + _FULL + _WHICH,
    }


def _listings(start: str, opening: str, basis: str) -> dict[str, str]:
    """A listing's four says: of one or two flights and of three or four, each with its full
    variant, the full-flight rule before the fare's basis."""
    return {
        start: opening + _EACH + basis + _ASK,
        f"{start}_full": opening + _EACH + _FULL + basis + _ASK,
        f"{start}_brief": opening + _brief("fare") + basis + _ASK,
        f"{start}_brief_full": opening + _brief("fare") + _FULL + basis + _ASK,
    }


def _relists(start: str, opening: str) -> dict[str, str]:
    """A change's relisting says, as `_listings`' are, with the flights' new fares."""
    return {
        start: opening + _EACH_NEW + _WHICH,
        f"{start}_full": opening + _EACH_NEW + _FULL + _WHICH,
        f"{start}_brief": opening + _brief("new fare") + _WHICH,
        f"{start}_brief_full": opening + _brief("new fare") + _FULL + _WHICH,
    }


SAY: Final[dict[str, str]] = {
    **_listings("listed", _DAY, _ONCE),
    **_listings("return_listed", "Say ", _NOT_AGAIN),
    **_listings("relisted", _NEW_DAY, _NOT_AGAIN),
    "days": _SPAN + _TIMES,
    "days_some": _SPAN + " but the days in no_flight_days," + _TIMES,
    "not_served_city": "Say we do not fly there, name the cities we fly to, and ask where they "
    "would like to go.",
    "not_served_route": "Say we fly only to and from Riyadh, with no connections, so each part "
    "would be its own trip through Riyadh. Ask how they would like to go on.",
    "past": "Say that day has passed and ask for another day.",
    "beyond_window": "Say bookings open only up to last_day, with its weekday, and ask for a "
    "day on or before it.",
    "no_such_day": "Say that day does not exist in that month and ask for the day again.",
    "return_before_departure": "Say that return is before the departure and ask when they "
    "would like to come back.",
    "return_only": "Ask which day they would like to leave.",
    "needs_return_date": "Ask when they would like to come back. Do not list flights yet.",
    "cabin_not_offered": "Say that cabin is not offered on this route, offer the cabins in "
    "offered, and ask which they would like. Do not list flights yet.",
    "no_flights_that_day": "Say there is no flight that day and offer these days.",
    "no_seats": "Say the flights that day are full in this cabin for this many travelers, and "
    "offer the cabins in cabins_with_seats or another day." + _WAIT,
    "no_seats_flight": "Say that flight is full in this cabin for this many travelers, and "
    "offer the cabins in cabins_with_seats or the other flights in other_flights." + _WAIT,
    "nothing_listed": "Search first.",
    "unclear_choice": "Say the flights the caller could mean, each by its departure time and "
    "fare, and ask which one they want.",
    **_unclear(),
    "chosen_then_return": "Say the choice back in a few words, then the return flights as their "
    "listing's say (returns.say) asks, and ask which one. Do not say again that fares are one "
    "way, per person.",
    "chosen_then_outbound": "Say the choice back in a few words, then ask which outbound flight "
    "they want.",
    "chosen_needs_return": "Say the choice back in a few words, then ask when they would like to "
    "come back.",
    "chosen_return_full": "Say the choice back in a few words, then that no return flight that "
    "day has a seat in this cabin for this many travelers, and offer another return day or cabin.",
    "complete": "Call book_trip now, in this reply, even right after a read-back the caller "
    "declined or changed, and say nothing yourself: never ask whether to book or confirm it. The "
    "caller hears the trip read back and is asked to confirm it; that is the only question.",
    "changed": "Say what changed in a few words, then ask for what is still missing.",
    **_relists("changed_relist", _RELIST + "these flights again, "),
    **_relists("changed_lost", _LOST),
    "changed_needs_return": "Say what changed, then ask when they would like to come back.",
    "trip": "Answer from this trip. If something is missing, ask for the first thing missing.",
    "trip_empty": "Nothing is planned yet. Ask where they would like to go.",
    "calendar": "Say the three cheapest days with their fares, then ask which day suits them.",
    "cabins": "Say each cabin's fare on this flight, one way, per person, and ask which cabin "
    "they want. Then wait for their answer; call change_trip only for a cabin the caller asked "
    "for.",
    "profile": "Answer from these counts. Say a past trip as one they flew, never as one you "
    "booked. Never read a booking reference unless the caller asks for it.",
}

"""The booking (`book_trip`), the flight agent's one action: read back, confirmed by the caller's
spoken yes, then written to the airline as a job outside the turn (invariant 1).

- **`validate`** reads the call's trip draft, never the talker's arguments (it has none to give,
  booking/draft.py): a caller with no traveler the airline knows, a trip with a leg not chosen,
  a flight short of seats or a day passed are each refused with a `ToolError` that names the
  failure and the next step; else the trip priced now fills every field of the draft.
- **`execute`** books from the draft's own fields, what was read back, for the call's verified
  traveler (`attributes.traveler_id`, invariant 3), the request ID the idempotency key. The
  airline's refusal (a changed price among them) is `ActionRejected`, said as `failed`; a write
  that cannot go out is `ActionNotSent`; anything else, the store's timeout among them, may have
  been done, so the runtime looks it up by its request ID (`lookup`, registered only when the
  store can find one, invariant 6) and says `unknown` when it finds nothing.
- **One booking a call** (`max_per_call` 1, the library's): a write that ended `unknown` is
  counted, so no second write goes out beside it under a new request ID, and a refused or
  dropped one is not, so the caller can change the trip and try again.
"""

from __future__ import annotations

from typing import Final

from t2_agentic_voice import (
    Action,
    ActionContext,
    ActionNotSent,
    ActionRejected,
    CallContext,
    Caller,
    ToolError,
    action,
)

from flight_voice.airline.bookings import BookingRefused, NewBooking, RefusalReason, priced
from flight_voice.airline.system import TRAVELERS, Airline
from flight_voice.booking import lines
from flight_voice.booking.draft import BOOK_TRIP, BookingDraft, BookingMade, NotFilledError, filled
from flight_voice.trip import Missing, TripBook

# One booking a call (the module's docstring).
BOOKINGS_PER_CALL: Final = 1
DESCRIPTION: Final = (
    "Book the trip the caller planned, once every flight of it is chosen. Call it with no "
    "arguments: the trip is read from the flights chosen. The caller hears the trip read back "
    "and is asked to confirm it; say nothing yourself after calling this."
)
NO_TRAVELER: Final = (
    "This call has no traveler to book for, so no booking can be made in it. Tell the caller "
    "plainly that you cannot book in this call."
)
_MISSING: Final[dict[Missing, str]] = {
    "destination": "No trip is planned yet. Ask where they would like to fly.",
    "depart": "The trip has no departure day yet. Ask which day they would like to leave.",
    "return_date": "The trip has no return day yet. Ask when they would like to come back.",
    "outbound": "The outbound flight is not chosen yet. Ask which one they want.",
    "return": "The return flight is not chosen yet. Ask which one they want.",
}
_REFUSED: Final[dict[RefusalReason, str]] = {
    "no_seats": "A chosen flight no longer has seats for every traveler in this cabin. Say so, "
    "and call search_flights again for that day to offer the others.",
    "date_passed": "A chosen flight's day has passed. Say so, and ask for another day.",
    "no_such_flight": "A chosen flight no longer flies that day. Say so, and call "
    "search_flights again for that day to offer the others.",
    "price_changed": "The trip's fare has changed. Call get_trip and say the new total.",
    "refused": "The booking cannot be made. Say so plainly.",
}


def traveler_of(caller: Caller) -> str | None:
    """The traveler the verified caller is, when the airline knows them; never a value the
    talker gives."""
    traveler = caller.attributes.get("traveler_id")
    return traveler if isinstance(traveler, str) and traveler in TRAVELERS else None


def book_trip(airline: Airline, trips: TripBook) -> Action:
    """The booking over `airline`, of the trip each call plans in `trips` (the module's
    docstring)."""

    async def from_the_trip(ctx: CallContext, draft: BookingDraft) -> BookingDraft:
        """`draft` replaced, every field, by the call's trip priced now; ToolError, which the
        talker reads, when it cannot be booked."""
        del draft  # whatever the talker sent is never kept
        if traveler_of(ctx.caller) is None:
            raise ToolError(NO_TRAVELER)
        trip = trips.get(ctx.call_id)
        missing = trip.missing()
        if missing:
            raise ToolError(_MISSING[missing[0]])
        try:
            total = priced(trip.legs(), trip.cabin, trip.travelers, airline.today())
            return filled(trip, total)
        except BookingRefused as error:
            raise ToolError(_REFUSED[error.reason]) from None
        except NotFilledError:
            raise ToolError(_MISSING["outbound"]) from None

    def _traveler(ctx: ActionContext) -> str:
        traveler = traveler_of(ctx.caller)
        if traveler is None:
            raise ActionNotSent("The call's caller is no traveler the airline knows.")
        return traveler

    @action(
        name=BOOK_TRIP,
        description=DESCRIPTION,
        read_back=lines.READ_BACK,
        done=lines.DONE,
        claims=lines.CLAIMS,
        sending=lines.SENDING,
        failed=lines.FAILED,
        unknown=lines.UNKNOWN,
        declined=lines.DECLINED,
        validate=from_the_trip,
        max_per_call=BOOKINGS_PER_CALL,
    )
    async def booked(ctx: ActionContext, draft: BookingDraft) -> BookingMade:
        traveler = _traveler(ctx)
        try:
            legs = draft.legs()
        except NotFilledError:
            raise ActionNotSent("The booking's draft holds no trip.") from None
        new = NewBooking(
            request_id=ctx.request_id,
            traveler_id=traveler,
            legs=legs,
            cabin=draft.cabin,
            travelers=draft.travelers,
            total_sar=draft.total_sar,
        )
        try:
            return BookingMade.of(await airline.bookings.create(new))
        except BookingRefused as error:
            raise ActionRejected(error.message, details={"reason": error.reason}) from error

    if airline.bookings.can_find:

        @booked.lookup
        async def found(ctx: ActionContext, request_id: str) -> BookingMade | None:
            made = await airline.bookings.find(request_id, _traveler(ctx))
            return None if made is None else BookingMade.of(made)

    return booked

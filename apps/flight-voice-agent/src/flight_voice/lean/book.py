"""`book_trip`, the lean agent's booking on the mock network alone (registered only when
`deps.bookable`; called anyway, it answers `not_bookable`): a tool that writes the trip chosen
so far to the mock airline's booking store, as the scripted agent's action job does, once the
booking check holds (booking_check.py). It takes no arguments: the trip is the call's, and the
traveler the call's verified caller (`attributes.traveler_id`, invariant 3), never a value the
model gives; a booking already made is told from the trip as it was booked (`Ledger.trip`),
never the call's trip since changed. This departs from the library's "only actions act"
design, for the mock airline alone, by the owner's ruling (D-113): the model's own judgement
that the caller agreed is the yes.

In order, each with nothing written: a caller who is no traveler the airline knows is a
`ToolError`; a booking already made in this call answers `already_booked` with it, and a write
whose end is not known `unknown` (one booking a call, never a second write beside one that may
have gone through); a trip with a leg not chosen is `incomplete`, with the legs `missing`; a trip
the airline can no longer sell as it is (a seat gone, a day passed, or a price that is no longer
the one the caller heard: `price_changed`) is `refused`, with the reason; and a trip whose total
was not said, played and answered is `not_confirmed`, its `say` the one fixed text the lean
tools hold (`NOT_CONFIRMED`). Then the store books it, priced again,
under a request ID of the call's own: a refusal is `refused`; a write that does not answer
within `WRITE_S` is looked up by its request ID (when the store can find one), and `unknown`
when nothing is found. A booking made returns its status, its total (the caller has just
heard the trip) and its reference, and the review card marked booked with its reference: the
owner ruled on 2026-11-18 that saying the reference unasked is fine ("it is not a hard
requirement"), after a pointer in its place left f20's caller told there was none
(f-dev-lean-4). A booking already made is told whole, its trip and reference as it was booked.

**No claim before the booking** (the owner's call of 2026-11-18: at the caller's yes the model
called `book_trip`, which answered `not_confirmed`, then said «تم حجز رحلتك …»): the tool
declares `LEAN_CLAIMS` as its `claims`, the booking's claim phrases (booking/lines.py's `CLAIMS`,
«تم حجز», «تم الحجز», "I've booked" and the like) and the rewordings a model writes that they
miss («حجزتها», «تم حجزها», «حجزت رحلتك», "your flight's booked"), and its `booked` and
`already_booked` results are `done`, so the library's output guard (rule A) says a clause
holding one only once this call's booking was made, and sends the model's request once more
when it held one back (`guard.retry_claims`, settings.py). The agent declares no action, so
the library's default phrases are not read (its "has been booked" sits in an honest "nothing
has been booked yet").

The tool finishes when a barge-in comes (`on_interrupt="finish"`), so a write is never cut in
half; a write begun is counted before it is sent, so a call cut off mid-write is `unknown`.
"""

from __future__ import annotations

import asyncio
from typing import Final

from pydantic import JsonValue
from t2_agentic_voice import (
    CallContext,
    Card,
    CardRow,
    Claims,
    Tool,
    ToolError,
    ToolResult,
    tool,
)

from flight_voice.airline.bookings import (
    AirlineError,
    Booking,
    BookingRefused,
    Leg,
    NewBooking,
    priced,
)
from flight_voice.airline.system import Airline
from flight_voice.booking.action import NO_TRAVELER, traveler_of
from flight_voice.booking.lines import CLAIMS
from flight_voice.flight_data.port import Places
from flight_voice.lean.booking_check import Ledger
from flight_voice.lean.deps import LeanDeps
from flight_voice.lean.draft import LeanDraft
from flight_voice.lean.offer_cards import trip_card
from flight_voice.lean.picking import Picking, chosen_legs
from flight_voice.lean.results import lean_result, route_said, trip_said
from flight_voice.said import Tag, arabic

BOOK_TRIP: Final = "book_trip"
DESCRIPTION: Final = (
    "Book the trip chosen so far, only once the caller heard the trip with its total and "
    "agreed. It takes no arguments."
)
NOT_BOOKABLE: Final[dict[str, JsonValue]] = {
    "status": "not_bookable",
    "note": "Booking is not open on this line: say the trip and its total, and that the "
    "airline's own site books it.",
}
NOT_CONFIRMED: Final[dict[str, JsonValue]] = {
    "status": "not_confirmed",
    "say": "Say the trip with its total in one sentence and ask whether to book it. Book only "
    "after the caller agrees.",
}
# How long a write may take before it is looked up; the tool's own limit is above it.
WRITE_S: Final = 15.0
TOOL_S: Final = 20.0
BOOKED: Final = {"en": "Booked · Reference {ref}", "ar": "تم الحجز · رقم الحجز {ref}"}
# The rewordings of a booking's claim that `CLAIMS` misses, as booking/lines.py's rule asks: none
# sits in a negative but after ma («ما حجزتها»), which the guard reads. «محجوزة» alone is no
# claim: «الرحلة محجوزة بالكامل» says the flight is sold out.
REWORDED: Final[dict[str, tuple[str, ...]]] = {
    "ar-SA": (
        "حجزتها",  # Hajaztha: I booked it
        "تم حجزها",  # tamm Hajzha: it was booked
        "تم حجزه",  # tamm Hajzah: the same, of a masculine word
        "حجزت رحلتك",  # Hajazt riHlatak: I booked your trip
    ),
    "ar": ("تم تأكيد حجزك",),  # tamma ta'keedu Hajzik: your booking was confirmed
    "en": (
        "you're all booked",
        "you are all booked",
        "I've got you booked",
        "your flight's booked",
        "your trip's booked",
        "your flight has been booked",
    ),
}
LEAN_CLAIMS: Final = Claims(
    {tag: (*phrases, *REWORDED.get(tag, ())) for tag, phrases in CLAIMS.phrases.items()}
)


def booked_card(draft: LeanDraft, places: Places, reference: str, tag: Tag) -> Card | None:
    """The review card of the trip booked, its last row "Booked · Reference …"."""
    trip = trip_card(draft, Picking(draft, places, tag).chosen_options(), tag)
    if trip is None:
        return None
    line = BOOKED["ar" if arabic(tag) else "en"].format(ref=reference)
    return trip.model_copy(update={"rows": (*trip.rows, CardRow(title=line))})


def _booked(booking: Booking, draft: LeanDraft, places: Places, tag: Tag) -> ToolResult:
    """A booking just made: its status, its total and its reference (the module's docstring)."""
    answer: dict[str, JsonValue] = {
        "status": "booked",
        "total": booking.total_sar,
        "reference": booking.reference,
    }
    return lean_result(answer, booked_card(draft, places, booking.reference, tag), done=True)


def _already(booking: Booking, draft: LeanDraft, places: Places, tag: Tag) -> ToolResult:
    """A booking made before in this call, told whole as it was booked (`draft`), its reference
    too."""
    end = draft.destination or places.get(booking.destination) or draft.origin
    said, msa = route_said((draft.origin, end), tag)
    kind, kind_msa = trip_said(booking.return_date is None, tag)
    answer: dict[str, JsonValue] = {
        "status": "already_booked",
        "total": booking.total_sar,
        "route": said,
        "route_msa": msa,
        "trip": kind,
        "trip_msa": kind_msa,
        "travelers": booking.travelers,
        "cabin": booking.cabin,
    }
    answer |= chosen_legs(draft, places, tag) | {"reference": booking.reference}
    return lean_result(answer, booked_card(draft, places, booking.reference, tag), done=True)


async def _write(airline: Airline, new: NewBooking, ledger: Ledger) -> Booking | None:
    """`new` written, or looked up when the write does not answer in time; None when its end
    is not known. A refusal is raised."""
    store = airline.bookings
    try:
        return await asyncio.wait_for(store.create(new), WRITE_S)
    except BookingRefused:
        ledger.unsure = False
        raise
    except (TimeoutError, AirlineError):
        if not store.can_find:
            return None
    try:
        return await store.find(new.request_id, new.traveler_id)
    except AirlineError:
        return None


def book_trip(deps: LeanDeps) -> Tool:
    """The booking of each call's trip in `deps.trips` on the mock airline, once `deps.check`
    holds (the module's docstring)."""
    airline, trips, check, places = deps.airline, deps.trips, deps.check, deps.places

    @tool(
        name=BOOK_TRIP,
        description=DESCRIPTION,
        timeout_s=TOOL_S,
        on_interrupt="finish",
        claims=LEAN_CLAIMS,
    )
    async def book(ctx: CallContext) -> ToolResult:
        tag: Tag = ctx.language
        if not deps.bookable:
            return lean_result(dict(NOT_BOOKABLE))
        traveler = traveler_of(ctx.caller)
        if traveler is None:
            raise ToolError(NO_TRAVELER)
        ledger = check.ledger(ctx.call_id)
        draft = trips.get(ctx.call_id)
        if ledger.booked is not None:
            booked = draft if ledger.trip is None else ledger.trip
            return _already(ledger.booked, booked, places, tag)
        if ledger.unsure:
            return lean_result({"status": "unknown"})
        missing: list[JsonValue] = [m for m in draft.missing() if m in ("outbound", "return")]
        if missing or draft.destination is None:
            return lean_result({"status": "incomplete", "missing": missing})
        chosen = tuple(Leg(flight=int(o.segments[0].number), day=o.day) for o in draft.legs())
        heard = draft.total()
        try:
            total = priced(chosen, draft.cabin, draft.travelers, deps.today())
        except BookingRefused as error:
            return lean_result({"status": "refused", "reason": error.reason})
        if heard is None or total != heard:
            return lean_result({"status": "refused", "reason": "price_changed"})
        if not check.confirmed(ctx.call_id, draft, total):
            return lean_result(dict(NOT_CONFIRMED))
        legs: tuple[Leg] | tuple[Leg, Leg] = (
            (chosen[0],) if len(chosen) == 1 else (chosen[0], chosen[1])
        )
        ledger.writes += 1
        ledger.unsure = True  # until the write's end is known
        new = NewBooking(
            request_id=f"{ctx.call_id}:lean:{ledger.writes}",
            traveler_id=traveler,
            legs=legs,
            cabin=draft.cabin,
            travelers=draft.travelers,
            total_sar=total,
        )
        try:
            made_booking = await _write(airline, new, ledger)
        except BookingRefused as error:
            return lean_result({"status": "refused", "reason": error.reason})
        if made_booking is None:
            return lean_result({"status": "unknown"})
        ledger.booked, ledger.trip, ledger.unsure = made_booking, draft, False
        return _booked(made_booking, draft, places, tag)

    return book

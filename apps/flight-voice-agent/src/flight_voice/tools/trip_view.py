"""The trip planned so far, as the talker reads it (`TripView`), and `get_trip`, which gives it.

The view is the call's draft said whole: the route and the trip's kind in the reply's registers,
the dates, the travelers and the cabin, each chosen leg with its times and fare priced now, what
is still missing in the order it is asked, and the total once every leg is chosen. The talker
calls `get_trip` when the caller asks what they chose, or when it is unsure which flight they
mean; `choose_flight` and `change_trip` give the same view when they change the trip.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import Final, Literal

from t2_agentic_voice import CallContext, Tool, ToolResult, tool

from flight_voice.airline.schedule import Cabin
from flight_voice.airline.system import Airline
from flight_voice.said import Tag, words
from flight_voice.tools import cards
from flight_voice.tools.listing import listed_again
from flight_voice.tools.results import SAY, DateSaid, Option, _Result, date_said, result, said
from flight_voice.trip import LegKind, Missing, Shown, TripBook, TripDraft

GET_TRIP: Final = "get_trip"
DESCRIPTION: Final = (
    "Read the trip planned so far: route, dates, travelers, cabin, the flights listed and "
    "chosen, the total, and what is still missing. Call it when the caller asks what they "
    "chose, or when you are unsure which flight they mean."
)


class TripView(_Result):
    """The trip planned so far (the module's docstring); `say` only when it is a result of its
    own, not a part of another."""

    status: Literal["ok", "empty"] = "ok"
    route_said: str | None = None
    route_said_msa: str | None = None
    trip_kind_said: str
    trip_kind_said_msa: str | None = None
    depart: DateSaid | None = None
    return_date: DateSaid | None = None
    travelers: int
    cabin: Cabin
    cabin_said: str
    cabin_said_msa: str | None = None
    outbound: Option | None = None
    return_flight: Option | None = None
    missing: tuple[Missing, ...]
    total_sar: int | None = None
    say: str | None = None


def chosen_option(
    draft: TripDraft, leg: LegKind, tag: Tag, name: Callable[[int], str]
) -> Option | None:
    """The leg's chosen flight as an option, priced now, keeping its number in the list."""
    chosen = draft.chosen(leg)
    if chosen is None:
        return None
    n = next((s.n for s in draft.shown(leg) if s.flight == chosen.flight), 1)
    shown = (Shown(n=n, flight=chosen.flight, day=chosen.day),)
    again = listed_again(
        shown, cabin=draft.cabin, travelers=draft.travelers, tag=tag, name=name, mark=False
    )
    return again[0] if again else None


def view(draft: TripDraft, tag: Tag, today: date, name: Callable[[int], str]) -> TripView:
    """`draft` as the talker reads it."""
    route = None
    if draft.destination is not None:
        end = draft.destination
        route = said(lambda r: words.route(draft.origin, end, r), tag)
    kind, kind_msa = said(lambda r: words.trip_kind(draft.one_way, r), tag)
    cabin, cabin_msa = said(lambda r: words.cabin(draft.cabin, r), tag)
    return TripView(
        status="ok" if draft.destination is not None else "empty",
        route_said=None if route is None else route[0],
        route_said_msa=None if route is None else route[1],
        trip_kind_said=kind,
        trip_kind_said_msa=kind_msa,
        depart=None if draft.depart is None else date_said(draft.depart, tag),
        return_date=None if draft.return_date is None else date_said(draft.return_date, tag),
        travelers=draft.travelers,
        cabin=draft.cabin,
        cabin_said=cabin,
        cabin_said_msa=cabin_msa,
        outbound=chosen_option(draft, "outbound", tag, name),
        return_flight=None if draft.one_way else chosen_option(draft, "return", tag, name),
        missing=draft.missing(),
        total_sar=draft.total(today),
    )


def get_trip(airline: Airline, trips: TripBook) -> Tool:
    """The trip's view, over the call's draft in `trips` (the module's docstring)."""

    @tool(name=GET_TRIP, description=DESCRIPTION)
    async def read(ctx: CallContext) -> ToolResult:
        tag: Tag = ctx.language
        draft = trips.get(ctx.call_id)
        seen = view(draft, tag, airline.today(), airline.flight_name)
        if seen.status == "empty":
            return result(seen.model_copy(update={"say": SAY["trip_empty"]}))
        answer = seen.model_copy(update={"say": SAY["trip"]})
        return result(answer, cards.trip_card(answer, draft, tag))

    return read

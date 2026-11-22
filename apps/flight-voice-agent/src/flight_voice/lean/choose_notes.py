"""What `choose_flights` says of the trip's two ways on the real network alone (choose.py,
turnaround.py): a return id that leaves too soon after the chosen outbound lands (`too_early`,
with the outbound's arrival and the return's flights that leave late enough), a return pick
another outbound dropped (`lost_return`), and the notes beside the trip so far (`ends`): that
pick dropped, no flight back leaving late enough, a round trip whose way back has no day yet,
and the trip's end once nothing is missing, one way so far (`ONE_WAY_SO_FAR`: ask whether they
come back, or sum it up) or both ways chosen (`BOTH_CHOSEN`: sum it up once). The mock says
none of it (run F reads it as before plan 011's round 2).
"""

from __future__ import annotations

from typing import Final

from pydantic import JsonValue
from t2_agentic_voice import ToolResult

from flight_voice.flight_data.model import Offer
from flight_voice.lean.draft import LeanDraft, LegKind
from flight_voice.lean.find_return import NO_BACK_DAY
from flight_voice.lean.picking import Lost, Picking
from flight_voice.lean.results import LegList, lean_result
from flight_voice.lean.turnaround import NONE_LATE_ENOUGH, RETURN_DROPPED, TOO_EARLY

__all__ = ["BOTH_CHOSEN", "ONE_WAY_SO_FAR", "ends", "lost_return", "too_early"]

ONE_WAY_SO_FAR: Final = (
    "One way so far. If the caller has not said whether they come back, ask whether they want "
    "a flight back; if they said one way, sum the trip up once, briefly, with the total."
)
BOTH_CHOSEN: Final = (
    "Both ways are chosen: sum the trip up once, briefly: each way's airline, day and time, "
    "and the total."
)


def too_early(picking: Picking, wanted: str) -> ToolResult:
    """A return listed that leaves too soon after the chosen outbound lands: the outbound's
    arrival, and the return's flights that leave late enough (none: `NONE_LATE_ENOUGH`)."""
    out = picking.draft.chosen_outbound
    others = picking.others("return")
    answer: dict[str, JsonValue] = {
        "status": "too_early",
        "leg": "return",
        "id": wanted,
        "outbound_arrives": None if out is None else out.arrives.strftime("%H:%M"),
        "outbound_next_day": True if out is not None and out.next_day else None,
        "others": others,
        "note": TOO_EARLY if others else NONE_LATE_ENOUGH,
    }
    return lean_result(answer)


def lost_return(dropped: Offer) -> Lost:
    """A return pick another outbound dropped, by its departure time."""
    return Lost(leg="return", departs=dropped.departs.strftime("%H:%M"))


def ends(
    draft: LeanDraft,
    missing: tuple[LegKind, ...],
    listed: dict[LegKind, LegList],
    lost: tuple[Lost, ...],
) -> tuple[str | None, ...]:
    """The notes on the trip's two ways and its end, beside the trip so far (the module's
    docstring); `missing` the legs still to choose, `listed` the legs listed with it."""
    back = listed.get("return")
    none_late = back is not None and not back.options and draft.chosen_outbound is not None
    no_day = "return" in missing and draft.return_date is None and not draft.one_way
    end = None if missing else (ONE_WAY_SO_FAR if draft.one_way else BOTH_CHOSEN)
    return (
        RETURN_DROPPED if lost else None,
        NONE_LATE_ENOUGH if none_late else None,
        NO_BACK_DAY if no_day else None,
        end,
    )

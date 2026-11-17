"""How a run F play waits on its call (call.py): the call moved on, a step of `STEP_S` at a
time, until no booking a turn confirmed is still being written (and, after the last turn, until
its reply is no longer pending), or, for a last turn said over a summary, until its words
confirmed the booking or no reply has played for `HELD_S` (a yes held there books only once the
summary played whole, D-108); and what a turn's booking came to (`OutcomeKind`).
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Sequence
from typing import Any, Final, Literal, get_args

from t2_agentic_voice.evals import TextCall, TextTurn

from flight_voice.booking.draft import BOOK_TRIP

STEP_S: Final = 0.1  # how far the call moves on between two looks at it
HELD_S: Final = 2.0  # call seconds a yes held over a summary may take to book once no reply plays
OutcomeKind = Literal["done", "failed", "unknown"]
OUTCOME_KINDS: Final[tuple[OutcomeKind, ...]] = get_args(OutcomeKind)


def holds(check: Callable[..., None], *args: Any, **values: Any) -> bool:
    try:
        check(*args, **values)
    except AssertionError:
        return False
    return True


def outcome_of(turn: TextTurn) -> OutcomeKind | None:
    return next((k for k in OUTCOME_KINDS if holds(turn.expect.action_ended, BOOK_TRIP, k)), None)


def writing(said: Sequence[TextTurn]) -> bool:
    """Whether a booking a turn of `said` confirmed has not ended, its lines said, yet."""
    return any(holds(t.expect.confirmed, BOOK_TRIP) and outcome_of(t) is None for t in said)


async def settle(call: TextCall, said: Sequence[TextTurn], limit_s: float, *, last: bool) -> None:
    """The call moved on until no booking is being written (and, for the `last` turn, its reply
    is no longer pending); a pending last reply after `limit_s` is a TimeoutError."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + limit_s
    while (last and said and said[-1].fate == "pending") or writing(said):
        if loop.time() >= deadline:
            if last and said and said[-1].fate == "pending":
                raise TimeoutError("the last turn's reply never ended")
            return
        await call.advance(STEP_S)


async def wait_held(
    call: TextCall, said: Sequence[TextTurn], turn: TextTurn | None, limit_s: float
) -> None:
    """The call moved on until `turn`, the last, said over a summary, confirmed the booking, or
    no reply of `said` has played for `HELD_S` (the module's docstring), or `limit_s` passed."""
    loop = asyncio.get_running_loop()
    deadline, quiet_s = loop.time() + limit_s, 0.0
    while turn is not None and quiet_s < HELD_S and not holds(turn.expect.confirmed, BOOK_TRIP):
        if loop.time() >= deadline:
            return
        await call.advance(STEP_S)
        quiet_s = 0.0 if any(t.fate == "pending" for t in said) else quiet_s + STEP_S

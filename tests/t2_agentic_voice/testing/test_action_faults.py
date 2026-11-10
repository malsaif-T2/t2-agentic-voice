"""The faults `ActionSafetySuite` gives an action (testing/action_faults.py; plan 007, Track D),
each called as the action runner will call it, by its parameters' names: the team's own write
counted and kept, async or sync, with or without its context; a write done whose reply is lost,
found by the lookup or by none; a backend that never answers; and a write refused, each
leaving the action's name, draft and words as they were."""

from __future__ import annotations

import asyncio

import pytest
from t2_agentic_voice.actions.action import Action, ActionContext, action
from t2_agentic_voice.actions.signature import context_parameter, is_async
from t2_agentic_voice.core.errors import ActionNotSent, ActionRejected
from t2_agentic_voice.domain.action_declaration import Claims, ReadBack, Say
from t2_agentic_voice.testing.action_faults import Writes, nothing

from tests.t2_agentic_voice.testing.action_support import (
    VISIT,
    Booked,
    Desk,
    Visit,
    book_action,
    context,
)


def _sync_action(desk: Desk) -> object:
    @action(
        description="Book a visit, sync.",
        read_back=ReadBack({"en": ("Room {room}.", "Send it?")}),
        done=Say(en="Done {number}."),
        claims=Claims({"en": ["booked"]}),
    )
    def book_visit(draft: Visit) -> Booked:  # no context: the request ID is not its to read
        return desk.book("own", draft)

    return book_visit


def _call(made: object, request_id: str = "r-1") -> object:
    """Call an action's function as the runner will: by its parameters' names."""
    execute = made.execute  # type: ignore[attr-defined]
    own = context_parameter(execute, context=ActionContext)
    given = {"draft": VISIT} | ({own: context(request_id)} if own else {})
    assert is_async(execute)
    return asyncio.run(execute(**given))


def test_the_teams_write_is_counted_and_its_result_kept() -> None:
    desk = Desk()
    writes = Writes(book_action(desk))
    counted = writes.counted()
    assert (counted.name, counted.draft, counted.read_back) == (
        "book_visit",
        Visit,
        writes.action.read_back,
    )
    assert _call(counted) == Booked(number="5101") and desk.booked == {"r-1": VISIT}
    assert writes.made == 1 and writes.results == {"r-1": Booked(number="5101")}
    sync = Writes(_sync_action(Desk()))  # type: ignore[arg-type]
    assert _call(sync.counted()) == Booked(number="5101") and sync.made == 1


async def _lost_then_looked_up(lost: Action) -> object:
    with pytest.raises(TimeoutError):
        await asyncio.wait_for(lost.execute(ctx=context("r-2"), draft=VISIT), timeout=0.05)
    assert lost.finder is not None
    return await lost.finder(ctx=context("r-2"), request_id="r-2")


def test_a_write_whose_reply_is_lost_is_done_and_found_by_its_lookup_alone() -> None:
    desk = Desk()
    writes = Writes(book_action(desk))
    for lookup in (True, False):
        found = asyncio.run(_lost_then_looked_up(writes.lost(lookup=lookup)))
        assert found == (Booked(number="5101") if lookup else None)
        assert desk.booked == {"r-2": VISIT}  # done at the desk all the same
    assert writes.made == 2


def test_a_backend_that_never_answers_writes_nothing_and_finds_nothing() -> None:
    desk = Desk()
    writes = Writes(book_action(desk))
    hangs = writes.hangs()

    async def scene() -> None:
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(hangs.execute(ctx=context(), draft=VISIT), timeout=0.05)

    asyncio.run(scene())
    assert desk.booked == {} and writes.made == 1 and hangs.finder is nothing
    assert asyncio.run(nothing(context(), "r-1")) is None


@pytest.mark.parametrize("error", [ActionRejected, ActionNotSent])
def test_a_refused_write_raises_and_writes_nothing(
    error: type[ActionRejected | ActionNotSent],
) -> None:
    desk = Desk()
    writes = Writes(book_action(desk))
    with pytest.raises(error):
        _call(writes.refused(error))
    assert desk.booked == {} and writes.made == 1

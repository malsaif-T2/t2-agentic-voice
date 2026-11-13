"""The states one action goes through (domain/action_flow.py): only the yes rule's yes reaches a
write, a stop over the read-back ends it with nothing sent, a repeat keeps it confirming for a
new reading, a write is never cut, and an end is never left."""

from __future__ import annotations

import pytest
from t2_agentic_voice.domain.action_flow import (
    ACTION_STATES,
    ENDS,
    FLOW_EVENTS,
    ActionState,
    FlowEvent,
    advance,
    moved,
)

# Every move, as the design's 6.4 and the owner's rulings of plan 007 have them.
MOVES: dict[tuple[ActionState, FlowEvent], ActionState] = {
    ("confirming", "yes"): "confirmed",
    ("confirming", "no"): "declined",
    ("confirming", "correction"): "declined",
    ("confirming", "stop"): "declined",
    ("confirming", "unclear"): "declined",
    ("confirming", "repeat"): "confirming",
    ("confirming", "asked_again"): "confirming",
    ("confirmed", "sent"): "sending",
    ("confirmed", "refused"): "failed",
    ("sending", "returned"): "done",
    ("sending", "found"): "done",
    ("sending", "refused"): "failed",
    ("sending", "lost"): "unknown",
}


@pytest.mark.parametrize(("move", "after"), MOVES.items(), ids=[f"{s}-{e}" for s, e in MOVES])
def test_each_move_of_the_lifecycle(move: tuple[ActionState, FlowEvent], after: str) -> None:
    assert advance(*move) == after


def test_moved_gives_each_move_and_none_for_any_other() -> None:
    """The refusal-tolerant reading of the same table, for a caller that logs a refusal."""
    for state in ACTION_STATES:
        for event in FLOW_EVENTS:
            assert moved(state, event) == MOVES.get((state, event))


def test_every_other_move_is_refused_naming_its_state_and_event() -> None:
    refused = [
        (state, event)
        for state in ACTION_STATES
        for event in FLOW_EVENTS
        if (state, event) not in MOVES
    ]
    assert len(refused) == len(ACTION_STATES) * len(FLOW_EVENTS) - len(MOVES)
    for state, event in refused:
        with pytest.raises(ValueError, match=f"state {state} has no move on {event}"):
            advance(state, event)


def _reachable(start: ActionState, *, without: FlowEvent | None = None) -> set[ActionState]:
    seen, waiting = {start}, [start]
    while waiting:
        state = waiting.pop()
        for event in FLOW_EVENTS:
            if event == without or (state, event) not in MOVES:
                continue
            after = advance(state, event)
            if after not in seen:
                seen.add(after)
                waiting.append(after)
    return seen


def test_no_write_begins_without_the_yes_rules_yes() -> None:
    """Invariant 1 in the flow: without `yes`, a proposal reaches no write and no outcome of
    one."""
    assert _reachable("confirming", without="yes") == {"confirming", "declined"}
    assert _reachable("confirming") == set(ACTION_STATES)


def test_a_stop_over_the_read_back_ends_it_with_nothing_sent() -> None:
    """The owner's ruling: no receipt, the confirming state ends, nothing is sent; only a new
    read-back played in full, a new proposal, can earn a yes."""
    assert advance("confirming", "stop") == "declined"
    assert _reachable("declined") == {"declined"}


def test_a_repeat_or_an_ask_again_keeps_it_confirming_for_a_new_reading() -> None:
    assert advance("confirming", "repeat") == "confirming"
    assert advance("confirming", "asked_again") == "confirming"


@pytest.mark.parametrize("event", ["stop", "repeat", "no", "correction", "yes", "sent"])
def test_a_write_under_way_is_never_cut_or_sent_again(event: FlowEvent) -> None:
    with pytest.raises(ValueError):
        advance("sending", event)


@pytest.mark.parametrize("end", sorted(ENDS))
def test_an_end_is_never_left(end: ActionState) -> None:
    for event in FLOW_EVENTS:
        with pytest.raises(ValueError):
            advance(end, event)

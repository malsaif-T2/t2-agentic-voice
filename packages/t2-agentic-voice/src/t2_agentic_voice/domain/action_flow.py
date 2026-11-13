"""The states one action goes through (the design's 6.4 lifecycle), pure, so that no step belongs
to the model. A proposal enters `confirming` when its read-back starts to play, never when the
talker writes it, so a reply cancelled before it played leaves nothing behind. `confirmed` is
the yes rule's alone, and `sending` is written to the outbox before the write.

The moves (`advance`), each the only one its state and event have:

- **Confirming.** The yes rule's yes is `confirmed`. A plain no, a correction, a stop or pause
  word over the read-back (the owner's ruling, plan 007), and no clear answer after the last
  ask-again end it, `declined`, with nothing sent: the talker keeps the draft, and only a new
  read-back, played in full, a new proposal, can earn a yes. A request to hear it again, or an
  unclear answer with attempts left, keeps it `confirming`: the read-back is said again, or the
  caller asked again, and only a yes to that new reading counts (a new receipt).
- **Confirmed.** The outbox row written and the write begun is `sending`; refused before
  anything was sent, `failed`.
- **Sending.** The write returned, or the lookup after a lost reply found it: `done`. The backend
  refused it, or it was not sent (`ActionRejected`, `ActionNotSent`): `failed`. Its reply lost
  and no lookup found it: `unknown`. Nothing else: a stop never cuts a write in half.
- The four ends are never left.

The call's confirming state moves each read-back's action while it is `confirming`
(voice/session/read_back.py's `Confirming`), and the action runner's job from `confirmed` on
(actions/action_job.py's `Flow`); each logs a move the table refuses (`moved` gives None, `advance`
raises), never raising it into a call. The outbox's own states are domain/ports/outbox.py's.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Literal, get_args

# Where an action stands: its read-back playing or waiting for an answer; the caller's yes
# issued; the write under way; and its four ends (`declined` by the caller, `failed` definitely
# not done, `unknown` with no reply and no lookup hit, `done`).
ActionState = Literal["confirming", "confirmed", "sending", "done", "failed", "unknown", "declined"]
ACTION_STATES: tuple[ActionState, ...] = get_args(ActionState)
# The states an action never leaves.
ENDS: frozenset[ActionState] = frozenset({"done", "failed", "unknown", "declined"})
# What may happen to an action next: the yes rule's yes, no and correction; a stop or pause
# word over the read-back (`stop`), a request to hear it again (`repeat`), an unclear answer
# asked again (`asked_again`), and none clear after the last ask-again (`unclear`); the write
# begun (`sent`), returned, refused, its reply lost with no lookup hit (`lost`), or found by
# the lookup (`found`).
FlowEvent = Literal[
    "yes",
    "no",
    "correction",
    "stop",
    "repeat",
    "asked_again",
    "unclear",
    "sent",
    "returned",
    "refused",
    "lost",
    "found",
]
FLOW_EVENTS: tuple[FlowEvent, ...] = get_args(FlowEvent)

# Every move the lifecycle has (the module's docstring), by the state and the event.
_MOVES: Mapping[tuple[ActionState, FlowEvent], ActionState] = {
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


def moved(state: ActionState, event: FlowEvent) -> ActionState | None:
    """The state after `event` in `state`; None for a move the lifecycle has not."""
    return _MOVES.get((state, event))


def advance(state: ActionState, event: FlowEvent) -> ActionState:
    """The state after `event` in `state`; ValueError for a move the lifecycle has not."""
    after = moved(state, event)
    if after is None:
        raise ValueError(f"an action in state {state} has no move on {event}")
    return after

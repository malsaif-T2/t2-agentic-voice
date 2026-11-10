"""The states one action goes through (the design's 6.4 lifecycle), pure, so that no step belongs
to the model. A proposal enters `confirming` when its read-back starts to play, never when the
talker writes it, so a reply cancelled before it played leaves nothing behind. `confirmed` is
the yes rule's alone, and `sending` is written to the outbox before the write.

Plan 007's Track A fills `advance`; the outbox's own states are domain/ports/outbox.py's.
"""

from __future__ import annotations

from typing import Literal, get_args

# Where an action stands: its read-back playing or waiting for an answer; the caller's yes
# issued; the write under way; and its four ends (`declined` by the caller, `failed` definitely
# not done, `unknown` with no reply and no lookup hit, `done`).
ActionState = Literal["confirming", "confirmed", "sending", "done", "failed", "unknown", "declined"]
ACTION_STATES: tuple[ActionState, ...] = get_args(ActionState)
# The states an action never leaves.
ENDS: frozenset[ActionState] = frozenset({"done", "failed", "unknown", "declined"})
# What may happen to an action next.
FlowEvent = Literal["yes", "no", "correction", "sent", "returned", "refused", "lost", "found"]


def advance(state: ActionState, event: FlowEvent) -> ActionState:
    """The state after `event` in `state`; ValueError for a move the lifecycle has not."""
    raise NotImplementedError(f"plan 007's Track A fills advance ({state}, {event})")

"""Each read-back's action as the lifecycle's table moves it (domain/action_flow.py's `moved`),
for read_back.py's `Confirming`, which tells it what happened.

The action is `confirming` once its read-back is read (`began`), and moves as confirming ends or
goes on: the yes rule's yes is `yes`; a no or a correction, the yes rule's or words over the
summary, is `no` or `correction`, and a stop or pause word over it, or said whole while it is
confirming, `stop` (`declined`); no clear answer after the last ask-again is `unclear`, and one
asked again `asked_again`; said again at the caller's request is `repeat`, and a repeat request
answered instead of said again a `correction`. The client's `stop`, the read-back's reply ending
before its summary played whole and the call's end end confirming with no move, since the table
has no event for them.

A move the table refuses is a bug: logged at ERROR as `action_flow_refused`, by the call, the
action, the state and the event alone, the state kept, and never raised into the call, which
goes on as before (actions/action_job.py's `Flow` does the same for a job's moves).
"""

from __future__ import annotations

from collections.abc import Mapping

from t2_agentic_voice.core.conversation import DeclineKind
from t2_agentic_voice.core.events import CallId
from t2_agentic_voice.core.logging import get_logger
from t2_agentic_voice.domain.action_flow import ActionState, FlowEvent, moved

_log = get_logger(__name__)
# The table's event each way of declining a read-back is.
_DECLINED: Mapping[DeclineKind, FlowEvent] = {
    "no": "no",
    "correction": "correction",
    "stopped": "stop",
    "unclear": "unclear",
}


class ReadBackFlow:
    """The current or last read-back's `action` in the call `call_id`, and its `state` as the
    table moved it; None for both before any read-back."""

    def __init__(self, call_id: CallId) -> None:
        self._call_id = call_id
        self.action: str | None = None
        self.state: ActionState | None = None

    def began(self, action: str) -> None:
        """`action`'s read-back is read: it is `confirming`."""
        self.action, self.state = action, "confirming"

    def declined(self, kind: DeclineKind) -> None:
        """The caller declined the read-back, as `kind`."""
        self.move(_DECLINED[kind])

    def move(self, event: FlowEvent) -> None:
        """Move the action on `event` (the module's docstring)."""
        state = self.state
        after = None if state is None else moved(state, event)
        if after is None:
            _log.error(
                "action_flow_refused",
                call_id=self._call_id,
                action=self.action,
                state=state,
                flow_event=event,  # `event` is the log line's own name
            )
            return
        self.state = after

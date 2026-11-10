"""One call's record of completed actions (the design's 6.4; docs/SECURITY.md, invariant 2): the
proof the output guard reads, and the only place a `CompletedAction` is built. A per-call object
shared by the write's job, which adds to it, and by the talker and its guard, which read it live
through its whole reply.

Plan 007's Track B fills this.
"""

from __future__ import annotations

from t2_agentic_voice.domain.completed_action import CompletedAction

_TRACK = "plan 007's Track B fills the record"


class ActionRecord:
    """The completed actions of one call, oldest first."""

    def add(
        self,
        *,
        action: str,
        request_id: str,
        result_json: str,
        evidence: tuple[str, ...],
        at: float,
    ) -> CompletedAction:
        """Record that the write `request_id` of `action` really returned."""
        raise NotImplementedError(f"{_TRACK} ({action})")

    def entries(self) -> tuple[CompletedAction, ...]:
        """Each completed action so far."""
        raise NotImplementedError(_TRACK)

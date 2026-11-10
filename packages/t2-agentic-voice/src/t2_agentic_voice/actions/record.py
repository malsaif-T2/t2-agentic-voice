"""One call's record of completed actions (the design's 6.4; docs/SECURITY.md, invariant 2): the
proof the output guard reads, and the only place a `CompletedAction` is built. A per-call object
shared by the write's job, which adds to it, and by the talker and its guard, which read it live
through its whole reply.

The action runner keeps one record a call, keyed by the call's ID (`ActionRunner.record`), so
call A's entries never reach call B; only the runner's job adds to one, once a write really
returned or a lookup found it (a review: no check stops another caller of `add`).
"""

from __future__ import annotations

import json
from collections.abc import Iterator

from pydantic import BaseModel

from t2_agentic_voice.actions.tools import RecordedAction
from t2_agentic_voice.domain.completed_action import RECORD_SEAL, CompletedAction


def _leaves(value: object) -> Iterator[str]:
    if isinstance(value, dict):
        for each in value.values():
            yield from _leaves(each)
    elif isinstance(value, list):
        for each in value:
            yield from _leaves(each)
    elif isinstance(value, str):
        yield value
    elif isinstance(value, int | float) and not isinstance(value, bool):
        yield json.dumps(value)


def evidence_of(result: BaseModel) -> tuple[str, ...]:
    """The texts of a write's real `result` an ID-shaped token may be said from: each text and
    number it holds, at any depth."""
    return tuple(_leaves(result.model_dump(mode="json")))


class ActionRecord:
    """The completed actions of one call, oldest first."""

    def __init__(self) -> None:
        self._entries: list[CompletedAction] = []

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
        values = {
            "action": action,
            "request_id": request_id,
            "result_json": result_json,
            "evidence": tuple(evidence),
            "at": float(at),
        }
        entry = CompletedAction.model_validate(values, context=RECORD_SEAL)
        self._entries.append(entry)
        return entry

    def entries(self) -> tuple[CompletedAction, ...]:
        """Each completed action so far."""
        return tuple(self._entries)

    def holds(self, request_id: str) -> bool:
        """Whether the write `request_id` is recorded here."""
        return any(entry.request_id == request_id for entry in self._entries)

    def view(self) -> tuple[RecordedAction, ...]:
        """Each entry as plain values, as a tool or an action reads them (`CallContext.record`),
        which prove nothing."""
        return tuple(
            RecordedAction(
                action=entry.action,
                request_id=entry.request_id,
                result=json.loads(entry.result_json),
            )
            for entry in self._entries
        )

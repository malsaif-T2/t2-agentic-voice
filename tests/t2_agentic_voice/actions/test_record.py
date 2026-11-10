"""One call's record of completed actions (actions/record.py; docs/SECURITY.md, invariant 2): the
only builder of a `CompletedAction`, each sealed so only the record's own entries count as
proof; its entries oldest first, a plain view for tools and actions, and the evidence of a
result."""

from __future__ import annotations

import pytest
from pydantic import BaseModel
from t2_agentic_voice.actions.record import ActionRecord, evidence_of
from t2_agentic_voice.actions.tools import RecordedAction
from t2_agentic_voice.domain.completed_action import CompletedAction, is_recorded


class _Opened(BaseModel):
    number: str
    queue: str
    count: int
    urgent: bool
    note: str | None
    lines: list[str]
    nested: dict[str, float]


def test_an_entry_is_recorded_sealed_and_kept_in_order() -> None:
    record = ActionRecord()
    first = record.add(
        action="open_request",
        request_id="r-1",
        result_json='{"number": "1"}',
        evidence=("1",),
        at=3,
    )
    second = record.add(action="add_note", request_id="r-2", result_json="{}", evidence=(), at=4.5)
    assert record.entries() == (first, second)
    assert is_recorded(first) and is_recorded(second) and first.at == 3.0
    assert record.holds("r-1") and not record.holds("r-3")
    assert not is_recorded(first.model_copy())  # a copy proves nothing


def test_the_entries_are_a_snapshot_never_the_record_itself() -> None:
    record = ActionRecord()
    before = record.entries()
    record.add(action="open_request", request_id="r-1", result_json="{}", evidence=(), at=1.0)
    assert before == () and len(record.entries()) == 1


def test_a_completed_action_is_built_by_nothing_but_the_record() -> None:
    with pytest.raises(TypeError, match=r"Only actions/record\.py"):
        CompletedAction(action="open_request", request_id="r", result_json="{}", at=1.0)


def test_a_view_holds_plain_values_that_prove_nothing() -> None:
    record = ActionRecord()
    record.add(
        action="open_request", request_id="r-1", result_json='{"number": "7"}', evidence=(), at=1.0
    )
    [seen] = record.view()
    assert seen == RecordedAction(action="open_request", request_id="r-1", result={"number": "7"})
    assert not is_recorded(seen)


def test_the_evidence_of_a_result_is_every_text_and_number_in_it() -> None:
    opened = _Opened(
        number="2026111082000123",
        queue="support",
        count=3,
        urgent=True,
        note=None,
        lines=["a", "b"],
        nested={"score": 0.5},
    )
    assert evidence_of(opened) == ("2026111082000123", "support", "3", "a", "b", "0.5")

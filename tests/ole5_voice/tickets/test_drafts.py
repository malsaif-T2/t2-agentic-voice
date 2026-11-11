"""What the talker writes for Ole5's actions (ole5_voice/tickets/drafts.py): each draft parsed
strictly, a value outside a fixed set and a key the draft does not hold refused, naming the field
and never the value (docs/SECURITY.md, invariant 4); every type and priority said in Saudi
Arabic and English; a number in four groups; and the record's tickets read back, anything else
skipped."""

from __future__ import annotations

from pathlib import Path

import pytest
from ole5_voice.tickets.actions import add_ticket_note, create_ticket, hand_off
from ole5_voice.tickets.drafts import (
    PRIORITY_LABELS,
    TYPE_LABELS,
    HandoffDraft,
    NoteAdded,
    NoteDraft,
    TicketDraft,
    TicketMade,
    made_in,
)
from ole5_voice.tickets.system import TicketRef
from ole5_voice.tickets.values import DEFAULT_PRIORITY, PRIORITIES, TYPES
from pydantic import BaseModel, ValidationError
from t2_agentic_voice import RecordedAction

from tests.leaks import holding
from tests.ole5_voice.tickets.action_support import recorded
from tests.ole5_voice.tickets.ticket_support import SUMMARY, mock

REF = TicketRef(id="7", number="2026111082000917")


def _told(error: ValidationError) -> dict[str, str]:
    """What a refusal shows beside the errors the library's runner reads without their input
    (`include_input=False`): its text and its repr."""
    return {"text": str(error), "repr": repr(error)}


def _drafts(tmp_path: Path) -> dict[str, type[BaseModel]]:
    """Each action's draft as the talker's arguments are parsed into it (`Action.parameters`)."""
    system = mock(tmp_path)
    made = (create_ticket(system), add_ticket_note(system), hand_off(system))
    return {each.name: each.parameters for each in made}


def test_a_ticket_draft_holds_only_what_a_caller_can_answer() -> None:
    """Q5: what is wrong (the summary the model writes); the type the model picks, and the
    priority it sets (the next test). No queue, subtype, reason, email or customer: those are
    not the talker's."""
    assert set(TicketDraft.model_fields) == {"summary", "type", "priority"}
    draft = TicketDraft(summary=SUMMARY, type="Report")
    assert draft.priority == "Medium"  # unless the caller says how urgent it is
    assert set(NoteDraft.model_fields) == {"ticket_ends_in", "note"}
    assert set(HandoffDraft.model_fields) == {"summary"}


def test_the_talker_sets_the_priority_from_the_callers_words_and_never_asks(
    tmp_path: Path,
) -> None:
    """The owner's ruling of 2026-11-11: the priority is internal. The field, as the model is
    told of it, says to set it from what the caller said, Medium by default, and never to ask
    for it or say it; a draft with none holds Medium."""
    field = TicketDraft.model_fields["priority"]
    assert field.default == DEFAULT_PRIORITY == "Medium"
    schema = _drafts(tmp_path)["create_ticket"].model_json_schema()
    told = " ".join(str(schema["properties"]["priority"]["description"]).split())
    for needed in (
        "Set it yourself from what the caller said; never ask for it, and never say it to them.",
        "High when they say it is urgent or stops their work",
        "Low when they say it can wait",
        "Medium when they say nothing of it",
    ):
        assert needed in told, needed
    assert "how urgent it is:" not in told  # the old help, which waited for the caller to say


@pytest.mark.parametrize(
    ("name", "valid"),
    [
        ("create_ticket", {"summary": SUMMARY, "type": "Bug", "priority": "High"}),
        ("add_ticket_note", {"ticket_ends_in": "0917", "note": SUMMARY}),
        ("hand_off", {"summary": SUMMARY}),
    ],
)
def test_a_key_the_draft_does_not_hold_is_refused(
    name: str, valid: dict[str, str], tmp_path: Path
) -> None:
    """Invariants 1, 3 and 4: the talker can name no customer, no queue and no consent."""
    parameters = _drafts(tmp_path)[name]
    assert isinstance(parameters.model_validate(valid), BaseModel)
    for invented in ("customer_email", "email", "queue", "confirmed", "caller"):
        with pytest.raises(ValidationError) as caught:
            parameters.model_validate({**valid, invented: "someone.else@example.com"})
        assert holding("someone.else@example.com", _told(caught.value)) == []


@pytest.mark.parametrize(
    "changed",
    [
        {"type": "Complaint"},  # not one of the 11
        {"type": "bug"},  # not as the system writes it
        {"priority": "Urgent"},
        {"summary": "x" * 201},
        {"summary": "   "},
        {"summary": "Two lines\nof summary"},
        {"summary": "A summary with a \x00 control"},
    ],
)
def test_a_value_outside_its_set_or_its_shape_is_refused_naming_only_the_field(
    changed: dict[str, str],
) -> None:
    with pytest.raises(ValidationError) as caught:
        TicketDraft.model_validate({"summary": SUMMARY, "type": "Bug", **changed})
    [(field, value)] = changed.items()
    assert [error["loc"][0] for error in caught.value.errors()] == [field]
    if value.strip():
        assert holding(value, _told(caught.value)) == []


@pytest.mark.parametrize("ends_in", ["917", "09170", "٠٩١٧", "o917", ""])
def test_a_note_names_its_ticket_by_four_ascii_digits(ends_in: str) -> None:
    with pytest.raises(ValidationError):
        NoteDraft(ticket_ends_in=ends_in, note="The made-up report is the monthly one.")


def test_a_summary_is_kept_trimmed() -> None:
    assert TicketDraft(summary=f"  {SUMMARY} ", type="Bug").summary == SUMMARY


def test_every_type_and_priority_is_said_in_saudi_arabic_and_english() -> None:
    """And in MSA: the Saudi label, which MSA says alike, or the MSA one where it differs."""
    assert set(TYPE_LABELS) == set(TYPES) and len(TYPES) == 11
    assert set(PRIORITY_LABELS) == set(PRIORITIES)
    for labels in (*TYPE_LABELS.values(), *PRIORITY_LABELS.values()):
        assert {"ar-SA", "en"} <= set(labels) <= {"ar-SA", "ar", "en"}
        assert labels["en"].isascii() and not labels["ar-SA"].isascii()
    said = [labels["ar-SA"] for labels in TYPE_LABELS.values()]
    assert len(set(said)) == len(said)  # each type is told apart by its label
    # «nidhaam thaani», another system, is Saudi; MSA says «nidhaam aakhar».
    assert TYPE_LABELS["Request for Integration"]["ar"] == "طلب ربط مع نظام آخر"
    msa = [labels.get("ar", labels["ar-SA"]) for labels in TYPE_LABELS.values()]
    assert len(set(msa)) == len(msa)


def test_a_ticket_made_says_its_number_in_four_groups_the_last_its_last_four() -> None:
    made = TicketMade.of(REF)
    assert (made.part_1, made.part_2, made.part_3, made.part_4) == ("2026", "1110", "8200", "0917")
    assert made.last_four == "0917" and made.number == REF.number and made.ticket_id == "7"
    assert NoteAdded.of(REF).last_four == "0917"


def test_the_record_gives_back_only_the_tickets_its_makers_made() -> None:
    other = TicketRef(id="8", number="2026111082000918")
    entries = [
        recorded("create_ticket", REF),
        RecordedAction(action="create_ticket", request_id="req-2", result={"id": "made up"}),
        RecordedAction(action="create_ticket", request_id="req-3", result=None),
        recorded("add_ticket_note", other),  # a note makes no ticket
        recorded("search_knowledge", other),
        recorded("hand_off", other),
    ]
    found = made_in(entries)
    assert [(by, made.number) for by, made in found] == [
        ("create_ticket", REF.number),
        ("hand_off", other.number),
    ]

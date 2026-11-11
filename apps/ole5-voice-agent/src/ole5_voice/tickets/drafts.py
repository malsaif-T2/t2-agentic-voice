"""What the talker writes for Ole5's actions, and what each one gives back (plan 007's Q5, Q6
and Q7): the drafts, parsed strictly and read back to the caller, and the results the outcome
line is filled from and the record keeps.

- **A ticket's draft** holds a summary of what is wrong, which the model writes in the
  caller's language, at most `MAX_SUMMARY_CHARS`; one of the 11 types; and the priority,
  which is internal (the owner's ruling of 2026-11-11): the talker sets it from what the
  caller said, Medium when they say nothing of it, never asks for it and never says it, so
  the read-back leaves it out. The caller is asked only what is wrong. The queue follows the
  type (values.py's `QUEUE_OF`), and subtype and reason are left to support staff, so the
  talker is asked for neither. Each type and priority has its `Spoken` label in Saudi Arabic
  and English, and in MSA the Saudi label, which MSA says alike, but where it differs; the
  read-back says only the type's.
- **A note's draft** names a ticket made in this call by its number's last four digits, the
  way the caller hears it, and the note's text.
- **A handoff's draft** is the summary of what the caller needs from a person; the call's
  transcript goes with it, from the session, never from the talker (D-009, Q7).
- **The results:** a ticket made (`TicketMade`), its number in four groups of four digits so
  `done` says it digit by digit in groups (Q6), and a note added (`NoteAdded`), with the last
  four digits. `made_in` reads the tickets a list of recorded actions holds, parsed, any row
  that is not one skipped.

A summary and a note are one line of plain words, so the read-back says what will be sent; a
refusal names the field, never its value (invariant 4).
"""

from __future__ import annotations

import unicodedata
from collections.abc import Iterable
from typing import Annotated, Final

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, ValidationError
from t2_agentic_voice import RecordedAction, Spoken

from ole5_voice.tickets.system import MAX_SUMMARY_CHARS, Number, TicketId, TicketRef
from ole5_voice.tickets.values import DEFAULT_PRIORITY, Priority, TicketType

# The names the talker calls Ole5's actions by.
CREATE_TICKET: Final = "create_ticket"
ADD_NOTE: Final = "add_ticket_note"
HAND_OFF: Final = "hand_off"
# The actions that make a ticket, whose results a status reads.
MAKERS: Final = (CREATE_TICKET, HAND_OFF)
# The longest note the talker may write: read back word for word, so as short as a summary.
MAX_NOTE_CHARS: Final = MAX_SUMMARY_CHARS
# A number said in four groups of four digits (Q6), the last group its last four.
GROUP: Final = 4

# How each type is said: Saudi Arabic first, then English; MSA says the Saudi label, but where
# it gives its own (`ar`).
TYPE_LABELS: Final[dict[str, dict[str, str]]] = {
    "Bug": {"ar-SA": "خلل في النظام", "en": "bug"},
    "Infrastructure": {"ar-SA": "بنية تحتية", "en": "infrastructure"},
    "Inquiry": {"ar-SA": "استفسار", "en": "inquiry"},
    "Issue": {"ar-SA": "مشكلة", "en": "issue"},
    "Mobile App Issue": {"ar-SA": "مشكلة في تطبيق الجوال", "en": "mobile app issue"},
    "Report": {"ar-SA": "تقارير", "en": "report"},
    "Request for Integration": {
        "ar-SA": "طلب ربط مع نظام ثاني",
        "ar": "طلب ربط مع نظام آخر",  # talabu rabtin ma'a nidhaamin aakhar: with another system
        "en": "integration request",
    },
    "Request for Migration": {"ar-SA": "طلب نقل بيانات", "en": "migration request"},
    "Request for New Feature with Change Request": {
        "ar-SA": "طلب خاصية جديدة",
        "en": "new feature request",
    },
    "Request": {"ar-SA": "طلب", "en": "request"},
    "Reset Password": {"ar-SA": "إعادة تعيين كلمة المرور", "en": "password reset"},
}
PRIORITY_LABELS: Final[dict[str, dict[str, str]]] = {
    "Low": {"ar-SA": "منخفضة", "en": "low"},
    "Medium": {"ar-SA": "متوسطة", "en": "medium"},
    "High": {"ar-SA": "عالية", "en": "high"},
    "Critical": {"ar-SA": "حرجة", "en": "critical"},
}
SpokenType = Annotated[TicketType, Spoken(TYPE_LABELS)]
SpokenPriority = Annotated[Priority, Spoken(PRIORITY_LABELS)]

_TYPE_HELP: Final = (
    "The one type that fits best: Bug, something in Ole5 works wrongly or shows an error; "
    "Infrastructure, Ole5 as a whole is down or unreachable; Inquiry, a question for support "
    "staff; Issue, a problem using Ole5 that is not clearly a defect; Mobile App Issue, a problem "
    "in Ole5's mobile app; Report, about Ole5's reports; Request for Integration, connecting "
    "Ole5 with another system; Request for Migration, moving data into or out of Ole5; Request "
    "for New Feature with Change Request, a new feature or a change to Ole5; Request, any other "
    "request to support staff, such as a user or a permission; Reset Password, the caller "
    "cannot sign in and needs a new password."
)
_PRIORITY_HELP: Final = (
    "Set it yourself from what the caller said; never ask for it, and never say it to them. "
    "High when they say it is urgent or stops their work, Low when they say it can wait, "
    "Medium when they say nothing of it."
)


def _one_line(value: str) -> str:
    """`value`, trimmed, when it is one line of plain words; the error never repeats it."""
    value = value.strip()
    if any(unicodedata.category(c) in ("Cc", "Zl", "Zp") for c in value) or not value:
        raise ValueError("it is one line of plain words, read back to the caller as written")
    return value


def _digits(value: str) -> str:
    if not (value.isascii() and value.isdigit()):
        raise ValueError("it is the ticket number's last four digits, as ASCII digits")
    return value


Words = Annotated[str, AfterValidator(_one_line)]
LastFour = Annotated[str, Field(min_length=GROUP, max_length=GROUP), AfterValidator(_digits)]


class _Draft(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)


class TicketDraft(_Draft):
    """A ticket to open (the module's docstring)."""

    summary: Annotated[
        Words,
        Field(
            max_length=MAX_SUMMARY_CHARS,
            description=(
                "What is wrong, in one or two short sentences you write in the caller's "
                "language from what they said, at most 200 characters. It is read back to them."
            ),
        ),
    ]
    type: Annotated[SpokenType, Field(description=_TYPE_HELP)]
    priority: Annotated[SpokenPriority, Field(description=_PRIORITY_HELP)] = DEFAULT_PRIORITY


class NoteDraft(_Draft):
    """A note for a ticket made in this call (the module's docstring)."""

    ticket_ends_in: Annotated[
        LastFour,
        Field(description="The last four digits of the number of a ticket made in this call."),
    ]
    note: Annotated[
        Words,
        Field(
            max_length=MAX_NOTE_CHARS,
            description=(
                "What to add or correct, in one or two short sentences you write in the "
                "caller's language, at most 200 characters. It is read back to them."
            ),
        ),
    ]


class HandoffDraft(_Draft):
    """A request passed to support staff (the module's docstring)."""

    summary: Annotated[
        Words,
        Field(
            max_length=MAX_SUMMARY_CHARS,
            description=(
                "What the caller needs from a person, in one or two short sentences you write "
                "in the caller's language, at most 200 characters. It is read back to them."
            ),
        ),
    ]


class _Result(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class TicketMade(_Result):
    """A ticket the ticket system made: its ID, its number, and the number's four groups."""

    ticket_id: TicketId
    number: Number
    part_1: str
    part_2: str
    part_3: str
    part_4: str

    @classmethod
    def of(cls, ref: TicketRef) -> TicketMade:
        """The result for the ticket `ref` names."""
        parts = [ref.number[n : n + GROUP] for n in range(0, len(ref.number), GROUP)]
        return cls(
            ticket_id=ref.id,
            number=ref.number,
            part_1=parts[0],
            part_2=parts[1],
            part_3=parts[2],
            part_4=parts[3],
        )

    @property
    def last_four(self) -> str:
        """The number's last four digits, what a status says."""
        return self.part_4


class NoteAdded(_Result):
    """A note the ticket system added: the ticket's ID, its number and its last four digits."""

    ticket_id: TicketId
    number: Number
    last_four: str

    @classmethod
    def of(cls, ref: TicketRef) -> NoteAdded:
        """The result for a note on the ticket `ref` names."""
        return cls(ticket_id=ref.id, number=ref.number, last_four=ref.number[-GROUP:])


def made_in(entries: Iterable[RecordedAction]) -> list[tuple[str, TicketMade]]:
    """The tickets `entries` made, each with the action that made it, in their order: each
    entry of an action in `MAKERS` whose result is a `TicketMade`, any other skipped."""
    found = []
    for entry in entries:
        if entry.action not in MAKERS:
            continue
        try:
            found.append((entry.action, TicketMade.model_validate(entry.result)))
        except ValidationError:
            continue
    return found

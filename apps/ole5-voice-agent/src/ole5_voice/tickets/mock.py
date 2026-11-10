"""The mock ticket system (plan 007's Q2): what a demo runs on and what proves the actions work,
since the owner has no access to the real one. A `TicketSystem` (system.py).

- **Kept in one file**, `tickets.json` in the folder it is given (the app's settings give it,
  by default under the app's var/ folder: settings.py's `tickets_folder`), read on first use
  and written whole on each write, through a temporary file it then renames, so a reopen finds
  every ticket. It makes no folder and reads nothing until it is first used, and makes its
  folder only on its first write.
- **Numbers in the real shape:** 16 digits, the date in Riyadh (`YYYYMMDD`), `82`, and a
  six-digit counter that starts again each day; its IDs count up from 1.
- **Modes**, one for its writes (`create`, `add_note`) and one for its reads (`get`, `find`),
  each set by the settings or a test, and read as a call starts: `answer`; `refuse`, which
  raises TicketRefused and changes nothing; `timeout`, which waits `late_s` and raises
  TicketTimeoutError, having done nothing; and `late`, which does the call at once and answers
  only after `late_s`, so a lookup in the meantime finds the write. `late_s` (30 s) is above an
  action's default timeout (20 s).
- **The lookup** by request ID (`can_find`) can be switched off, as the real system would have
  it; `find` then raises LookupUnavailableError. It never dedupes a request ID, so a write sent
  twice shows as two tickets.
- **Scoped by customer:** `get`, `find` and `add_note` see only the tickets of the email they
  are given, compared without case.

`listed()` gives every ticket whatever the modes, for the page (page.py). The calls do their
file work with no await between reading and writing, so two calls on one event loop never
interleave a write; the file is small, so its blocking IO is short. No log line holds a
ticket's values, only the call and the mode.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterable
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Final, Literal, get_args

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, ValidationError
from t2_agentic_voice import ConfigurationError, ConversationLine, get_logger

from ole5_voice.tickets.system import (
    MAX_NOTE_CHARS,
    Email,
    LookupUnavailableError,
    NewNote,
    NewTicket,
    RequestId,
    Ticket,
    TicketRef,
    TicketRefused,
    TicketTimeoutError,
)
from ole5_voice.tickets.values import NEW_STATUS

# How the mock answers a call (the module's docstring).
Mode = Literal["answer", "refuse", "timeout", "late"]
MODES: Final[tuple[Mode, ...]] = get_args(Mode)
LATE_S: Final = 30.0
FILE_NAME: Final = "tickets.json"
# The two digits between a number's date and its counter (the owner's examples, plan 002).
SYSTEM_ID: Final = "82"
MAX_COUNTER: Final = 999_999
# Riyadh's time, three hours ahead of UTC all year: Saudi Arabia keeps no daylight saving.
RIYADH: Final = timezone(timedelta(hours=3), "+03")

log = get_logger(__name__)


def riyadh_now() -> datetime:
    """The time now in Riyadh, aware: the mock's clock unless a test gives its own."""
    return datetime.now(RIYADH)


class MockNote(BaseModel):
    """A note on a mock ticket: the write's request ID, its text and when it was added."""

    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

    request_id: RequestId
    text: str = Field(min_length=1, max_length=MAX_NOTE_CHARS, repr=False)
    created_at: AwareDatetime


class MockTicket(Ticket):
    """A ticket as the mock keeps it: `get`'s fields, the request ID of the write that made it,
    the customer's email, the call's transcript (a handoff's) and its notes."""

    request_id: RequestId
    customer_email: Email
    transcript: tuple[ConversationLine, ...] = ()
    notes: tuple[MockNote, ...] = ()


class _Kept(BaseModel):
    """The mock's file."""

    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

    tickets: tuple[MockTicket, ...] = ()


class MockTicketSystem:
    """The mock, kept in `folder`, its writes answered by `mode` and its reads by `read_mode`,
    finding writes by their request ID when `lookup`, a late or timed-out call taking `late_s`,
    on `clock` (aware). Built with no IO."""

    def __init__(
        self,
        folder: Path,
        *,
        mode: Mode = "answer",
        read_mode: Mode = "answer",
        lookup: bool = True,
        late_s: float = LATE_S,
        clock: Callable[[], datetime] = riyadh_now,
    ) -> None:
        self.folder = folder
        self.mode: Mode = mode
        self.read_mode: Mode = read_mode
        self.can_find = lookup
        self.late_s = late_s
        self._clock = clock
        self._tickets: tuple[MockTicket, ...] | None = None

    @property
    def path(self) -> Path:
        """The file the tickets are kept in."""
        return self.folder / FILE_NAME

    async def create(self, ticket: NewTicket) -> TicketRef:
        """Create `ticket`, as the mode says (the module's docstring)."""
        mode = self.mode
        await self._fail(mode, "create")
        kept = self._loaded()
        now = self._clock()
        made = MockTicket(
            id=_next_id(kept),
            number=_number(kept, now),
            queue=ticket.queue,
            type=ticket.type,
            priority=ticket.priority,
            status=NEW_STATUS,
            summary=ticket.summary,
            created_at=now,
            request_id=ticket.request_id,
            customer_email=ticket.customer_email,
            transcript=ticket.transcript,
        )
        self._save((*kept, made))
        log.info("mock_ticket_written", call="create", mode=mode)
        await self._late(mode)
        return TicketRef(id=made.id, number=made.number)

    async def get(self, ticket_id: str, *, customer_email: str) -> Ticket | None:
        """The ticket `ticket_id` when it is `customer_email`'s, as the read mode says."""
        mode = self.read_mode
        await self._fail(mode, "get")
        found = _theirs(self._loaded(), customer_email, lambda t: t.id == ticket_id)
        await self._late(mode)
        if found is None:
            return None
        return Ticket.model_validate(found.model_dump(include=set(Ticket.model_fields)))

    async def add_note(self, note: NewNote) -> TicketRef:
        """Add `note` to its ticket when that ticket is the note's customer's, as the mode
        says; TicketRefused (`not_found`) otherwise."""
        mode = self.mode
        await self._fail(mode, "add_note")
        kept = self._loaded()
        found = _theirs(kept, note.customer_email, lambda t: t.id == note.ticket_id)
        if found is None:
            raise TicketRefused("not_found")
        added = MockNote(request_id=note.request_id, text=note.text, created_at=self._clock())
        noted = found.model_copy(update={"notes": (*found.notes, added)})
        self._save(tuple(noted if t is found else t for t in kept))
        log.info("mock_ticket_written", call="add_note", mode=mode)
        await self._late(mode)
        return TicketRef(id=found.id, number=found.number)

    async def find(self, request_id: str, *, customer_email: str) -> TicketRef | None:
        """The ticket the write `request_id` made or added a note to, when it is
        `customer_email`'s, as the read mode says; LookupUnavailableError when the lookup is
        off."""
        if not self.can_find:
            raise LookupUnavailableError()
        mode = self.read_mode
        await self._fail(mode, "find")
        found = _theirs(
            self._loaded(),
            customer_email,
            lambda t: (
                t.request_id == request_id or any(n.request_id == request_id for n in t.notes)
            ),
        )
        await self._late(mode)
        return None if found is None else TicketRef(id=found.id, number=found.number)

    def listed(self) -> tuple[MockTicket, ...]:
        """Every ticket, oldest first, whatever the modes: what the page shows."""
        return self._loaded()

    async def _fail(self, mode: Mode, call: str) -> None:
        """Refuse, or wait and time out, when `mode` says so."""
        if mode == "refuse":
            log.info("mock_ticket_refused", call=call)
            raise TicketRefused("refused")
        if mode == "timeout":
            log.info("mock_ticket_timing_out", call=call, seconds=self.late_s)
            await asyncio.sleep(self.late_s)
            raise TicketTimeoutError()

    async def _late(self, mode: Mode) -> None:
        """Wait `late_s` before answering, when `mode` is `late`."""
        if mode == "late":
            await asyncio.sleep(self.late_s)

    def _loaded(self) -> tuple[MockTicket, ...]:
        """The tickets, read from the file on first use (none when it does not exist yet)."""
        if self._tickets is None:
            self._tickets = _read(self.path)
        return self._tickets

    def _save(self, tickets: tuple[MockTicket, ...]) -> None:
        """Write `tickets` whole, through a temporary file renamed over the last one."""
        self.folder.mkdir(parents=True, exist_ok=True)
        written = self.path.with_name(f"{FILE_NAME}.tmp")
        written.write_text(_Kept(tickets=tickets).model_dump_json(indent=2), encoding="utf-8")
        written.replace(self.path)
        self._tickets = tickets


def _read(path: Path) -> tuple[MockTicket, ...]:
    """The tickets kept in `path`, none when it does not exist; a ConfigurationError naming
    the file, never its content, when it is not the mock's."""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ()
    try:
        return _Kept.model_validate_json(text).tickets
    except ValidationError:
        pass  # its errors may hold the file's values: not chained
    raise ConfigurationError(
        f"The mock ticket system's file {path} does not hold its tickets. FIX: move the file "
        "aside to start with no tickets, or mend it.",
        details={"file": str(path)},
    )


def _next_id(kept: Iterable[MockTicket]) -> str:
    """The ID after the highest kept: the IDs count up from 1."""
    ids = (int(t.id) for t in kept if t.id.isascii() and t.id.isdigit())
    return str(1 + max(ids, default=0))


def _number(kept: Iterable[MockTicket], now: datetime) -> str:
    """The next ticket number on `now`'s day: its date, SYSTEM_ID and the day's next counter;
    TicketRefused (`full`) past MAX_COUNTER."""
    day = f"{now:%Y%m%d}{SYSTEM_ID}"
    counter = 1 + max(
        (int(t.number[len(day) :]) for t in kept if t.number.startswith(day)), default=0
    )
    if counter > MAX_COUNTER:
        raise TicketRefused("full")
    return f"{day}{counter:06d}"


def _theirs(
    kept: Iterable[MockTicket], customer_email: str, wanted: Callable[[MockTicket], bool]
) -> MockTicket | None:
    """The first ticket of `customer_email`'s (compared without case) that is `wanted`."""
    email = customer_email.strip().casefold()
    return next(
        (t for t in kept if t.customer_email.strip().casefold() == email and wanted(t)), None
    )

"""The writes of an action runner (actions/action_runner.py), each confirmed action carried out
as a job of its own (the design's 6.4; docs/SECURITY.md, invariants 2 and 6), and the rows a
start finds left `sending`.

- **A job** is started by `start`, which waits for it shielded: a stop, a cancel of the caller's
  wait or the call's end never cuts it in half, and it runs to its end. Its request ID comes
  from the confirmed action (`request_id_of`), so the same one asked twice finds its row
  (`INSERT OR IGNORE`) and is never written again: its row's outcome is said, with no event.
  Otherwise the row is written `sending` before the write; the write's meaning
  (actions/action_writes.py) marks the row `done`, `rejected`, `not_sent` or `flagged`, after a
  lookup by the request ID when no reply came; only `done` adds a `CompletedAction` to the
  call's record. A row that cannot be written means nothing was sent: `failed`. A row that
  cannot be marked stays as it was, for `reconcile` at the next start.
- **`reconcile`** looks up each row left `sending` by an earlier process, never sending it
  again: found, `done`; else, or with no lookup, `flagged`. Asked to (`t2v outbox reconcile`),
  it looks each `flagged` row up again too: found, `done`; else left as it was. The outbox
  keeps no consent words and no language, so the lookup is told none (English).

The outcome's line is the action's `done`, `failed` or `unknown`, or the library's; a `done`
the result cannot fill says the library's `unknown`, which claims nothing. `ActionCompleted` or
`ActionUnconfirmed` goes to `emit` as each job ends.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from functools import partial
from typing import Final

from pydantic import BaseModel, ValidationError

from t2_agentic_voice.actions.action import Action, ActionContext, HeardConsent
from t2_agentic_voice.actions.action_writes import Refused, Returned, look_up, write
from t2_agentic_voice.actions.record import ActionRecord, evidence_of
from t2_agentic_voice.actions.spoken_lines import outcome_line
from t2_agentic_voice.actions.tools import RecordedAction
from t2_agentic_voice.core.clock import Clock
from t2_agentic_voice.core.conversation import ConversationLine
from t2_agentic_voice.core.events import ActionCompleted, ActionUnconfirmed, CallId, Event, TurnId
from t2_agentic_voice.core.identity import Caller
from t2_agentic_voice.core.logging import get_logger
from t2_agentic_voice.core.settings.tts import LanguageTag
from t2_agentic_voice.domain.action_lines import SpokenLine, default_action_lines
from t2_agentic_voice.domain.ports.action_jobs import ActionOutcome, OutcomeKind
from t2_agentic_voice.domain.ports.outbox import Outbox, OutboxEntry, OutboxState
from t2_agentic_voice.domain.yes_rule import ConfirmedAction

_log = get_logger(__name__)
# Where the runner's public events go: the runtime's observers (voice/session/io.py's
# `EventSink`, which `actions` may not import).
EventSink = Callable[[Event], None]
# The namespace of the request IDs, each a UUID 5 of the call and the confirmed action.
_REQUESTS = uuid.UUID("6f3a7c2e-0b1d-5e8f-9a4c-2d7e1b5f8c30")
_UNKEPT = HeardConsent(words="", source="speech_to_text", speech_at=None)
_START_LANGUAGE: Final[LanguageTag] = "en"


def request_id_of(call_id: CallId, confirmed: ConfirmedAction) -> str:
    """The request ID of `confirmed` in the call `call_id`: the same for the same confirmed
    action, so a job asked twice finds its row and never writes again."""
    parts = (call_id, confirmed.action, str(confirmed.reply_id), str(confirmed.turn_id))
    return str(uuid.uuid5(_REQUESTS, "\n".join((*parts, confirmed.draft_json))))


@dataclass(frozen=True, slots=True)
class JobCall:
    """What a job knows of the call that confirmed it, and the call's record."""

    caller: Caller
    call_id: CallId
    language: LanguageTag
    turn_id: TurnId
    conversation: tuple[ConversationLine, ...]
    clock: Clock
    record: ActionRecord


class Writes:
    """The jobs of one runner, against its `outbox`, their events to `emit`."""

    def __init__(self, outbox: Outbox, emit: EventSink | None) -> None:
        self._outbox = outbox
        self._emit = emit
        self._jobs: set[asyncio.Future[ActionOutcome]] = set()
        self.running: set[str] = set()

    async def start(
        self, action: Action, confirmed: ConfirmedAction, call: JobCall
    ) -> ActionOutcome:
        """Carry out `confirmed` as a job, and wait for its outcome, shielded."""
        job = asyncio.ensure_future(self._job(action, confirmed, call))
        self._jobs.add(job)
        job.add_done_callback(self._finished)
        return await asyncio.shield(job)

    def _finished(self, job: asyncio.Future[ActionOutcome]) -> None:
        """A job ended: let go of it, and log a failure no one may be waiting to hear of."""
        self._jobs.discard(job)
        if not job.cancelled() and (error := job.exception()) is not None:
            _log.error("action_job_failed", failure=type(error).__qualname__)

    async def _job(
        self, action: Action, confirmed: ConfirmedAction, call: JobCall
    ) -> ActionOutcome:
        request_id = request_id_of(call.call_id, confirmed)
        try:
            draft = action.parameters.model_validate_json(confirmed.draft_json)
        except ValidationError:
            _log.error("action_draft_unreadable", action=action.name)
            return self._ended(action, request_id, "failed", call)
        now = call.clock.wall()
        entry = OutboxEntry(
            request_id=request_id,
            call_id=call.call_id,
            subject=call.caller.subject,
            action=action.name,
            draft_json=confirmed.draft_json,
            created_at=now,
            updated_at=now,
        )
        try:
            added = await self._outbox.add(entry)
        except Exception as error:  # nothing was sent: definitely not done
            _log.error("outbox_unwritten", action=action.name, failure=type(error).__qualname__)
            return self._ended(action, request_id, "failed", call, draft=draft)
        if not added:
            return await self._again(action, request_id, draft, call)
        self.running.add(request_id)
        try:
            return await self._carried_out(action, confirmed, request_id, draft, call)
        finally:
            self.running.discard(request_id)

    async def _carried_out(
        self,
        action: Action,
        confirmed: ConfirmedAction,
        request_id: str,
        draft: BaseModel,
        call: JobCall,
    ) -> ActionOutcome:
        consent = HeardConsent(
            words=confirmed.words, source=confirmed.source, speech_at=confirmed.speech_at
        )
        ctx = ActionContext(
            caller=call.caller,
            call_id=call.call_id,
            language=call.language,
            record=call.record.view(),
            request_id=request_id,
            consent=consent,
            conversation=call.conversation,
        ).reading_past(partial(done_rows, self._outbox))
        written = await write(action, ctx, draft, call.clock)
        if isinstance(written, Returned):
            return await self._done(action, request_id, written.result, call)
        if isinstance(written, Refused):
            await mark_row(self._outbox, request_id, state=written.state, note=written.state)
            return self._ended(action, request_id, "failed", call, draft=draft)
        found = await look_up(action, ctx, call.clock)
        if found is not None:
            return await self._done(action, request_id, found, call, note="looked_up")
        missed = "not_found" if action.finder is not None else "no_lookup"
        note = f"{written.note}, {missed}"
        await mark_row(self._outbox, request_id, state="flagged", note=note)
        return self._ended(action, request_id, "unknown", call, draft=draft)

    async def _done(
        self,
        action: Action,
        request_id: str,
        result: BaseModel,
        call: JobCall,
        *,
        note: str | None = None,
    ) -> ActionOutcome:
        """The write returned or was found: recorded, then its row marked."""
        _recorded(action, request_id, result, call)
        result_json = result.model_dump_json()
        await mark_row(self._outbox, request_id, state="done", note=note, result_json=result_json)
        return self._ended(action, request_id, "done", call, result=result)

    async def _again(
        self, action: Action, request_id: str, draft: BaseModel, call: JobCall
    ) -> ActionOutcome:
        """A confirmed action carried out before: never written again, its row's outcome said."""
        _log.info("action_asked_twice", action=action.name)
        try:
            row = await self._outbox.get(request_id)
        except Exception as error:
            _log.error("outbox_unread", action=action.name, failure=type(error).__qualname__)
            row = None
        result = _stored_result(action, row)
        if result is not None:
            if not call.record.holds(request_id):
                _recorded(action, request_id, result, call)
            return self._ended(action, request_id, "done", call, result=result, emit=False)
        kind: OutcomeKind = "unknown"
        if row is not None and row.state in ("rejected", "not_sent"):
            kind = "failed"
        return self._ended(action, request_id, kind, call, draft=draft, emit=False)

    def _ended(
        self,
        action: Action,
        request_id: str,
        kind: OutcomeKind,
        call: JobCall,
        *,
        draft: BaseModel | None = None,
        result: BaseModel | None = None,
        emit: bool = True,
    ) -> ActionOutcome:
        """How the write ended, its line said in the call's language, and its event."""
        line = _line(action, kind, draft=draft, result=result, tag=call.language)
        if emit and self._emit is not None:
            at = call.clock.wall()
            event: Event
            if kind == "done":
                event = ActionCompleted(
                    call_id=call.call_id,
                    turn_id=call.turn_id,
                    at=at,
                    action=action.name,
                    request_id=request_id,
                )
            else:
                event = ActionUnconfirmed(
                    call_id=call.call_id,
                    turn_id=call.turn_id,
                    at=at,
                    action=action.name,
                    request_id=request_id,
                    kind=kind,
                )
            self._emit(event)
        return ActionOutcome(action=action.name, request_id=request_id, kind=kind, line=line)

    async def reconcile(
        self, actions: Mapping[str, Action], clock: Clock, *, flagged: bool = False
    ) -> int:
        """Look up or flag every row left `sending` but those of the jobs under way here; with
        `flagged`, look the flagged rows up again too, one not found left as it was."""
        rows = await self._outbox.entries(state="sending")
        if flagged:
            rows += await self._outbox.entries(state="flagged")
        waiting = [row for row in rows if row.request_id not in self.running]
        for row in waiting:
            await self._reconciled(actions.get(row.action), row, clock)
        _log.info("outbox_reconciled", rows=len(waiting))
        return len(waiting)

    async def _reconciled(self, action: Action | None, row: OutboxEntry, clock: Clock) -> None:
        if row.state == "flagged" and (action is None or action.finder is None):
            return  # nothing more to learn of it: its note stays
        if action is None or action.finder is None:
            note = "no_such_action" if action is None else "no_lookup"
            await mark_row(self._outbox, row.request_id, state="flagged", note=f"left, {note}")
            return
        ctx = ActionContext(
            caller=Caller(subject=row.subject),
            call_id=row.call_id,
            language=_START_LANGUAGE,
            request_id=row.request_id,
            consent=_UNKEPT,
        )
        found = await look_up(action, ctx, clock)
        if found is None:
            if row.state != "flagged":
                await mark_row(
                    self._outbox, row.request_id, state="flagged", note="left, not_found"
                )
            return
        result_json = found.model_dump_json()
        await mark_row(
            self._outbox, row.request_id, state="done", note="looked_up", result_json=result_json
        )


async def done_rows(outbox: Outbox, subject: str, action: str) -> tuple[RecordedAction, ...]:
    """The writes of `action` done for the caller `subject`, in any call, oldest first: the
    outbox's `done` rows, as plain values. A row whose result cannot be read is left out,
    logged by the action's name alone."""
    rows = await outbox.entries(state="done", subject=subject, action=action)
    found: list[RecordedAction] = []
    for row in rows:
        try:
            result = json.loads(row.result_json or "null")
            found.append(
                RecordedAction(action=row.action, request_id=row.request_id, result=result)
            )
        except (ValueError, ValidationError):
            _log.error("outbox_result_unreadable", action=action)
    return tuple(found)


async def mark_row(
    outbox: Outbox,
    request_id: str,
    *,
    state: OutboxState,
    note: str | None,
    result_json: str | None = None,
) -> None:
    """Move a row on; one that cannot be moved stays as it was, for `reconcile`."""
    try:
        await outbox.mark(request_id, state=state, note=note, result_json=result_json)
    except Exception as error:
        _log.error("outbox_unmarked", state=state, failure=type(error).__qualname__)


def _recorded(action: Action, request_id: str, result: BaseModel, call: JobCall) -> None:
    call.record.add(
        action=action.name,
        request_id=request_id,
        result_json=result.model_dump_json(),
        evidence=evidence_of(result),
        at=call.clock.now(),
    )


def _stored_result(action: Action, row: OutboxEntry | None) -> BaseModel | None:
    """The result a `done` row holds, parsed; None for any other row."""
    if row is None or row.state != "done" or row.result_json is None:
        return None
    try:
        return action.result.model_validate_json(row.result_json)
    except ValidationError:
        return None


def _line(
    action: Action,
    kind: OutcomeKind,
    *,
    draft: BaseModel | None,
    result: BaseModel | None,
    tag: LanguageTag,
) -> SpokenLine:
    """The outcome's line; the library's `unknown` when the action's own cannot be said."""
    try:
        return outcome_line(action, kind, draft=draft, result=result, tag=tag)
    except (KeyError, ValueError):
        _log.error("action_line_unsaid", action=action.name, kind=kind)
        lines = default_action_lines(tag)
        text = lines.failed if kind == "failed" else lines.unknown
        return SpokenLine(text=text, spoken=text)

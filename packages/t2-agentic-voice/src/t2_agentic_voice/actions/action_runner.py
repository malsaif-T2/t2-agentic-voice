"""The action runner (the design's 6.4 lifecycle), what an action's call is handed to, as the tool
runner is for a tool. One serves every call of an agent, against its outbox.

- **`propose`** answers the talker's call inside the turn and writes nothing: the arguments
  parsed into the action's draft (a missing or extra field, or a value outside a fixed set,
  told back with the field named and never the value, invariant 4); its `validate`, run as a
  read within the action's `timeout_s`, a `ToolError` told to the talker and any other failure
  a generic one; the caps, counted over the outbox's rows, which only a `ConfirmedAction`
  writes, never over proposals: `max_per_call` of the action in this call, and
  `per_caller_per_day` (`limits.actions_per_caller_per_day`) of it for the verified caller in
  the last day, each counting only a write that may have reached the system (`sending`, `done`,
  `flagged`), never one refused or never sent (`NOT_WRITTEN`), so the caller may try again;
  then the read-back rendered in the reply's language (actions/spoken_lines.py), its texts read
  in `wording` when the talker gives one (MSA, `ar`, for an `ar-SA` reply to an MSA caller:
  agent/language.py's `wording`), which the plan keeps for the outcome's line.
- **`run`** meets the `ActionJobs` port: it takes only a `ConfirmedAction` the yes rule issued
  (`is_confirmed`; anything else is a TypeError, and nothing is written or sent), and carries
  it out as a job outside the turn (actions/action_job.py): the outbox row before the write,
  the error meanings, the lookup, the record, and the outcome's line, read in the read-back's
  `wording` (its language when none is given). The session builds each outcome's event from
  the `ActionOutcome` it is returned (core/events.py: `voice` builds the events).
- **`reconcile`**, at the runtime's start, looks up or flags each row left `sending`; it never
  sends one again. `t2v outbox reconcile` looks the flagged rows up again too.
- **`past`** reads what a caller had done, in any call: the outbox's `done` rows
  (`CallContext.past_actions`).

Each call's record is kept here by the call's ID (`record`), so call A's entries never reach
call B; the runtime drops it with `forget` once the call has ended. A runner given one call's
`record` (`TextCall`'s) fills that one instead. No log line or error holds a draft's value, a
result, the caller's words or a reason a backend gave.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import timedelta
from typing import Final

from pydantic import BaseModel

from t2_agentic_voice.actions.action import Action
from t2_agentic_voice.actions.action_job import JobCall, Writes, done_rows
from t2_agentic_voice.actions.action_writes import parsed_result, validated
from t2_agentic_voice.actions.record import ActionRecord
from t2_agentic_voice.actions.runner import FAILED, failed_result, parsed_arguments
from t2_agentic_voice.actions.spoken_lines import read_back_plan
from t2_agentic_voice.actions.tools import CallContext, RecordedAction, ToolResult
from t2_agentic_voice.core.clock import SYSTEM_CLOCK, Clock
from t2_agentic_voice.core.conversation import ConversationLine
from t2_agentic_voice.core.errors import ConfigurationError, ToolError
from t2_agentic_voice.core.events import CallId, TurnId
from t2_agentic_voice.core.identity import Caller
from t2_agentic_voice.core.logging import get_logger
from t2_agentic_voice.core.settings.limits import LimitSettings
from t2_agentic_voice.core.settings.tts import LanguageTag
from t2_agentic_voice.domain.action_lines import ReadBackPlan
from t2_agentic_voice.domain.ports.action_jobs import ActionOutcome
from t2_agentic_voice.domain.ports.chat_model import ToolCallRequest, ToolSchema
from t2_agentic_voice.domain.ports.outbox import NOT_WRITTEN, Outbox
from t2_agentic_voice.domain.yes_rule import ConfirmedAction, is_confirmed

_log = get_logger(__name__)
# How many of one action one caller may have done in a day, unless the runtime passes the
# settings' `limits.actions_per_caller_per_day`.
PER_CALLER_PER_DAY: Final = LimitSettings().actions_per_caller_per_day
_DAY = timedelta(days=1)
# What the talker is told of a cap reached and of a draft the read-back cannot say.
PER_CALL = "this cannot be done again in this call: tell the caller so, and do not call it again"
PER_DAY = "the caller has had this done as many times as one day allows: tell them so"
UNSAID = "the read-back cannot be said with this draft: give every field it reads"
NOT_CONFIRMED = (
    "The action runner carries out only a ConfirmedAction the yes rule issued, unchanged; it "
    "wrote nothing. FIX: pass on the one decide() returned inside a Yes."
)
_ACTIONS_FIX = "FIX: build each action with @action, each with its own name."


class ActionRunner:
    """One agent's `actions`, against its `outbox`, for every call (the module's docstring).
    Given `record` (one call's, as `TextCall` gives it), every job adds to that one."""

    def __init__(
        self,
        actions: Sequence[Action],
        *,
        outbox: Outbox,
        record: ActionRecord | None = None,
        per_caller_per_day: int = PER_CALLER_PER_DAY,
    ) -> None:
        if not all(isinstance(each, Action) for each in actions):
            raise ConfigurationError(
                f"The runner takes only actions. {_ACTIONS_FIX}", details={"field": "actions"}
            )
        self.actions = tuple(actions)
        self._by_name = {each.name: each for each in self.actions}
        if len(self._by_name) != len(self.actions):
            raise ConfigurationError(
                f"Two actions share a name. {_ACTIONS_FIX}", details={"field": "actions"}
            )
        self._outbox = outbox
        self._per_day = per_caller_per_day
        self._writes = Writes(outbox)
        self._record = record
        self._records: dict[str, ActionRecord] = {}

    def schemas(self) -> tuple[ToolSchema, ...]:
        """Each action as the talker is told of it, in order."""
        return tuple(each.tool_schema() for each in self.actions)

    def action(self, name: str) -> Action | None:
        """The action named `name`, None for a name the agent has none of."""
        return self._by_name.get(name)

    def record(self, call_id: CallId) -> ActionRecord:
        """The record of the call `call_id`, shared by its jobs and its talker's guard: the one
        the runner was given, when it was given one."""
        if self._record is not None:
            return self._record
        return self._records.setdefault(call_id, ActionRecord())

    def forget(self, call_id: CallId) -> None:
        """Drop the call's record once the call has ended; a job still running keeps its own. A
        record the runner was given stays its giver's."""
        self._records.pop(call_id, None)

    async def past(self, subject: str, action: str) -> tuple[RecordedAction, ...]:
        """The writes of `action` done for the caller `subject`, in any call, oldest first
        (actions/action_job.py's `done_rows`; `CallContext.past_actions` reads them)."""
        return await done_rows(self._outbox, subject, action)

    async def propose(
        self,
        request: ToolCallRequest,
        ctx: CallContext,
        *,
        clock: Clock = SYSTEM_CLOCK,
        wording: LanguageTag | None = None,
    ) -> ReadBackPlan | ToolResult:
        """The read-back of the call `request` names, its texts read in `wording` (the reply's
        language unless given), or a failed result the talker reads, naming the field at
        fault. Writes nothing; a cancelled early start leaves nothing."""
        action = self._by_name.get(request.name)
        if action is None:
            names = ", ".join(self._by_name) or "none"
            message = f"there is no action named `{request.name}`; the actions are: {names}"
            return failed_result(message, "no_such_action")
        parsed = parsed_arguments(action.parameters, request.arguments)
        if isinstance(parsed, ToolResult):
            return parsed
        draft = await self._validated(action, ctx, parsed, clock)
        if isinstance(draft, ToolResult):
            return draft
        capped = await self._capped(action, ctx, clock)
        if capped is not None:
            return capped
        try:
            return read_back_plan(
                action, draft, tool_call_id=request.id, tag=ctx.language, wording=wording
            )
        except (KeyError, ValueError):
            _log.error("action_read_back_unsaid", action=action.name)
            return failed_result(UNSAID, "read_back_unsaid")

    async def _validated(
        self, action: Action, ctx: CallContext, draft: BaseModel, clock: Clock
    ) -> BaseModel | ToolResult:
        """`draft` as the action's `validate` keeps it, or the failed result the talker reads."""
        gave, kept = await validated(action, ctx, draft, clock)
        if not gave:
            return failed_result(FAILED, "validate_failed")
        if isinstance(kept, ToolError):
            return failed_result(kept.message, "draft_rejected")
        if kept is None:
            return draft
        again = None
        if isinstance(kept, action.draft):
            again = parsed_result(action.parameters, kept.model_dump(by_alias=True))
        if again is None:
            _log.error("action_validate_unreadable", action=action.name)
            return failed_result(FAILED, "validate_failed")
        return again

    async def _capped(self, action: Action, ctx: CallContext, clock: Clock) -> ToolResult | None:
        """The failed result of a cap the action has reached, None when it has reached none;
        each counts only the writes that may have reached the system."""
        subject = ctx.caller.subject
        try:
            rows = await self._outbox.entries(subject=subject, action=action.name)
            today = await self._outbox.count(
                subject=subject, action=action.name, since=clock.wall() - _DAY
            )
        except Exception as error:
            _log.error("outbox_unread", action=action.name, failure=type(error).__qualname__)
            return failed_result(FAILED, "outbox_unread")
        in_call = sum(row.call_id == ctx.call_id and row.state not in NOT_WRITTEN for row in rows)
        if in_call >= action.max_per_call:
            return failed_result(PER_CALL, "cap_per_call")
        if today >= self._per_day:
            return failed_result(PER_DAY, "cap_per_caller")
        return None

    async def run(
        self,
        confirmed: ConfirmedAction,
        *,
        caller: Caller,
        call_id: CallId,
        language: LanguageTag,
        turn_id: TurnId,
        conversation: tuple[ConversationLine, ...],
        clock: Clock,
        wording: LanguageTag | None = None,
    ) -> ActionOutcome:
        """Carries out `confirmed` (the `ActionJobs` port; the module's docstring). The port's
        `turn_id` names the turn that said yes, which the session's events carry."""
        if not is_confirmed(confirmed):
            _log.warning("action_not_confirmed")
            raise TypeError(NOT_CONFIRMED)
        action = self._by_name.get(confirmed.action)
        if action is None:
            raise ConfigurationError(
                f"A confirmed action names none of the runner's. {_ACTIONS_FIX}",
                details={"field": "actions"},
            )
        record = self.record(call_id)
        read = wording or language
        call = JobCall(caller, call_id, language, conversation, clock, record, read)
        return await self._writes.start(action, confirmed, call)

    async def reconcile(self, *, clock: Clock = SYSTEM_CLOCK, flagged: bool = False) -> int:
        """Looks up or flags every row left `sending`, never sending one again; how many. A row
        whose write is under way in this process is left to its job. With `flagged`
        (`t2v outbox reconcile`), each flagged row is looked up again: found, it is done; else
        it stays as it was."""
        return await self._writes.reconcile(self._by_name, clock, flagged=flagged)

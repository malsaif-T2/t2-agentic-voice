"""The action runner (the design's 6.4 lifecycle), what an action's call is handed to, as the tool
runner is for a tool. `propose` answers the talker's call inside the turn: the draft parsed, its
`validate`, the caps counted over confirmed actions only, the read-back rendered. `run` meets
the `ActionJobs` port and carries out a confirmed action as a job outside the turn: the outbox
row before the write, the error meanings, the lookup, the record. It holds no call's state, as
the tool runner does, except what each call's job passes in.

Plan 007's Track B fills this.
"""

from __future__ import annotations

from collections.abc import Sequence

from t2_agentic_voice.actions.action import Action
from t2_agentic_voice.actions.record import ActionRecord
from t2_agentic_voice.actions.tools import CallContext, ToolResult
from t2_agentic_voice.core.clock import Clock
from t2_agentic_voice.core.conversation import ConversationLine
from t2_agentic_voice.core.events import CallId, TurnId
from t2_agentic_voice.core.identity import Caller
from t2_agentic_voice.core.settings.tts import LanguageTag
from t2_agentic_voice.domain.action_lines import ReadBackPlan
from t2_agentic_voice.domain.ports.action_jobs import ActionOutcome
from t2_agentic_voice.domain.ports.chat_model import ToolCallRequest, ToolSchema
from t2_agentic_voice.domain.ports.outbox import Outbox
from t2_agentic_voice.domain.yes_rule import ConfirmedAction

_TRACK = "plan 007's Track B fills the action runner"


class ActionRunner:
    """One agent's `actions`, against its `outbox`; one call's `record` passed in to each job."""

    def __init__(
        self, actions: Sequence[Action], *, outbox: Outbox, record: ActionRecord | None = None
    ) -> None:
        self.actions = tuple(actions)
        self._outbox = outbox
        self._record = record

    def schemas(self) -> tuple[ToolSchema, ...]:
        """Each action as the talker is told of it, in order."""
        return tuple(each.tool_schema() for each in self.actions)

    async def propose(
        self, request: ToolCallRequest, ctx: CallContext
    ) -> ReadBackPlan | ToolResult:
        """The read-back of the call `request` names, or a failed result the talker reads,
        naming the field at fault. Writes nothing; a cancelled early start leaves nothing."""
        raise NotImplementedError(f"{_TRACK} ({request.name})")

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
    ) -> ActionOutcome:
        """Carries out `confirmed` (the `ActionJobs` port)."""
        raise NotImplementedError(f"{_TRACK} ({confirmed.action})")

    async def reconcile(self) -> int:
        """Looks up or flags every row left `sending`, never sending one again; how many."""
        raise NotImplementedError(_TRACK)

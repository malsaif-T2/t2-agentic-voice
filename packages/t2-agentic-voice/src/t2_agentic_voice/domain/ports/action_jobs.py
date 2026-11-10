"""How a confirmed action reaches the part that acts: `voice` may not import `actions`
(harness.toml [layers]), so the session holds this port and the api layer injects
`actions`' runner, as `CallSetup.action_jobs`. Internal; not on the `ports` facade.

`run` is started as a task of its own, outside every reply's cancel scope and off the session's
lock, so a stop never cuts a write in half (docs/SECURITY.md, invariant 6). The call's end does
not cancel it either.
"""

from __future__ import annotations

from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from t2_agentic_voice.core.clock import Clock
from t2_agentic_voice.core.conversation import ConversationLine
from t2_agentic_voice.core.events import CallId, TurnId
from t2_agentic_voice.core.identity import Caller
from t2_agentic_voice.core.settings.tts import LanguageTag
from t2_agentic_voice.domain.action_lines import SpokenLine
from t2_agentic_voice.domain.yes_rule import ConfirmedAction

# How a write ended: it returned or a lookup found it (`done`); it was definitely not done
# (`failed`); or no reply came and no lookup found it (`unknown`, with no number).
OutcomeKind = Literal["done", "failed", "unknown"]


class ActionOutcome(BaseModel):
    """How one write ended: the `action`, its `request_id`, the `kind`, the `line` the
    session speaks at the next turn boundary, from the action's own template, and, for `done`,
    the write's real result as JSON text (`result_json`, as the call's record holds it; empty
    otherwise), for the session's `ActionCompleted`."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    action: str = Field(min_length=1)
    request_id: str = Field(min_length=1)
    kind: OutcomeKind
    line: SpokenLine
    result_json: str = Field(default="", repr=False)


class ActionJobs(Protocol):
    """What the session asks of the part that acts."""

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
        """Write the outbox row, run the action, wait for its reply or its timeout, look it up
        when the reply was lost, and say how it ended; a failure of the write is an outcome,
        never an exception. `confirmed` is refused unless `is_confirmed`."""

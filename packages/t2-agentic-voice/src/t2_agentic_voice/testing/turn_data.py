"""What one turn of a `TextCall` did, as data (plan 006): the shapes `TextTurn`'s reads give, so a
runner that scores a call (a judge of the reply, its language, a search made when needed, the
guard's blocks, the time to the first clause) reads what the caller heard and what the talker
did through the public `evals` facade, never through the talker's own events, which are not
public. Frozen, a misspelt key an error. Plan 006's Track C fills them from the session and the
talker; this module holds their shapes.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

from t2_agentic_voice.core.conversation import ClauseFate
from t2_agentic_voice.core.settings.base import FROZEN, PLAIN
from t2_agentic_voice.core.settings.tts import LanguageTag

# What came of a tool call: it returned (`ok`); it `failed` (a `ToolError`, any other failure,
# or its timeout); a barge-in or a stop `cancelled` it; or it is still `running` (a tool whose
# barge-in is `finish`, read before it ends).
ToolOutcome = Literal["ok", "failed", "cancelled", "running"]


class _Data(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class HeardClause(_Data):
    """One clause of the turn's reply as the caller heard it: its text, as the output guard let
    it through and the fake text-to-speech played it; its language; what became of it, and the
    share of its audio that played (1 played, 0 unplayed, the share when cut: core/conversation.py's
    `SaidClause`); whether it was a fixed phrase from the phrase cache (`phrase`: a progress
    line, or the guard's line said in a blocked clause's place) rather than the talker's words;
    and whether it was a line of the runtime's own for an action (`template`: a read-back's
    summary or closing question, an ask-again, `declined`, `sending` or an outcome's line), the
    agent's template filled with the draft's or the result's values, which the output guard
    never checks (testing/text_read_back.py), so a runner reads the talker's register without
    it."""

    text: str
    language: LanguageTag
    fate: ClauseFate
    played_fraction: float = Field(ge=0, le=1, allow_inf_nan=False)
    phrase: bool = False
    template: bool = False

    @model_validator(mode="after")
    def _share_of_its_fate(self) -> Self:
        whole = {"played": 1.0, "unplayed": 0.0}.get(self.fate)
        if whole is not None and self.played_fraction != whole:
            raise ValueError("a played clause played 1 of its audio, an unplayed one 0")
        return self


class TextToolCall(_Data):
    """A tool call the turn's reply made: the model's id for it, the tool's name, the arguments
    the model wrote, parsed as JSON (empty when they were not a JSON object; a bound parameter is
    the caller's, never among them), what came of it, how long it ran on the call's clock in
    milliseconds, None while it runs, and when it began, in seconds on the call's clock from the
    moment the turn's words were handed to the session, as the turn's other times are (`began_s`,
    None when not known), so a runner can take the tools' time out of the reply's."""

    call_id: str = Field(min_length=1)
    tool: str = Field(min_length=1)
    arguments: Annotated[Mapping[str, JsonValue], FROZEN, PLAIN] = Field(default_factory=dict)
    outcome: ToolOutcome
    ms: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    began_s: float | None = Field(default=None, ge=0, allow_inf_nan=False)

    @model_validator(mode="after")
    def _timed_once_ended(self) -> Self:
        if (self.outcome == "running") != (self.ms is None):
            raise ValueError("a tool call that ended has its time, one still running none")
        return self


class BlockedClause(_Data):
    """A clause of the turn's reply that the output guard blocked (rule B), never spoken: its
    text and language, and the ID-shaped tokens it held with no evidence."""

    text: str
    language: LanguageTag
    unsupported: tuple[str, ...] = ()

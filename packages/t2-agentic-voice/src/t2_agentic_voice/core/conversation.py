"""The call so far as the talker reads it (plan 006, "What voice-first means here", item 1): what
the caller heard, never what the agent meant to say. The voice session builds these plain models
from its heard history (voice/session/history.py) for each turn it hands the talker; the talker
(agent/) turns them into the model's messages. They live in core, the lowest layer both `voice`
and `agent` import (harness.toml [layers]).

Each of the caller's turns keeps its heard words and what became of it (`TurnFate`); each of the
agent's replies keeps its clauses, each `played` (all of its audio), `cut` (a stop or the call's
end cut it while it played, with the share of its audio that played; a clause's words are never
split, Orpheus giving no word times) or `unplayed`. The turn handed to the talker carries its own
heard words, the language its transcript was heard in, the reply its speech began over, if any,
and the reply it cut, if any. Frozen, a misspelt key an error.
"""

from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from t2_agentic_voice.core.events import ReplyId, TurnId
from t2_agentic_voice.core.yes_inputs import ActionName

# What became of a clause of a reply: it played whole, a stop cut it while it played, or it
# never played.
ClauseFate = Literal["played", "cut", "unplayed"]
# What became of one of the caller's turns: still being answered (`pending`); answered, its
# reply played whole; its reply `cut` after a clause played, or `rolled_back`, cut before any
# did; taken as a command (a stop, a pause, a repeat), not answered; an overlap after which the
# reply `went_on`; `dropped` by the drop rule; or `unfinished`, the call ended first.
TurnFate = Literal[
    "pending", "answered", "cut", "rolled_back", "command", "went_on", "dropped", "unfinished"
]
# How the caller declined an action's read-back (the design's 6.4): a whole no answer; other
# words, a correction the talker may answer with a new draft; a stop or pause word over it, or
# said whole while it waits, after which the talker asks what to change, its draft kept (the
# owner's stop ruling); or no clear answer after the read-back's `max_attempts`.
DeclineKind = Literal["no", "correction", "stopped", "unclear"]
# A language as a transcript names it, in the provider's code ("ar", "en"): its shortest and
# longest.
_HEARD_CHARS = (2, 16)
_Heard = Annotated[str, Field(min_length=_HEARD_CHARS[0], max_length=_HEARD_CHARS[1])]


def heard_language(language: str | None) -> str | None:
    """`language`, a transcript's, as a `TalkerTurn` takes it: None for none, or for a name
    shorter or longer than a language's (`_Heard`)."""
    shortest, longest = _HEARD_CHARS
    return language if language is not None and shortest <= len(language) <= longest else None


class _Plain(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


def check_share(fate: ClauseFate, played_fraction: float) -> None:
    """Raise ValueError unless `played_fraction` is the share of a clause's audio its `fate`
    allows: 1 for one played, 0 for one unplayed, any for one cut. A model's validator calls it,
    here and in the testing kit's `HeardClause` (testing/turn_data.py)."""
    whole = {"played": 1.0, "unplayed": 0.0}.get(fate)
    if whole is not None and played_fraction != whole:
        raise ValueError("a played clause played 1 of its audio, an unplayed one 0")


class SaidClause(_Plain):
    """One clause of a reply as the caller heard it: its text, what became of it, and the share
    of its audio that played: 1 for one played, 0 for one unplayed, the share for one cut."""

    text: str
    fate: ClauseFate
    played_fraction: float = Field(ge=0, le=1, allow_inf_nan=False)

    @model_validator(mode="after")
    def _share_of_its_fate(self) -> Self:
        check_share(self.fate, self.played_fraction)
        return self


class SaidReply(_Plain):
    """One of the agent's replies as the caller heard it: its number, the caller's turn it
    answers (None for the greeting or a notice), and its clauses in order."""

    reply_id: ReplyId
    turn_id: TurnId | None = None
    clauses: tuple[SaidClause, ...] = ()


class PastTurn(_Plain):
    """One of the caller's turns: its heard words ("" when nothing was heard), what became of
    it, and the reply that answers it, if any."""

    turn_id: TurnId
    words: str
    fate: TurnFate
    reply_id: ReplyId | None = None


class Conversation(_Plain):
    """The call's heard history before the turn the talker answers: each turn and each reply,
    in order."""

    turns: tuple[PastTurn, ...] = ()
    replies: tuple[SaidReply, ...] = ()


class ConversationLine(_Plain):
    """One thing said in a call, as an action may attach it for the people who read its record
    (plan 007's Q7): who said it and the words, as the caller heard them."""

    speaker: Literal["caller", "agent"]
    text: str = Field(repr=False)


class DeclinedAction(_Plain):
    """An action the caller did not confirm, as the talker learns of it in the turn after: its
    name, how it was declined (`kind`, so the talker can tell a no from a correction), and the
    words heard ("" when nothing was).

    Who speaks, as the owner rules (plan 007): after a plain no (`no`) the talker always
    answers, in its own words, and after a `correction` too; after a stop (`stopped`) it asks
    what to change, keeping its draft. The action's fixed `declined` line
    (`ReadBackPlan.declined`) is the session's only where no talker turn can answer: nothing
    usable heard after the last ask-again (`unclear`)."""

    action: ActionName
    kind: DeclineKind
    words: str = Field(repr=False)


class TalkerTurn(_Plain):
    """One turn of the caller's, as the session hands it to the talker: its number; its heard
    words, whole (a turn the caller went on with after a pause, within the hold, is one turn);
    the language its transcript was heard in (None when the provider named none); the tag of the
    language it asked the call to move to (`asked`, a spoken switch request under
    `stt.live_language = "detected"`; None for none), which its reply is in; the reply its
    speech began over (`over_reply`, None when it was said while the agent was silent) and the
    reply it stopped (`cut_reply`, None when it stopped none; a turn said alone may stop a
    reply to an earlier turn before it played); the action this turn declined, if any; and the
    call so far."""

    turn_id: TurnId
    words: str = Field(min_length=1)
    language: _Heard | None = None
    asked: _Heard | None = None
    over_reply: ReplyId | None = None
    cut_reply: ReplyId | None = None
    declined: DeclinedAction | None = None
    conversation: Conversation = Field(default_factory=Conversation)

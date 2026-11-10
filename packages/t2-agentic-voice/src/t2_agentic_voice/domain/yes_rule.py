"""The yes rule (the design's 8.3; docs/SECURITY.md, invariant 1): the only thing that issues a
`ConfirmedAction`, and only from two inputs no other layer can make, the heard words and the
read-back receipt that `voice` builds (core/yes_inputs.py). The action runner accepts nothing
else, so no tool argument or model output can stand in for a yes.

A `ConfirmedAction` takes its action and its draft from the receipt, so the draft confirmed is
the draft the caller heard. `decide` is pure. It reads only `heard`, the turn's own transcript
(never a held or overlap one), against the receipt's times: words whose speech began before the
summary ended count for nothing; while `question_ended_at` is None or the speech began before
it, the words are over the closing question, where a yes needs a send word; with neither, a yes
stands alone among fillers and send words. A whole no answer is declined, other words a
correction, and nothing heard is asked again. Typed words count only under `env` `test`.

Plan 007's Track A fills `decide`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar, Final, final

from pydantic import Field

from t2_agentic_voice.core.config import Environment
from t2_agentic_voice.core.events import ReplyId, TurnId
from t2_agentic_voice.core.seal import SealedModel, still_sealed
from t2_agentic_voice.core.yes_inputs import HeardSource, HeardWords, ReadBackReceipt
from t2_agentic_voice.domain.yes_words import ConsentWords

# The seal a validation of a `ConfirmedAction` must be given; only this module names it.
CONFIRMED_SEAL: Final[object] = object()


@final
class ConfirmedAction(SealedModel):
    """An action the caller said yes to, as the yes rule issued it: the action and the draft
    (`draft_json`, the receipt's own) and the reply that read it back; the turn that said yes,
    its words and their source and when they began. Built only in this module."""

    refusal: ClassVar[str] = (
        "Only domain/yes_rule.py issues a ConfirmedAction, from heard words and a read-back "
        "receipt; call decide() instead of building one."
    )

    action: str = Field(min_length=1)
    draft_json: str = Field(min_length=2, repr=False)
    reply_id: ReplyId
    turn_id: TurnId
    words: str = Field(repr=False)
    source: HeardSource
    speech_at: float

    def model_post_init(self, context: Any, /) -> None:
        self._seal_with(context, CONFIRMED_SEAL)


def is_confirmed(value: object) -> bool:
    """Whether `value` is a confirmed action only the yes rule issued, unchanged since. The
    action runner asks this before anything else."""
    return type(value) is ConfirmedAction and still_sealed(value)


@dataclass(frozen=True, slots=True)
class Yes:
    """A yes: `confirmed`, the only way to one."""

    confirmed: ConfirmedAction


@dataclass(frozen=True, slots=True)
class Declined:
    """The caller said no: `words`, what was heard."""

    words: str


@dataclass(frozen=True, slots=True)
class Correction:
    """The caller said something else: `words` go to the talker, with the draft declined."""

    words: str


@dataclass(frozen=True, slots=True)
class AskAgain:
    """Unclear, or nothing heard: asked again, at most the read-back's `max_attempts` times."""


type YesOutcome = Yes | Declined | Correction | AskAgain


def _issued(heard: HeardWords, receipt: ReadBackReceipt, *, speech_at: float) -> ConfirmedAction:
    """The confirmed action of `receipt`'s draft, `heard` saying yes to it."""
    values = {
        "action": receipt.action,
        "draft_json": receipt.draft_json,
        "reply_id": receipt.reply_id,
        "turn_id": heard.turn_id,
        "words": heard.text,
        "source": heard.source,
        "speech_at": speech_at,
    }
    return ConfirmedAction.model_validate(values, context=CONFIRMED_SEAL)


def decide(
    heard: HeardWords | None,
    receipt: ReadBackReceipt,
    *,
    words: ConsentWords,
    env: Environment,
) -> YesOutcome:
    """What the turn's own `heard` words (None when nothing was heard) say to the read-back
    `receipt` stands for (the module's docstring). `heard` and `receipt` must pass their own
    checks (`is_heard_words`, `is_read_back_receipt`): anything else counts for nothing. Returns
    the `ConfirmedAction` only inside a `Yes`."""
    raise NotImplementedError(f"plan 007's Track A fills decide ({env})")

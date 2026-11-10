"""The yes rule (the design's 8.3; docs/SECURITY.md, invariant 1): the only thing that issues a
`ConfirmedAction`, and only from two inputs no other layer can make, the heard words and the
read-back receipt that `voice` builds (core/yes_inputs.py). The action runner accepts nothing
else, so no tool argument or model output can stand in for a yes.

A `ConfirmedAction` takes its action and its draft from the receipt, so the draft confirmed is
the draft the caller heard. `decide` is pure. It reads only `heard`, the turn's own transcript
(never a held or overlap one), against the receipt's times, in this order:

1. **Counts for nothing**, asked again as if nothing was heard: heard words or a receipt that
   fail their own checks (`is_heard_words`, `is_read_back_receipt`: built elsewhere, a copy,
   or changed since); typed words unless `env` is `test`; words whose speech began before the
   summary ended (`speech_at`, never `at`: Whisper gives no partials, so a yes said over the
   summary arrives after it), or with no `speech_at`, which reads as said before anything. A
   new reading of the read-back is a new receipt, so a yes said before it ended counts for
   nothing either.
2. The words in the rule's form, read as the interruption rule reads them (each listed phrase
   one word, the longest first; a send word may be written after waw, and): nothing left is
   **asked again**; any word on none of the lists (`ConsentWords`) is a **correction**, the
   words going to the talker, so a yes with a change in it is never a yes.
3. A no word, with no yes word beside it, is **declined**; with one, unclear, and **asked
   again**.
4. A yes word, among only send words and fillers and with no question mark (a yes asked back is
   no answer), is a **yes** after the closing question ended. Over it (`question_ended_at` None,
   or the speech began before it) it needs a send word too; a bare yes there is **asked
   again**. Send words or fillers with no yes word are asked again: a closing question holds a
   send word, and its echo must confirm nothing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar, Final, Literal, final

from pydantic import Field

from t2_agentic_voice.core.config import Environment
from t2_agentic_voice.core.events import ReplyId, TurnId
from t2_agentic_voice.core.seal import SealedModel, still_sealed
from t2_agentic_voice.core.yes_inputs import (
    HeardSource,
    HeardWords,
    ReadBackReceipt,
    is_heard_words,
    is_read_back_receipt,
)
from t2_agentic_voice.domain.interruption_words import QUESTION_MARKS
from t2_agentic_voice.domain.words import rule_form
from t2_agentic_voice.domain.yes_words import ConsentWords

# What one word of the heard words is to the rule: on a list, or on none (`content`).
_Kind = Literal["no", "yes", "send", "filler", "content"]
_AND = "و"  # waw, and

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


def _listed(words: ConsentWords) -> dict[str, _Kind]:
    """Each listed word or phrase with its kind; one on two lists takes the first of no, yes,
    send and filler, so a word a team adds as a yes is never only a filler."""
    listed: dict[str, _Kind] = {}
    lists: tuple[tuple[_Kind, tuple[str, ...]], ...] = (
        ("filler", words.fillers),
        ("send", words.send),
        ("yes", words.yes),
        ("no", words.no),
    )
    for kind, phrases in lists:
        listed.update(dict.fromkeys(phrases, kind))
    return listed


def _kinds(text: str, words: ConsentWords) -> set[_Kind]:
    """The kinds of the words of `text`, in the rule's form, each listed phrase one word, the
    longest that starts at a word first; a word on no list after waw (and) is a send word when
    the rest of it is one."""
    listed = _listed(words)
    heard = text.split()
    longest = max((len(phrase.split()) for phrase in listed), default=1)
    found: set[_Kind] = set()
    at = 0
    while at < len(heard):
        sizes = range(min(longest, len(heard) - at), 0, -1)
        size = next((n for n in sizes if " ".join(heard[at : at + n]) in listed), 1)
        word = " ".join(heard[at : at + size])
        kind = listed.get(word)
        if kind is None and word.startswith(_AND) and listed.get(word[1:]) == "send":
            kind = "send"
        found.add(kind or "content")
        at += size
    return found


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
    if heard is None or not is_heard_words(heard) or not is_read_back_receipt(receipt):
        return AskAgain()
    if heard.source != "speech_to_text" and env != "test":
        return AskAgain()
    began = heard.speech_at
    if began is None or began < receipt.summary_played_at:
        return AskAgain()
    kinds = _kinds(rule_form(heard.text), words)
    if not kinds:
        return AskAgain()
    if "content" in kinds:
        return Correction(words=heard.text)
    if "no" in kinds:
        return AskAgain() if "yes" in kinds else Declined(words=heard.text)
    if "yes" not in kinds or any(mark in heard.text for mark in QUESTION_MARKS):
        return AskAgain()
    ended = receipt.question_ended_at
    if (ended is None or began < ended) and "send" not in kinds:
        return AskAgain()
    return Yes(confirmed=_issued(heard, receipt, speech_at=began))

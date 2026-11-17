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
   send word, and the lists cannot tell its echo from the caller's own go-ahead.

**What the lists leave unplaced** (D-082; the owner's rulings of 2026-11-10). `decide` marks
three of its answers `askable`: a correction for a word on none of the lists; send words alone
or among fillers with no yes word and no question mark (arsilha, send it, said alone, and yalla
arsilha, come on, send it, are unclear to the lists); and a yes among fillers over the closing
question with no send word. For an agent that asks (`VoiceAgent.ask_on_unlisted_answers`), the
session puts those words to a chat model (domain/consent_check.py) and hands its word to
`judged`, which keeps the lists' every other answer and never takes the model's word as it is:
its `send` or `yes` is a yes only when the words hold no no word and no question mark (else
asked again), no change marker (else a correction), are not the agent's own words heard back
(else asked again), and the receipt built when the turn began still stands (else asked again);
over the closing question only its `send` confirms, or its `yes` beside a send word and other
words, its `yes` alone or to a send word alone asked again. Its `no` is declined and its
`change` a correction, but on the agent's own words heard back (the echo rail) each is asked
again, as its `yes` is; anything else is asked again. No word at all (the request failed or ran
out of its time) is asked again too, unless the words hold a no word of the lists: then it is
declined, as the model's `no` is, and asked again only on the agent's own words heard back
(the owner's "Yes, all three", 2026-11-11, after run A's a3-dev, where a no that asked for
another ticket, asked again, let the next yes make the ticket dropped). The model is told that
a question, or a request for something else, is a `no` (the owner's answer of 2026-11-11), so
the turn goes to the talker, which answers it. An agent that does not ask takes `decide`'s
answer as is.

**A plain no** (`plain_no`, domain/yes_kinds.py): a no word with only send words and fillers
beside it, the words `decide` declines once the summary played. The session reads what cuts the
summary with it, so a cancel said over the summary is declined as a no, not a correction (D-081).

**The echo rail** (the owner's third ruling, 2026-11-10; on the model's `no` and `change` too,
2026-11-11, and on no word with a no word): a model's word, or no word, on the agent's own
lines heard back is asked again, so its echo never confirms, cancels or changes a read-back.
Words that copy them, read as the interruption rule reads its own words heard back (every word
a word of the lines heard, or one edit from one of three letters or more), are its echo only
when the speech began while those lines were heard: while its reply played, or within its
tail after it ended, the drop rule's window (`DROP_AFTER_S` after a reply's end, none after
the caller's own stop), the agent's voice leaked past the browser's echo cancellation. Over
the closing question (by the receipt), or as the session tells it (`SaidLines.over_read_back`),
that is the read-back's summary and question; as the session tells it of a line that asked it
again (`SaidLines.over_asked_again`), the ask-again line; each True when the session cannot
tell. Speech begun when none of them was heard cannot be the agent's echo, so a caller who
answers arsilha once the question and its tail ended can send. Only the rail's window has the
tail: a yes over the closing question is still one whose speech began before the question
ended (`question_ended_at`, the receipt's).

**Any yes books** (D-108, the owner's ruling of 2026-11-17), only for a call under
`interruptions.yes_over_read_back`, which hands `decide` the read-back's lines (`said`) and
`judged` its `bare`: over the closing question a bare yes, a yes among fillers, is a yes, and
the model's plain `yes` too, but to a send word alone; and khalas beside a send word, with only
fillers else, is a yes (`holds_okay`), each unless the words are the agent's own lines heard
back. `held` issues a yes held over the summary (domain/yes_kinds.py's `held_yes`), its speech
begun after the summary's first audio and before its last clause played, once the receipt
stands for that summary played whole.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar, Final, final

from pydantic import Field

from t2_agentic_voice.core.config import Environment
from t2_agentic_voice.core.events import ReplyId, TurnId
from t2_agentic_voice.core.seal import SealedModel, still_sealed
from t2_agentic_voice.core.yes_inputs import (
    ActionName,
    DraftJson,
    HeardSource,
    HeardWords,
    ReadBackReceipt,
    is_heard_words,
    is_read_back_receipt,
)
from t2_agentic_voice.domain.interruption_words import QUESTION_MARKS
from t2_agentic_voice.domain.words import rule_form
from t2_agentic_voice.domain.yes_kinds import ModelWord as ModelWord
from t2_agentic_voice.domain.yes_kinds import SaidLines as SaidLines
from t2_agentic_voice.domain.yes_kinds import (
    echoes,
    held_yes,
    holds_okay,
    kinds,
    marked,
    playing,
)
from t2_agentic_voice.domain.yes_kinds import plain_no as plain_no
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

    action: ActionName
    draft_json: DraftJson
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
    """The caller said something else: `words` go to the talker, with the draft declined.
    `askable`, when `decide` left a word on none of its lists: an agent that asks puts the
    words to a chat model first (the module's docstring); it is no part of the answer, so two
    corrections of the same words are equal whatever it says."""

    words: str
    askable: bool = field(default=False, compare=False)


@dataclass(frozen=True, slots=True)
class AskAgain:
    """Unclear, or nothing heard: asked again, at most the read-back's `max_attempts` times.
    `askable`, as `Correction`'s, when `decide` left the words unplaced."""

    askable: bool = field(default=False, compare=False)


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


def _counts(heard: HeardWords | None, receipt: ReadBackReceipt, env: Environment) -> bool:
    """Whether `heard` and `receipt` pass their own checks, and the words are speech-to-text's
    (or typed, in a test)."""
    if heard is None or not is_heard_words(heard) or not is_read_back_receipt(receipt):
        return False
    return heard.source == "speech_to_text" or env == "test"


def decide(
    heard: HeardWords | None,
    receipt: ReadBackReceipt,
    *,
    words: ConsentWords,
    env: Environment,
    said: SaidLines | None = None,
) -> YesOutcome:
    """What the turn's own `heard` words (None when nothing was heard) say to the read-back
    `receipt` stands for (the module's docstring); `said`, the read-back's lines, only under
    `interruptions.yes_over_read_back` (D-108). `heard` and `receipt` must pass their own checks
    (`is_heard_words`, `is_read_back_receipt`): anything else counts for nothing. Returns the
    `ConfirmedAction` only inside a `Yes`."""
    if heard is None or not _counts(heard, receipt, env):
        return AskAgain()
    began = heard.speech_at
    if began is None or began < receipt.summary_played_at:
        return AskAgain()
    text = rule_form(heard.text)
    found = kinds(text, words)
    if not found:
        return AskAgain()
    if "content" in found:
        return Correction(words=heard.text, askable=True)
    if "no" in found:
        return AskAgain() if "yes" in found else Declined(words=heard.text)
    if any(mark in heard.text for mark in QUESTION_MARKS):
        return AskAgain()
    ended = receipt.question_ended_at
    over = ended is None or began < ended
    if "yes" in found and (not over or "send" in found):
        return Yes(confirmed=_issued(heard, receipt, speech_at=began))
    # any yes books (D-108): a bare yes over the question, khalas beside a send word; never the
    # agent's own lines heard back
    okay = said is not None and ("yes" in found or ("send" in found and holds_okay(text)))
    if okay and said is not None and not echoes(text, playing(said, over=over)):
        return Yes(confirmed=_issued(heard, receipt, speech_at=began))
    if "yes" not in found:
        # send words, alone or among fillers, may be a go-ahead the lists cannot place
        return AskAgain(askable="send" in found)
    # so may a yes among fillers over the closing question ("yes, please do")
    return AskAgain(askable="filler" in found)


def held(
    word: ModelWord,
    heard: HeardWords,
    receipt: ReadBackReceipt,
    *,
    words: ConsentWords,
    env: Environment,
    said: SaidLines,
    rails: ConsentWords | None = None,
) -> Yes | AskAgain:
    """A yes held over the read-back's summary (D-108; the module's docstring): `heard`, the
    held turn's own words, said after the summary's first audio and before its last clause
    played, yes words by the lists or the model's `word`, within the rails (`held_yes`), issued
    now `receipt` stands for that summary played whole; asked again (never sent) otherwise."""
    if not _counts(heard, receipt, env):
        return AskAgain()
    began, start = heard.speech_at, receipt.summary_began_at
    if began is None or start is None or not start < began < receipt.summary_played_at:
        return AskAgain()
    if not held_yes(word, heard.text, words, said=said, rails=rails):
        return AskAgain()
    return Yes(confirmed=_issued(heard, receipt, speech_at=began))


def _askable(outcome: YesOutcome) -> bool:
    return isinstance(outcome, Correction | AskAgain) and outcome.askable


def _stands(receipt: ReadBackReceipt, current: ReadBackReceipt | None) -> bool:
    """Whether `current`, the receipt built anew as a model's word lands, is of the same
    read-back as `receipt`, the one built when the turn's words reached the rule, both the
    session's own."""
    if not is_read_back_receipt(receipt) or current is None or not is_read_back_receipt(current):
        return False
    held = (receipt.action, receipt.draft_json, receipt.reply_id, receipt.summary_played_at)
    now = (current.action, current.draft_json, current.reply_id, current.summary_played_at)
    return held == now


def judged(
    word: ModelWord,
    heard: HeardWords | None,
    receipt: ReadBackReceipt,
    *,
    current: ReadBackReceipt | None,
    words: ConsentWords,
    env: Environment,
    said: SaidLines,
    rails: ConsentWords | None = None,
    bare: bool = False,
) -> YesOutcome:
    """What a chat model's `word` on the turn's own `heard` words makes of the read-back
    `receipt` stands for (the module's docstring): `receipt` built when the words reached the
    rule, `current` as the word lands (None when no read-back is current), `said` the read-back's
    lines as the agent said them and whether each was still heard as the speech began, `rails`
    the lists whose no words and change markers the rails read (`words` unless given; every
    language's for words heard in another: domain/yes_words.py's `rails_for`), and `bare` under
    `interruptions.yes_over_read_back` (D-108). A receipt that no longer stands is asked again;
    every other answer of `decide`'s that is not `askable` stands as it is, so a model's word
    never confirms what the lists refused; a missing word (None: the request failed or timed
    out) is declined on words that hold a no word, as a `no` is, and asked again on any other;
    and its `no` or `change`, or a missing word, on the agent's own words heard back is asked
    again, never a cancel. The only other builder of a `ConfirmedAction`, inside a `Yes`."""
    if not _stands(receipt, current):
        return AskAgain()
    listed = decide(heard, receipt, words=words, env=env, said=said if bare else None)
    if not _askable(listed) or heard is None or heard.speech_at is None:
        return listed
    text = rule_form(heard.text)
    began, ended = heard.speech_at, receipt.question_ended_at
    over = ended is None or began < ended
    echo = echoes(text, playing(said, over=over))
    found = kinds(text, words)
    refused = "no" in kinds(text, rails or words)
    if word is None:  # no word: a no word declines, unless it is the agent's echo
        return Declined(words=heard.text) if refused and not echo else AskAgain()
    if word not in ("send", "yes", "no", "change"):
        return AskAgain()
    if word in ("no", "change"):  # the agent's echo never cancels or changes a read-back
        if echo:
            return AskAgain()
        return Declined(words=heard.text) if word == "no" else Correction(words=heard.text)
    if refused or any(mark in heard.text for mark in QUESTION_MARKS):
        return AskAgain()
    if marked(text, (rails or words).change):
        return Correction(words=heard.text)
    if echo:
        return AskAgain()
    # over the question a yes needs a go-ahead: the model's `send`, or a send word beside other
    # words; a send word alone it judged agreement only is asked again, as the lists ask it,
    # and under `bare` (D-108) only that
    plain = "send" not in found and not bare
    if over and word != "send" and (plain or found == {"send"}):
        return AskAgain()
    return Yes(confirmed=_issued(heard, receipt, speech_at=began))

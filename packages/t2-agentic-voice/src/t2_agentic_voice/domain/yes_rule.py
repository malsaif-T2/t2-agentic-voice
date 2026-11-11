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

**A plain no** (`plain_no`): a no word with only send words and fillers beside it, the words
`decide` declines once the summary played. The session reads what cuts the summary with it, so
a cancel said over the summary is declined as a no, not a correction (D-081).

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
tell.
Speech begun when none of them was heard cannot be the agent's echo, so a caller who answers
arsilha once the question and its tail ended can send. Only the rail's window has the tail: a
yes over the closing question is still one whose speech began before the question ended
(`question_ended_at`, the receipt's).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
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
from t2_agentic_voice.domain.consent_check import ConsentAnswer
from t2_agentic_voice.domain.interruption_words import QUESTION_MARKS
from t2_agentic_voice.domain.interruptions import own_words
from t2_agentic_voice.domain.words import rule_form
from t2_agentic_voice.domain.yes_words import ConsentWords

# What one word of the heard words is to the rule: on a list, or on none (`content`).
_Kind = Literal["no", "yes", "send", "filler", "content"]
_AND = "\u0648"  # waw, and

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
# A chat model's word on the words (domain/consent_check.py's), or None for no word: the request
# failed or timed out.
type ModelWord = ConsentAnswer | None


@dataclass(frozen=True, slots=True, kw_only=True)
class SaidLines:
    """What the agent said of one read-back, each line written and spoken, as `judged`'s echo
    rail reads them (the module's docstring): `read_back`, its summary and closing question;
    `asked_again`, the line that asks it again; and whether the caller's speech began while
    each was still heard, its reply playing or within its tail after it ended
    (`over_read_back`, `over_asked_again`), which the session tells, each True when it cannot
    tell, so the rail keeps that line."""

    read_back: tuple[str, ...]
    asked_again: tuple[str, ...]
    over_read_back: bool = True
    over_asked_again: bool = True


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


def plain_no(text: str, words: ConsentWords) -> bool:
    """Whether `text`, brought to the rule's form, is a plain no to the lists `words`: a no
    word, and beside it only send words and fillers ("no, cancel it, don't send it"), with no
    yes word and no word on none of the lists; the words `decide` declines once the summary
    played. The session reads what cuts a read-back's summary with it (voice/session/
    read_back.py's `handed`), so a cancel said over it is a no, not a correction."""
    kinds = _kinds(rule_form(text), words)
    return "no" in kinds and not kinds & {"yes", "content"}


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
        return Correction(words=heard.text, askable=True)
    if "no" in kinds:
        return AskAgain() if "yes" in kinds else Declined(words=heard.text)
    asked = any(mark in heard.text for mark in QUESTION_MARKS)
    if "yes" not in kinds or asked:
        # send words, alone or among fillers, may be a go-ahead the lists cannot place
        return AskAgain(askable=not asked and "send" in kinds)
    ended = receipt.question_ended_at
    if (ended is None or began < ended) and "send" not in kinds:
        # so may a yes among fillers over the closing question ("yes, please do")
        return AskAgain(askable="filler" in kinds)
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


def _marked(text: str, markers: tuple[str, ...]) -> bool:
    """Whether `text`, in the rule's form, holds a change marker as whole words, or one after
    waw (and) written onto it."""
    padded = f" {text} "
    if any(f" {marker} " in padded for marker in markers):
        return True
    return any(word.startswith(_AND) and word[1:] in markers for word in text.split())


def _echoes(text: str, playing: Sequence[str]) -> bool:
    """Whether `text`, in the rule's form, is the agent's own words, its lines `playing` as the
    speech began read together as the interruption rule reads the clauses that played
    (domain/interruptions.py's `own_words`): every word a word of them, or one edit from one of
    three letters or more. Its read-back heard back, across two lines or a letter off, never
    the caller's answer."""
    heard = text.split()
    return bool(heard) and own_words(heard, [rule_form(line) for line in playing])


def _playing(said: SaidLines, *, over: bool) -> tuple[str, ...]:
    """The lines of `said` still heard by the caller as the speech began: the read-back's over
    the closing question (`over`) or as the session tells it, its tail included; the ask-again
    line's as the session tells it; none else, so words begun while none was heard are never
    the agent's echo."""
    reading = over or said.over_read_back
    asking = said.over_asked_again
    return (*(said.read_back if reading else ()), *(said.asked_again if asking else ()))


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
) -> YesOutcome:
    """What a chat model's `word` on the turn's own `heard` words makes of the read-back
    `receipt` stands for (the module's docstring): `receipt` built when the words reached the
    rule, `current` as the word lands (None when no read-back is current), `said` the read-back's
    lines as the agent said them and whether each was still heard as the speech began, `rails`
    the lists whose no words and change markers the rails read (`words` unless given; every
    language's for words heard in another: domain/yes_words.py's `rails_for`). A
    receipt that no longer stands is asked again; every other answer of `decide`'s that is not
    `askable` stands as it is, so a model's word never confirms what the lists refused; a
    missing word (None: the request failed or timed out) is declined on words that hold a no
    word, as a `no` is, and asked again on any other; and its `no` or `change`, or a missing
    word, on the agent's own words heard back is asked again, never a cancel. The only other
    builder of a `ConfirmedAction`, inside a `Yes`."""
    if not _stands(receipt, current):
        return AskAgain()
    listed = decide(heard, receipt, words=words, env=env)
    if not _askable(listed) or heard is None or heard.speech_at is None:
        return listed
    text = rule_form(heard.text)
    began, ended = heard.speech_at, receipt.question_ended_at
    over = ended is None or began < ended
    echo = _echoes(text, _playing(said, over=over))
    kinds = _kinds(text, words)
    refused = "no" in _kinds(text, rails or words)
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
    if _marked(text, (rails or words).change):
        return Correction(words=heard.text)
    if echo:
        return AskAgain()
    # over the question a yes needs a go-ahead: the model's `send`, or a send word beside other
    # words; a send word alone it judged agreement only is asked again, as the lists ask it
    if over and word != "send" and ("send" not in kinds or kinds == {"send"}):
        return AskAgain()
    return Yes(confirmed=_issued(heard, receipt, speech_at=began))

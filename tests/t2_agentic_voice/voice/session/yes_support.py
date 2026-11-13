"""What the tests of the caller's answer to a read-back share: the yes rule as these tests give
it, the `ActionJobs` port as they give it, and a confirming call's steps.

`FakeYesRule` stands in for the yes rule (domain/yes_rule.py's `decide`, which has tests of its
own), patched where the session calls it (yes_turns.py), through conftest.py's `yes_rule`. Unless a
test forces its answer, it reads the design's 8.3 on the words the session hands it
(read_back_support.py's `CONSENT`): speech begun before the summary ended counts for nothing; a word
of no list is a correction; a no word is a no; a yes over the closing question (its end not
reported, or the speech begun before it) needs a send word; anything else with no yes is asked
again. The action's write (`FakeJobs`) takes `seconds` on the call's clock, then gives its outcome,
or raises the `error` given.

Turn 0's reply (reply 1) reads `PLAN` back; the texts are made up, none a golden item.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from t2_agentic_voice.core.clock import Clock
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.conversation import ConversationLine
from t2_agentic_voice.core.events import CallId, TurnId
from t2_agentic_voice.core.identity import Caller
from t2_agentic_voice.core.settings.tts import LanguageTag
from t2_agentic_voice.core.yes_inputs import HeardWords, ReadBackReceipt
from t2_agentic_voice.domain.action_lines import SpokenLine
from t2_agentic_voice.domain.ports.action_jobs import ActionOutcome, OutcomeKind
from t2_agentic_voice.domain.words import rule_form
from t2_agentic_voice.domain.yes_rule import (
    AskAgain,
    ConfirmedAction,
    Correction,
    Declined,
    Yes,
    YesOutcome,
    _issued,
)
from t2_agentic_voice.domain.yes_words import ConsentWords
from t2_agentic_voice.voice.session.call import CallSession

from tests.t2_agentic_voice.session_fakes import FakeSessionIO
from tests.t2_agentic_voice.voice.session.overlap_support import two_step
from tests.t2_agentic_voice.voice.session.read_back_support import asked, read_whole, reads_back
from tests.t2_agentic_voice.voice.session.session_support import speaks
from tests.t2_agentic_voice.voice.session.talker_support import (
    FakeTalker,
    Script,
    settle,
    talker_call,
)

OUTCOME = SpokenLine(
    text="Made-up outcome line, request 4521.",
    spoken="Made-up outcome line, request four five two one.",
)
REQUEST_ID = "made-up-request-id"


@dataclass(frozen=True)
class Decided:
    """One call of the yes rule: what the session handed it."""

    heard: HeardWords
    receipt: ReadBackReceipt
    words: ConsentWords
    env: str


def _kinds(text: str, words: ConsentWords) -> list[str]:
    """Each phrase of `text`, the longest first, as the list it belongs to (`other` for none)."""
    lists = {"yes": words.yes, "send": words.send, "no": words.no, "filler": words.fillers}
    forms = {rule_form(phrase): kind for kind, phrases in lists.items() for phrase in phrases}
    heard, found, at = rule_form(text).split(), [], 0
    while at < len(heard):
        sizes = range(len(heard) - at, 0, -1)
        size = next((n for n in sizes if " ".join(heard[at : at + n]) in forms), 0)
        found.append(forms[" ".join(heard[at : at + size])] if size else "other")
        at += size or 1
    return found


def design_rule(heard: HeardWords, receipt: ReadBackReceipt, words: ConsentWords) -> YesOutcome:
    """The design's 8.3, as the module's docstring reads it."""
    began = heard.speech_at
    if began is None or began < receipt.summary_played_at:
        return AskAgain()
    kinds = _kinds(heard.text, words)
    if "other" in kinds:
        return Correction(words=heard.text)
    if "no" in kinds:
        return Declined(words=heard.text)
    if "yes" not in kinds:
        return AskAgain()
    ended = receipt.question_ended_at
    if (ended is None or began < ended) and "send" not in kinds:
        return AskAgain()
    return Yes(confirmed=_issued(heard, receipt, speech_at=began))


def yes_always(heard: HeardWords, receipt: ReadBackReceipt) -> YesOutcome:
    """A rule that says yes to any words, as the issued yes of `receipt`'s draft."""
    return Yes(confirmed=_issued(heard, receipt, speech_at=heard.speech_at or 0.0))


@dataclass
class FakeYesRule:
    """The yes rule as the tests give it (the module's docstring): `forced`, when given, answers
    in its place; each call is kept (`calls`)."""

    forced: Callable[[HeardWords, ReadBackReceipt], YesOutcome] | None = None
    calls: list[Decided] = field(default_factory=list)

    def __call__(
        self, heard: HeardWords | None, receipt: ReadBackReceipt, *, words: ConsentWords, env: str
    ) -> YesOutcome:
        assert heard is not None, "the session hands the rule words heard"
        self.calls.append(Decided(heard=heard, receipt=receipt, words=words, env=env))
        if self.forced is not None:
            return self.forced(heard, receipt)
        return design_rule(heard, receipt, words)


@dataclass(frozen=True)
class Run:
    """One write the session asked for: what it handed the port."""

    confirmed: ConfirmedAction
    caller: Caller
    call_id: CallId
    language: LanguageTag
    turn_id: TurnId
    conversation: tuple[ConversationLine, ...]
    wording: LanguageTag | None = None


@dataclass
class FakeJobs:
    """The `ActionJobs` port as the tests give it (the module's docstring): each run kept,
    `on_run` called as each begins, and how many finished or were cancelled."""

    seconds: float = 0.0
    kind: OutcomeKind = "done"
    error: Exception | None = None
    on_run: Callable[[], None] | None = None
    runs: list[Run] = field(default_factory=list)
    finished: int = 0
    cancelled: int = 0

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
        self.runs.append(Run(confirmed, caller, call_id, language, turn_id, conversation, wording))
        if self.on_run is not None:
            self.on_run()
        try:
            await clock.sleep(self.seconds)
        except asyncio.CancelledError:
            self.cancelled += 1
            raise
        self.finished += 1
        if self.error is not None:
            raise self.error
        return ActionOutcome(
            action=confirmed.action, request_id=REQUEST_ID, kind=self.kind, line=OUTCOME
        )


def confirm_call(
    settings: VoiceSettings, jobs: FakeJobs | None, script: Script = reads_back, **given: Any
) -> tuple[FakeSessionIO, CallSession, FakeTalker]:
    """A talker's call under `two_step` whose turn 0 is read back, its confirmed actions handed
    to `jobs`."""
    return talker_call(two_step(settings), script, action_jobs=jobs, **given)


async def read_back_played(io: FakeSessionIO) -> None:
    """Turn 0's read-back (reply 1) is asked for and plays whole, then a pause past its tail."""
    await asked(io)
    await read_whole(io)
    await settle()
    await io.clock.advance(1.0)


async def play_reply(io: FakeSessionIO, reply_id: int) -> None:
    """Each clause the session asked for of `reply_id` plays whole, 0.5 s each."""
    for speak in speaks(io, reply_id):
        if speak.audio is None:
            await io.synthesizing(reply_id, speak.clause)
        await io.clause_queued(reply_id, speak.clause)
        await io.clock.advance(0.5)
        await io.clause_played(reply_id, speak.clause, audio_s=0.5)
    await settle()

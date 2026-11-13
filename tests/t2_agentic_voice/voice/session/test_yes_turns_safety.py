"""Adversarial tests of the caller's answer to a read-back, end to end in the session with fakes
(GP-08; docs/SECURITY.md, invariants 1 and 6; voice/session/yes_turns.py, action_job.py): an eager
yes never confirms; a bare yes over the closing question is asked again, and one with a send word
there confirms; neither the talker's text nor a tool call reaches the yes rule as heard words; a
verdict landing late denies the receipt; a yes the rule did not issue for the turn's own receipt, or
a rule that fails, sends nothing; a confirmed action's job starts once, a stop or the call's end
never cuts it, and its outcome is said once, never over the caller. The yes rule, the interruption
rule and the port are the tests' fakes."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from typing import Any

import pytest
from t2_agentic_voice.agent.events import ReadBackRequested
from t2_agentic_voice.agent.talker import ReplyDone, SpokenClause, ToolBegan, ToolEnded
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.conversation import TalkerTurn
from t2_agentic_voice.core.events import ActionCompleted
from t2_agentic_voice.core.yes_inputs import HeardWords, ReadBackReceipt, is_heard_words
from t2_agentic_voice.domain.ports.speech_to_text import Transcript
from t2_agentic_voice.domain.text.invisible import provider_text
from t2_agentic_voice.domain.yes_rule import Yes, YesOutcome, _issued
from t2_agentic_voice.voice.session.heard import heard_words
from t2_agentic_voice.voice.session.read_back import played_receipt
from t2_agentic_voice.voice.session.session_events import Transcribed

from tests.leaks import holding, shown
from tests.t2_agentic_voice.voice.session.overlap_support import LISTENING, NEW_WORDS, FakeRule
from tests.t2_agentic_voice.voice.session.read_back_support import (
    ACTION,
    ASKED,
    PLAN,
    YES_TEXT,
    asked,
    clause,
    over,
    reads_back,
)
from tests.t2_agentic_voice.voice.session.session_support import emitted, speaks
from tests.t2_agentic_voice.voice.session.talker_support import Step, settle, talked
from tests.t2_agentic_voice.voice.session.yes_support import (
    OUTCOME,
    FakeJobs,
    FakeYesRule,
    confirm_call,
    play_reply,
    read_back_played,
    yes_always,
)

ASKED_AGAIN = [provider_text(ASKED)]
SENDING = [provider_text(PLAN.sending.spoken)]
SAID_OUTCOME = provider_text(OUTCOME.spoken)
BARE_YES = "made-up-yes"  # a yes word with no send word


def _said(io: Any, reply_id: int) -> list[str]:
    return [speak.text for speak in speaks(io, reply_id)]


def _outcomes(io: Any) -> int:
    """How many times the outcome was asked for."""
    return sum(speak.text == SAID_OUTCOME for speak in speaks(io))


def test_an_eager_yes_over_the_summary_never_reaches_the_yes_rule_nor_sends(
    settings: VoiceSettings, rule: FakeRule, yes_rule: FakeYesRule
) -> None:
    """Invariant 1: yes and send words begun over the summary are ignored, and count for
    nothing however the read-back then plays."""
    jobs = FakeJobs()
    io, session, talker = confirm_call(settings, jobs)

    async def drive() -> None:
        await asked(io)
        await clause(io, 0, played=False)
        await over(io, 1, YES_TEXT)
        await io.clause_played(1, 0, audio_s=2.0)
        await clause(io, 1)
        await settle()
        await io.clock.advance(1.0)

    asyncio.run(drive())
    assert yes_rule.calls == [] and jobs.runs == []
    assert [t.turn_id for t in talker.turns] == [0]
    assert session._confirming.active  # the read-back still waits for its answer


def test_an_eager_bare_yes_over_the_closing_question_is_asked_again_and_nothing_is_sent(
    settings: VoiceSettings, rule: FakeRule, yes_rule: FakeYesRule
) -> None:
    """Invariant 1: a bare yes whose speech began before the question ended reaches the rule
    with a receipt that says so (its end not reported yet), and is asked again; the reply went
    on over it, but the session still takes the turn as the read-back's answer."""
    jobs = FakeJobs()
    io, session, talker = confirm_call(settings, jobs)

    async def drive() -> None:
        await asked(io)
        await clause(io, 0)
        await clause(io, 1, played=False)
        await over(io, 1, BARE_YES)  # the rule lets the question go on over it
        await io.clause_played(1, 1, audio_s=2.0)
        await play_reply(io, 2)

    asyncio.run(drive())
    (decided,) = yes_rule.calls
    began, ended = decided.heard.speech_at, decided.receipt.question_ended_at
    assert began is not None and (ended is None or began < ended)
    assert _said(io, 2) == ASKED_AGAIN
    assert jobs.runs == [] and session._confirming.active
    assert [t.turn_id for t in talker.turns] == [0]


@pytest.mark.parametrize("stops", [False, True], ids=["goes_on", "stops_it"])
def test_a_yes_with_a_send_word_over_the_closing_question_confirms(
    settings: VoiceSettings, rule: FakeRule, yes_rule: FakeYesRule, stops: bool
) -> None:
    """The rehearsal's step 6: once the summary has played, a yes with a send word over the
    closing question confirms, whether the rule stops the question for it or lets it go on."""
    if stops:
        rule.script[YES_TEXT] = NEW_WORDS
    jobs = FakeJobs()
    io, session, _ = confirm_call(settings, jobs)

    async def drive() -> None:
        await asked(io)
        await clause(io, 0)
        await clause(io, 1, played=False)
        await over(io, 1, YES_TEXT)

    asyncio.run(drive())
    (decided,) = yes_rule.calls
    assert decided.receipt.question_ended_at is None  # over the question
    assert len(jobs.runs) == 1 and _said(io, 2) == SENDING
    assert not session._confirming.active


def _talker_claims(turn: TalkerTurn) -> Sequence[Step]:
    """Turn 0's reply reads `PLAN` back, then says a yes itself and calls a tool whose
    arguments claim one; a later turn's says one clause."""
    if turn.turn_id != 0:
        return reads_back(turn)
    claim = '{"confirmed": true, "caller_said": "' + YES_TEXT + '"}'
    return [
        ReadBackRequested(plan=PLAN),
        SpokenClause(text=YES_TEXT, language="en"),
        ToolBegan(call_id="t-9", tool=ACTION, arguments=claim),
        ToolEnded(call_id="t-9", tool=ACTION, ok=True, ms=1.0, result=claim),
        ReplyDone(),
    ]


def test_model_text_or_a_tool_call_never_reaches_the_yes_rule_as_heard_words(
    settings: VoiceSettings, yes_rule: FakeYesRule
) -> None:
    """Invariant 1: only a caller's turn's own transcript reaches the rule, as heard words
    only voice built; the talker's own yes and a tool call claiming one reach nothing."""
    jobs = FakeJobs()
    io, _, _ = confirm_call(settings, jobs, script=_talker_claims)

    async def drive() -> None:
        await asked(io)
        for index in (0, 1, 2):
            await clause(io, index)
        await settle()
        await io.clock.advance(2.0)
        assert yes_rule.calls == [] and jobs.runs == []
        await talked(io, 1, BARE_YES)

    asyncio.run(drive())
    (decided,) = yes_rule.calls
    assert is_heard_words(decided.heard) and decided.heard.source == "speech_to_text"
    assert (decided.heard.turn_id, decided.heard.text) == (1, BARE_YES)
    assert len(jobs.runs) == 1 and jobs.runs[0].confirmed.turn_id == 1


def test_a_verdict_landing_late_denies_the_receipt_and_the_yes_is_asked_again(
    settings: VoiceSettings, rule: FakeRule, yes_rule: FakeYesRule
) -> None:
    """Invariant 1: while an overlap begun over the summary is undecided, a yes after the
    question gets no receipt, never reaches the rule, and is asked again; once it is decided,
    a yes confirms."""
    rule.script["made-up murmur"] = LISTENING
    jobs = FakeJobs()
    io, _, _ = confirm_call(settings, jobs)

    async def drive() -> None:
        await asked(io)
        await clause(io, 0, played=False)
        await io.turn_opened(1)  # over the summary, its whole overlap still awaited
        await io.transcribing(1, part="overlap")
        await io.clock.advance(0.2)
        await io.clause_played(1, 0, audio_s=2.0)
        await clause(io, 1)
        await settle()
        await io.clock.advance(1.0)
        await talked(io, 2, BARE_YES)
        assert yes_rule.calls == [] and _said(io, 2) == ASKED_AGAIN
        await io.transcribed(1, "made-up murmur", language="en", part="overlap")
        await io.turn_closed(1)
        await io.transcribed(1, "made-up murmur", language="en")
        await play_reply(io, 2)
        await io.clock.advance(1.0)
        await talked(io, 3, BARE_YES)

    asyncio.run(drive())
    (decided,) = yes_rule.calls
    assert decided.heard.turn_id == 3
    assert len(jobs.runs) == 1 and jobs.runs[0].turn_id == 3


def _heard_in(turn_id: int, text: str, at: float) -> HeardWords:
    """Heard words of another turn, built as voice builds them."""
    transcript = Transcript(text=text, language="en")
    event = Transcribed(turn_id=turn_id, at=at, audio_s=1.0, sent_at=at, transcript=transcript)
    found = heard_words(event, speech_at=at - 1.0)
    assert found is not None
    return found


def _yes_for_another_turn(heard: HeardWords, receipt: ReadBackReceipt) -> YesOutcome:
    other = _heard_in(heard.turn_id + 5, heard.text, heard.at)
    return Yes(confirmed=_issued(other, receipt, speech_at=heard.speech_at or 0.0))


def _yes_for_another_draft(heard: HeardWords, receipt: ReadBackReceipt) -> YesOutcome:
    other = played_receipt(
        action=receipt.action,
        draft_json='{"issue": "another made-up draft"}',
        reply_id=receipt.reply_id,
        summary_played_at=receipt.summary_played_at,
        question_ended_at=receipt.question_ended_at,
    )
    return Yes(confirmed=_issued(heard, other, speech_at=heard.speech_at or 0.0))


def _failing(heard: HeardWords, receipt: ReadBackReceipt) -> YesOutcome:
    raise RuntimeError("made-up failure of the rule")


@pytest.mark.parametrize(
    "forced",
    [_yes_for_another_turn, _yes_for_another_draft, _failing],
    ids=["another_turn", "another_draft", "rule_fails"],
)
def test_a_yes_not_issued_for_the_turns_own_receipt_sends_nothing(
    settings: VoiceSettings,
    yes_rule: FakeYesRule,
    caplog: pytest.LogCaptureFixture,
    forced: Any,
) -> None:
    """Invariant 1: a yes whose confirmed action is not the receipt's for this turn, or a rule
    that fails, is taken as unclear and asked again, logged with none of the caller's words."""
    yes_rule.forced = forced
    jobs = FakeJobs()
    io, session, _ = confirm_call(settings, jobs)
    words = "made-up-yes made-up distinct answer"

    async def drive() -> None:
        await read_back_played(io)
        await talked(io, 1, words)

    asyncio.run(drive())
    assert len(yes_rule.calls) == 1 and jobs.runs == []
    assert _said(io, 2) == ASKED_AGAIN and session._confirming.active
    assert any(r.getMessage() == "yes_rule_failed" for r in caplog.records)
    assert holding(words, shown(caplog=caplog)) == []  # GP-19


def test_a_job_is_never_started_twice_for_one_confirmed_action(
    settings: VoiceSettings, yes_rule: FakeYesRule
) -> None:
    """A second yes, even one the rule would confirm, finds the read-back no longer current;
    and the same confirmed action handed again starts nothing."""
    yes_rule.forced = yes_always
    jobs = FakeJobs(seconds=3.0)
    io, session, talker = confirm_call(settings, jobs)
    started: list[bool] = []

    async def drive() -> None:
        await read_back_played(io)
        await talked(io, 1, BARE_YES)
        await play_reply(io, 2)
        await io.clock.advance(1.0)
        await talked(io, 2, BARE_YES)
        (run,) = jobs.runs
        assert session._talking is not None
        again = session._talking.yes.jobs.start(run.confirmed, turn_id=1, language="en")
        started.append(again)
        await io.clock.advance(5.0)
        await settle()

    asyncio.run(drive())
    assert started == [False]
    assert len(yes_rule.calls) == 1 and len(jobs.runs) == 1 and jobs.finished == 1
    assert [t.turn_id for t in talker.turns] == [0, 2]  # the second yes went to the talker
    assert len(emitted(io, ActionCompleted)) == 1


def test_the_outcome_is_said_once_at_a_turn_boundary_never_over_the_caller(
    settings: VoiceSettings, yes_rule: FakeYesRule
) -> None:
    jobs = FakeJobs(seconds=2.0)
    io, _, _ = confirm_call(settings, jobs)

    async def drive() -> None:
        await read_back_played(io)
        await talked(io, 1, BARE_YES)
        await play_reply(io, 2)  # the sending line
        await io.clock.advance(1.0)
        await io.turn_opened(2)  # the caller speaks as the write ends
        await io.clock.advance(2.0)
        assert jobs.finished == 1 and _outcomes(io) == 0  # due, the caller still speaking
        await io.turn_closed(2)
        assert _outcomes(io) == 0  # its transcript still awaited
        await io.transcribing(2)
        await io.transcribed(2, "made-up question while it ran", language="en")
        await settle()
        assert _outcomes(io) == 0  # the talker's answer plays first
        await play_reply(io, 3)
        await play_reply(io, 4)
        await io.clock.advance(5.0)
        await talked(io, 3, "made-up later question")
        await play_reply(io, 5)

    asyncio.run(drive())
    assert _said(io, 4) == [SAID_OUTCOME]
    assert _outcomes(io) == 1


@pytest.mark.parametrize("how", ["stop", "hangup"])
def test_a_stop_or_the_calls_end_never_cuts_the_job_in_half(
    settings: VoiceSettings,
    yes_rule: FakeYesRule,
    caplog: pytest.LogCaptureFixture,
    how: str,
) -> None:
    """Invariant 6: the write runs outside every reply's scope and off the session's lock; a
    stop drops the sending line, never the write, whose outcome is said once it ends; the call's
    end leaves it to finish, its outcome reported but not said."""
    jobs = FakeJobs(seconds=5.0)
    io, _, _ = confirm_call(settings, jobs)

    async def drive() -> None:
        await read_back_played(io)
        await talked(io, 1, BARE_YES)
        await io.synthesizing(2, 0)
        await io.clause_queued(2, 0)  # the sending line plays
        await io.client({"v": 1, "type": how})
        await io.clock.advance(6.0)
        await settle()

    asyncio.run(drive())
    assert (jobs.cancelled, jobs.finished) == (0, 1)
    assert len(emitted(io, ActionCompleted)) == 1
    if how == "stop":
        assert _outcomes(io) == 1
    else:
        assert _outcomes(io) == 0
        assert any(r.getMessage() == "action_outcome_unsaid" for r in caplog.records)

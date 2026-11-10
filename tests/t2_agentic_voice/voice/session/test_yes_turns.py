"""The caller's answer to an action's read-back (voice/session/yes_turns.py, action_job.py; plan
007, Track C, and the owner's rulings of 2026-11-10): while the call is confirming, a turn whose
speech began once the summary played goes to the yes rule with its own heard words and the
receipt built then; a yes says the sending line, then hands the confirmed action to the call's
`ActionJobs`, its outcome said once the sending line has played, and nothing else claims it; a
plain no and a correction reach the talker with the action declined as that kind, and it
answers in its own words; an unclear answer is asked again at most `max_attempts` times, then
the declined line ends it; with no `ActionJobs` a yes is told as the `error` notice and nothing
is sent; a stop or pause request said whole while confirming declines it, the talker asking what
to change; a turn that answers the read-back starts no talker early; and the turn book, the
history and the next talker turn hold the read-back, the sending line and the outcome as they
hold any reply. The yes rule and the port are the tests' fakes (yes_support.py)."""

from __future__ import annotations

import asyncio

import pytest
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.conversation import DeclinedAction, DeclineKind
from t2_agentic_voice.core.events import (
    ActionCompleted,
    ConfirmationAnswered,
    ConfirmationRequested,
)
from t2_agentic_voice.core.yes_inputs import is_heard_words, is_read_back_receipt
from t2_agentic_voice.domain.text.invisible import provider_text
from t2_agentic_voice.domain.words import PRESET_WORDS
from t2_agentic_voice.domain.yes_rule import AskAgain, is_confirmed
from t2_agentic_voice.voice.protocol import Notice

from tests.leaks import holding, shown
from tests.t2_agentic_voice.session_fakes import FakeSessionIO
from tests.t2_agentic_voice.voice.session.read_back_support import (
    ACTION,
    ASKED,
    CALLER_WORDS,
    CONSENT,
    DRAFT,
    PLAN,
    QUESTION,
    REQUEST,
    SUMMARY,
)
from tests.t2_agentic_voice.voice.session.session_support import emitted, sent, speaks
from tests.t2_agentic_voice.voice.session.talker_support import settle, talked
from tests.t2_agentic_voice.voice.session.yes_support import (
    OUTCOME,
    REQUEST_ID,
    FakeJobs,
    FakeYesRule,
    confirm_call,
    play_reply,
    read_back_played,
)

SENDING = [provider_text(PLAN.sending.spoken)]
SAID_OUTCOME = [provider_text(OUTCOME.spoken)]
YES = "made-up-yes"  # a yes word alone, after the closing question
STOP_WORD = PRESET_WORDS["en"].stop[0]


def _said(io: FakeSessionIO, reply_id: int) -> list[str]:
    return [speak.text for speak in speaks(io, reply_id)]


def test_a_yes_says_the_sending_line_then_hands_the_job_on_and_says_its_outcome_once(
    settings: VoiceSettings, yes_rule: FakeYesRule, caplog: pytest.LogCaptureFixture
) -> None:
    jobs = FakeJobs()
    io, session, talker = confirm_call(settings, jobs)
    asked_first: list[list[str]] = []
    jobs.on_run = lambda: asked_first.append(_said(io, 2))

    async def drive() -> None:
        await read_back_played(io)
        await talked(io, 1, YES)
        assert _said(io, 3) == []  # the outcome waits for the sending line
        await play_reply(io, 2)
        await play_reply(io, 3)
        await io.clock.advance(5.0)
        await settle()

    asyncio.run(drive())
    (decided,) = yes_rule.calls
    heard, receipt = decided.heard, decided.receipt
    assert is_heard_words(heard) and (heard.turn_id, heard.text) == (1, YES)
    assert heard.source == "speech_to_text"
    assert is_read_back_receipt(receipt)
    assert (receipt.action, receipt.draft_json, receipt.reply_id) == (ACTION, DRAFT, 1)
    ended = receipt.question_ended_at
    assert ended is not None and heard.speech_at is not None and heard.speech_at > ended
    assert decided.words == CONSENT and decided.env == settings.env
    assert _said(io, 2) == SENDING and asked_first == [SENDING]  # said before the job began
    (run,) = jobs.runs
    assert is_confirmed(run.confirmed) and (run.confirmed.draft_json, run.turn_id) == (DRAFT, 1)
    assert (run.call_id, run.caller, run.language) == (io.setup.call_id, io.setup.caller, "en")
    assert [(line.speaker, line.text) for line in run.conversation][1:] == [
        ("caller", REQUEST),
        ("agent", f"{SUMMARY} {QUESTION}"),
        ("caller", YES),
    ]
    assert _said(io, 3) == SAID_OUTCOME and speaks(io, 4) == []  # once
    outcome = session.playback.reply(3)
    assert outcome is not None and outcome.turn_id is None  # it answers no turn
    assert [t.turn_id for t in talker.turns] == [0]  # the talker never heard the yes
    assert not session._confirming.active
    assert [(e.turn_id, e.action) for e in emitted(io, ConfirmationRequested)] == [(0, ACTION)]
    answered = emitted(io, ConfirmationAnswered)
    assert [(e.turn_id, e.decision) for e in answered] == [(1, "yes")]
    (completed,) = emitted(io, ActionCompleted)
    assert (completed.turn_id, completed.action, completed.request_id) == (1, ACTION, REQUEST_ID)
    logged = shown(caplog=caplog)
    for value in (DRAFT, OUTCOME.text, SUMMARY):  # GP-19
        assert holding(value, logged) == []


@pytest.mark.parametrize(
    ("text", "kind"), [("no", "no"), (CALLER_WORDS, "correction")], ids=["no", "correction"]
)
def test_a_no_or_a_correction_reaches_the_talker_declined_and_nothing_is_sent(
    settings: VoiceSettings, yes_rule: FakeYesRule, text: str, kind: DeclineKind
) -> None:
    """The owner's ruling: after a plain no the talker answers in its own words, and after a
    correction too; the action's declined line is not said."""
    jobs = FakeJobs()
    io, session, talker = confirm_call(settings, jobs)

    async def drive() -> None:
        await read_back_played(io)
        await talked(io, 1, text)

    asyncio.run(drive())
    assert len(yes_rule.calls) == 1
    handed = talker.turns[1]
    assert handed.words == text
    assert handed.declined == DeclinedAction(action=ACTION, kind=kind, words=text)
    assert _said(io, 2) == ["Made-up answer."]  # the talker's own words
    assert jobs.runs == [] and not session._confirming.active
    declined = provider_text(PLAN.declined.spoken)
    assert all(speak.text != declined for speak in speaks(io))


def test_an_unclear_answer_is_asked_again_at_most_max_attempts_times_then_declined(
    settings: VoiceSettings, yes_rule: FakeYesRule
) -> None:
    yes_rule.forced = lambda heard, receipt: AskAgain()
    jobs = FakeJobs()
    io, session, talker = confirm_call(settings, jobs)

    async def drive() -> None:
        await read_back_played(io)
        for turn_id in (1, 2, 3):
            await talked(io, turn_id, f"made-up mumble {turn_id}")
            await play_reply(io, turn_id + 1)
            await io.clock.advance(1.0)

    asyncio.run(drive())
    assert PLAN.max_attempts == 2
    asked = [provider_text(ASKED)]
    assert [_said(io, reply_id) for reply_id in (2, 3, 4)] == [
        asked,
        asked,
        [provider_text(PLAN.declined.spoken)],
    ]
    assert [t.turn_id for t in talker.turns] == [0]
    assert jobs.runs == [] and not session._confirming.active
    answered = [e.decision for e in emitted(io, ConfirmationAnswered)]
    assert answered == ["asked_again"] * 3


def test_with_no_action_jobs_a_yes_is_told_as_the_error_notice_and_nothing_is_sent(
    settings: VoiceSettings, yes_rule: FakeYesRule
) -> None:
    io, session, talker = confirm_call(settings, None)

    async def drive() -> None:
        await read_back_played(io)
        await talked(io, 1, YES)

    asyncio.run(drive())
    assert len(yes_rule.calls) == 1
    assert [notice.kind for notice in sent(io, Notice)] == ["error"]
    assert all(speak.text not in SENDING for speak in speaks(io))
    assert [t.turn_id for t in talker.turns] == [0] and not session._confirming.active


def test_a_stop_request_said_whole_while_confirming_declines_it_and_the_talker_asks(
    settings: VoiceSettings, yes_rule: FakeYesRule
) -> None:
    """The owner's stop ruling, for a stop word said once the read-back has played: no receipt,
    confirming ends, nothing is sent, and the talker hears it with the action declined."""
    jobs = FakeJobs()
    io, session, talker = confirm_call(settings, jobs)

    async def drive() -> None:
        await read_back_played(io)
        await talked(io, 1, STOP_WORD)

    asyncio.run(drive())
    assert yes_rule.calls == []
    handed = talker.turns[1]
    assert handed.declined == DeclinedAction(action=ACTION, kind="stopped", words=STOP_WORD)
    assert jobs.runs == [] and not session._confirming.active


def test_a_turn_that_answers_the_read_back_starts_no_talker_in_its_hold(
    settings: VoiceSettings, yes_rule: FakeYesRule
) -> None:
    jobs = FakeJobs()
    io, _, talker = confirm_call(settings, jobs)

    async def drive() -> None:
        await read_back_played(io)
        await io.turn_opened(1)
        await io.clock.advance(1.0)
        await io.turn_held(1)
        await io.transcribing(1, part="held")
        await io.transcribed(1, YES, language="en", part="held")
        await settle()
        assert [t.turn_id for t in talker.turns] == [0]  # no early start
        await io.turn_closed(1)
        await io.transcribed(1, YES, language="en")  # the held result, reused
        await settle()

    asyncio.run(drive())
    assert [t.turn_id for t in talker.turns] == [0]
    assert len(yes_rule.calls) == 1 and len(jobs.runs) == 1
    assert _said(io, 2) == SENDING


def test_the_turn_book_and_the_history_hold_the_read_back_and_its_outcome(
    settings: VoiceSettings, yes_rule: FakeYesRule
) -> None:
    jobs = FakeJobs()
    io, session, talker = confirm_call(settings, jobs)

    async def drive() -> None:
        await read_back_played(io)
        await talked(io, 1, YES)
        await play_reply(io, 2)
        await play_reply(io, 3)
        await io.clock.advance(1.0)
        await talked(io, 2, "made-up question afterwards")

    asyncio.run(drive())
    yes_turn = session._turns.turn(1)
    assert (yes_turn.fate, yes_turn.reply_id) == ("answered", 2)
    assert yes_turn.said == PLAN.sending.text
    replies = {reply.reply_id: reply for reply in session.history.replies()}
    assert replies[1].text == f"{SUMMARY} {QUESTION}"
    assert (replies[2].turn_id, replies[2].text) == (1, PLAN.sending.text)
    assert (replies[3].turn_id, replies[3].text) == (None, OUTCOME.text)
    handed = talker.turns[-1]
    assert handed.turn_id == 2 and handed.declined is None
    said = {reply.reply_id: reply for reply in handed.conversation.replies}
    assert [clause.text for clause in said[3].clauses] == [OUTCOME.text]
    assert [clause.fate for clause in said[2].clauses] == ["played"]

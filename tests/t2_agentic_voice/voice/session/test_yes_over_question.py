"""A bare yes over a reply's closing question under `interruptions.answer_yes_over_question`
(D-116, the owner's ruling of 2026-11-17, "Any yes books"; voice/session/yes_over_question.py,
interrupter.py): a yes said in English or Saudi Arabic over the question that ends a talker's
reply, which the reply goes on over, is held and handed to the talker as the caller's next turn
once the reply ends and its tail and the speech detector's lag have passed, never before, and
the reply is never stopped; so is one begun in the 0.3 s tail after it. With the setting off
none is answered (characterization). Its `UserTurnEnded` says what of the reply had played
before it began, and each held yes logs what became of it, never a word. What is never answered
is test_yes_over_question_never.py's, what lets a held yes go test_yes_over_question_dropped.py's.
The interruption rule is the tests' fake (overlap_support.py); every text is made up."""

from __future__ import annotations

import asyncio
import logging

import pytest
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.events import AgentSpeechEnded, Interrupted, UserTurnEnded
from t2_agentic_voice.core.settings.tts import LanguageTag
from t2_agentic_voice.voice.session.commands import StopSpeaking

from tests.t2_agentic_voice.voice.session.overlap_support import FakeRule
from tests.t2_agentic_voice.voice.session.session_support import emitted
from tests.t2_agentic_voice.voice.session.yes_question_support import (
    QUESTION,
    REQUEST,
    SAUDI_QUESTION,
    SAUDI_SUMMARY,
    SAUDI_YES,
    SUMMARY,
    call,
    fate,
    handed,
    question_ends,
    said,
    summary_played,
    waited,
)


@pytest.mark.parametrize(
    ("yes", "summary", "question", "language", "heard_in"),
    [
        ("yes", SUMMARY, QUESTION, "en", "en"),
        ("Yes please.", SUMMARY, QUESTION, "en", "en"),
        ("Yes, go ahead.", SUMMARY, QUESTION, "en", "en"),
        ("go ahead", SUMMARY, QUESTION, "en", "en"),
        (SAUDI_YES, SAUDI_SUMMARY, SAUDI_QUESTION, "ar-SA", "ar"),
    ],
    ids=["en", "en-filler", "en-send", "en-send-alone", "ar-SA"],
)
def test_a_bare_yes_over_the_closing_question_is_answered_once_the_reply_ends(
    settings: VoiceSettings,
    rule: FakeRule,
    yes: str,
    summary: str,
    question: str,
    language: LanguageTag,
    heard_in: str,
) -> None:
    io, session, talker = call(settings, summary=summary, question=question, language=language)
    before: list[list[tuple[int, str]]] = []

    async def drive() -> None:
        await summary_played(io)
        await said(io, 1, yes, language=heard_in)
        before.append(handed(talker))
        await io.clock.advance(0.3)
        await question_ends(io)
        before.append(handed(talker))
        await waited(io)

    asyncio.run(drive())
    # held while the question still plays, and until its tail and the detector's lag passed
    assert before == [[(0, REQUEST)], [(0, REQUEST)]]
    assert handed(talker) == [(0, REQUEST), (1, yes)]
    assert talker.turns[1].over_reply == 1 and talker.turns[1].cut_reply is None
    assert io.commands.of(StopSpeaking) == []  # the reply was never stopped
    assert [(e.turn_id, e.kind) for e in emitted(io, Interrupted)] == [(0, "false")]
    order = [type(e) for e in io.emitted if isinstance(e, UserTurnEnded | AgentSpeechEnded)]
    assert order[-2:] == [UserTurnEnded, AgentSpeechEnded]  # its words came first
    assert fate(session, 1) == "pending"  # answered: its reply asked for
    (heard,) = [e for e in emitted(io, UserTurnEnded) if e.turn_id == 1]
    assert heard.reply_played == summary  # what had played before it began


def test_a_yes_begun_in_the_tail_after_the_reply_ended_is_answered(
    settings: VoiceSettings, rule: FakeRule
) -> None:
    io, _session, talker = call(settings)

    async def drive() -> None:
        await summary_played(io)
        await question_ends(io)
        await io.clock.advance(0.2)  # within the 0.3 s after it ended
        await said(io, 1, "yes")
        await waited(io)

    asyncio.run(drive())
    assert handed(talker) == [(0, REQUEST), (1, "yes")]
    (heard,) = [e for e in emitted(io, UserTurnEnded) if e.turn_id == 1]
    assert heard.reply_played == f"{SUMMARY} {QUESTION}"


def test_each_held_yes_logs_what_became_of_it_and_never_a_word(
    settings: VoiceSettings, rule: FakeRule, caplog: pytest.LogCaptureFixture
) -> None:
    io, _session, _talker = call(settings)
    caplog.set_level(logging.INFO)

    async def drive() -> None:
        await summary_played(io)
        await said(io, 1, "yes")
        await said(io, 2, "yeah")
        await question_ends(io)
        await waited(io)

    asyncio.run(drive())
    lines = [
        (r.getMessage(), vars(r)["fields"])
        for r in caplog.records
        if r.getMessage().startswith("question_yes_")
    ]
    call_id = io.setup.call_id
    assert lines == [
        ("question_yes_held", {"call_id": call_id, "turn_id": 1}),
        ("question_yes_held", {"call_id": call_id, "turn_id": 2}),
        ("question_yes_answered", {"call_id": call_id, "turn_id": 1}),
        ("question_yes_let_go", {"call_id": call_id, "turn_id": 2, "why": "second"}),
    ]


@pytest.mark.parametrize("on", [False, True], ids=["off", "on"])
def test_with_the_setting_off_a_yes_over_the_question_is_not_answered(
    settings: VoiceSettings, rule: FakeRule, on: bool
) -> None:
    io, session, talker = call(settings, on=on)

    async def drive() -> None:
        await summary_played(io)
        await said(io, 1, "yes")
        await question_ends(io)
        await io.clock.advance(1.0)

    asyncio.run(drive())
    if on:
        assert handed(talker) == [(0, REQUEST), (1, "yes")]
        return
    assert handed(talker) == [(0, REQUEST)]  # as before: settled as a go-on overlap
    assert fate(session, 1) == "went_on"
    assert [(e.turn_id, e.kind) for e in emitted(io, Interrupted)] == [(0, "false")]

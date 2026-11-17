"""What a bare yes over a reply's closing question never is, under
`interruptions.answer_yes_over_question` (D-116; voice/session/yes_over_question.py; adversarial,
GP-08): answered when said over an earlier clause, when it is fillers alone, a question or a no,
over a reply the client stopped, a second yes over the same question, the agent's own words
heard back (the rule's verdict, or a send word the question holds itself), or over a reply whose
last clause is no question; and an action's read-back keeps its own rule, the same with the
setting on or off. The interruption rule is the tests' fake (overlap_support.py); every text is
made up."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.events import UserTurnEnded
from t2_agentic_voice.voice.protocol import Stop

from tests.t2_agentic_voice.voice.session.held_yes_support import answered
from tests.t2_agentic_voice.voice.session.held_yes_support import call as read_back_call
from tests.t2_agentic_voice.voice.session.overlap_support import OWN_WORDS, FakeRule, two_step
from tests.t2_agentic_voice.voice.session.read_back_support import asked as read_back_asked
from tests.t2_agentic_voice.voice.session.read_back_support import clause as read_back_clause
from tests.t2_agentic_voice.voice.session.read_back_support import over as read_back_over
from tests.t2_agentic_voice.voice.session.session_support import emitted, greeted
from tests.t2_agentic_voice.voice.session.talker_support import settle, talked
from tests.t2_agentic_voice.voice.session.yes_question_support import (
    REQUEST,
    call,
    fate,
    handed,
    question_ends,
    said,
    summary_played,
    waited,
)


def test_a_yes_over_an_earlier_clause_is_never_answered(
    settings: VoiceSettings, rule: FakeRule
) -> None:
    io, session, talker = call(settings)

    async def drive() -> None:
        await greeted(io)
        await talked(io, 0, REQUEST)
        await io.synthesizing(1, 0)
        await io.clause_queued(1, 0)
        await io.clock.advance(0.3)
        await said(io, 1, "yes")  # over the summary, before its total
        await io.clause_played(1, 0, audio_s=1.0)
        await io.clause_queued(1, 1)
        await io.clock.advance(0.5)
        await question_ends(io)
        await io.clock.advance(1.0)

    asyncio.run(drive())
    assert handed(talker) == [(0, REQUEST)]
    assert fate(session, 1) == "went_on"
    (heard,) = [e for e in emitted(io, UserTurnEnded) if e.turn_id == 1]
    assert heard.reply_played == ""  # nothing of the reply had played whole


@pytest.mark.parametrize(
    "words",
    ["okay", "uh huh", "please", "yes?", "no", "yes, but no"],
    ids=["filler", "listening", "filler-word", "question", "no", "yes-and-no"],
)
def test_words_other_than_a_bare_yes_over_the_question_are_not_answered(
    settings: VoiceSettings, rule: FakeRule, words: str
) -> None:
    io, session, talker = call(settings)

    async def drive() -> None:
        await summary_played(io)
        await said(io, 1, words)
        await question_ends(io)
        await io.clock.advance(1.0)

    asyncio.run(drive())
    assert handed(talker) == [(0, REQUEST)]
    assert fate(session, 1) == "went_on"


def test_a_yes_over_a_reply_the_client_stopped_is_never_answered(
    settings: VoiceSettings, rule: FakeRule
) -> None:
    io, session, talker = call(settings)

    async def drive() -> None:
        await summary_played(io)
        await said(io, 1, "yes")
        await io.client(Stop(v=1, type="stop"))
        await settle()
        await io.clock.advance(1.0)

    asyncio.run(drive())
    assert handed(talker) == [(0, REQUEST)]
    assert fate(session, 1) == "went_on"


def test_two_yeses_over_one_question_are_answered_once(
    settings: VoiceSettings, rule: FakeRule
) -> None:
    io, _session, talker = call(settings)

    async def drive() -> None:
        await summary_played(io)
        await said(io, 1, "yes")
        await said(io, 2, "yeah")
        await question_ends(io)
        await io.clock.advance(1.0)

    asyncio.run(drive())
    assert handed(talker) == [(0, REQUEST), (1, "yes")]


def test_the_agents_own_words_heard_back_are_never_answered(
    settings: VoiceSettings, rule: FakeRule
) -> None:
    rule.script["yes"] = OWN_WORDS
    io, _session, talker = call(settings)

    async def drive() -> None:
        await summary_played(io)
        await said(io, 1, "yes")
        await question_ends(io)
        await waited(io)

    asyncio.run(drive())
    assert handed(talker) == [(0, REQUEST)]


@pytest.mark.parametrize("words", ["book it", "Book it."], ids=["plain", "written"])
def test_a_send_word_the_question_holds_heard_back_alone_is_never_answered(
    settings: VoiceSettings, rule: FakeRule, words: str
) -> None:
    added = settings.words.model_copy(update={"send": {"en": ("book it",)}})
    io, session, talker = call(settings.model_copy(update={"words": added}))

    async def drive() -> None:
        await summary_played(io)  # the question, "Shall I book it?", plays
        await said(io, 1, words)  # the rule's fake verdict: too few words, no echo
        await question_ends(io)
        await waited(io)

    asyncio.run(drive())
    assert handed(talker) == [(0, REQUEST)]  # the question heard back is no go-ahead
    assert fate(session, 1) == "went_on"


def test_a_yes_over_a_reply_that_ends_with_no_question_is_never_answered(
    settings: VoiceSettings, rule: FakeRule
) -> None:
    io, _session, talker = call(settings, question="Made-up closing remark.")

    async def drive() -> None:
        await summary_played(io)
        await said(io, 1, "yes")
        await question_ends(io)
        await waited(io)

    asyncio.run(drive())
    assert handed(talker) == [(0, REQUEST)]


@pytest.mark.parametrize("on", [False, True], ids=["off", "on"])
@pytest.mark.parametrize("moment", ["question", "summary"])
def test_a_yes_over_an_actions_read_back_keeps_its_own_rule(
    settings: VoiceSettings,
    rule: FakeRule,
    consent: list[dict[str, Any]],
    on: bool,
    moment: str,
) -> None:
    io, _session, talker, jobs = read_back_call(two_step(settings, answer_yes_over_question=on))

    async def drive() -> None:
        await read_back_asked(io)
        if moment == "summary":
            await read_back_clause(io, 0, played=False)
            await read_back_over(io, 1, "yes")
            await io.clause_played(1, 0, audio_s=2.0)
        else:
            await read_back_clause(io, 0)
            await read_back_clause(io, 1, played=False)
            await read_back_over(io, 1, "yes")
        await settle()
        await io.clock.advance(1.0)
        await settle()

    asyncio.run(drive())
    (run,) = jobs.runs  # the read-back's yes rule books it, whatever the new setting says
    assert run.confirmed.turn_id == 1 and answered(io) == [(1, "yes", "words")]
    assert [turn.turn_id for turn in talker.turns] == [0]  # never handed to the talker

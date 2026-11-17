"""What lets a yes held over a reply's closing question go, under
`interruptions.answer_yes_over_question` (D-116; voice/session/yes_over_question.py's Dropped;
adversarial, GP-08), as a yes held over a read-back is let go (held_yes.py): a no said after it,
over the question or in its tail, in English or Saudi Arabic; a turn begun in the tail that the
speech detector reports late, which the held yes waits for; words said once the agent was
silent, which are answered alone; a stop in the tail, answered alone; and words begun after a
yes whose transcript came first. Fillers or listening sounds after it keep it, and words begun
before it say nothing of it. The interruption rule is the tests' fake (overlap_support.py);
every text is made up."""

from __future__ import annotations

import asyncio
import logging

import pytest
from t2_agentic_voice.core.config import VoiceSettings

from tests.t2_agentic_voice.voice.session.overlap_support import (
    NEW_WORDS,
    FakeRule,
    overlap_part,
)
from tests.t2_agentic_voice.voice.session.talker_support import settle, talked
from tests.t2_agentic_voice.voice.session.yes_question_support import (
    REQUEST,
    SAUDI_NO,
    SAUDI_QUESTION,
    SAUDI_SUMMARY,
    SAUDI_YES,
    call,
    fate,
    handed,
    question_ends,
    said,
    summary_played,
    waited,
)

DONT = "No, don't book it."  # words the fake rule is scripted to stop the reply for


@pytest.mark.parametrize("moment", ["question", "tail"])
@pytest.mark.parametrize("language", ["en", "ar-SA"])
def test_a_no_said_after_a_held_yes_lets_it_go(
    settings: VoiceSettings,
    rule: FakeRule,
    caplog: pytest.LogCaptureFixture,
    moment: str,
    language: str,
) -> None:
    saudi = language == "ar-SA"
    yes, no = (SAUDI_YES, SAUDI_NO) if saudi else ("yes", "no")
    if saudi:
        io, session, talker = call(
            settings, summary=SAUDI_SUMMARY, question=SAUDI_QUESTION, language="ar-SA"
        )
    else:
        io, session, talker = call(settings)
    heard_in = "ar" if saudi else "en"
    caplog.set_level(logging.INFO)

    async def drive() -> None:
        await summary_played(io)
        await said(io, 1, yes, language=heard_in)
        if moment == "tail":
            await question_ends(io)
            await said(io, 2, no, language=heard_in)  # 0.2 s after the reply ended
        else:
            await said(io, 2, no, language=heard_in)
            await question_ends(io)
        await waited(io)
        await io.clock.advance(1.0)
        await settle()

    asyncio.run(drive())
    assert handed(talker) == [(0, REQUEST)]  # neither is answered: the yes was taken back
    assert (fate(session, 1), fate(session, 2)) == ("went_on", "went_on")
    lines = [vars(r)["fields"] for r in caplog.records if r.getMessage() == "question_yes_let_go"]
    assert lines == [{"call_id": io.setup.call_id, "turn_id": 1, "why": "words"}]


def test_a_held_yes_waits_for_a_turn_begun_in_the_tail_that_opens_late(
    settings: VoiceSettings, rule: FakeRule
) -> None:
    io, _session, talker = call(settings)
    before: list[list[tuple[int, str]]] = []

    async def drive() -> None:
        await summary_played(io)
        await said(io, 1, "yes")
        await question_ends(io)
        ended = io.clock.now()
        await io.clock.advance(0.45)
        await settle()
        before.append(handed(talker))  # not answered yet: a turn begun in the tail may open
        await said(io, 2, "no", speech_at=ended + 0.25)  # reported only now, backdated
        await waited(io)

    asyncio.run(drive())
    assert before == [[(0, REQUEST)]]
    assert handed(talker) == [(0, REQUEST)]


def test_words_said_once_the_agent_was_silent_are_answered_alone(
    settings: VoiceSettings, rule: FakeRule
) -> None:
    io, session, talker = call(settings)

    async def drive() -> None:
        await summary_played(io)
        await said(io, 1, "yes")
        await question_ends(io)
        await io.clock.advance(0.35)  # past the tail: no overlap
        await talked(io, 2, "no")
        await waited(io)

    asyncio.run(drive())
    assert handed(talker) == [(0, REQUEST), (2, "no")]  # the held yes is never answered too
    assert fate(session, 1) == "went_on"


def test_a_stop_in_the_tail_after_a_held_yes_is_answered_alone(
    settings: VoiceSettings, rule: FakeRule
) -> None:
    rule.script[DONT] = NEW_WORDS
    io, session, talker = call(settings)

    async def drive() -> None:
        await summary_played(io)
        await said(io, 1, "yes")
        await question_ends(io)
        await said(io, 2, DONT)
        await waited(io)

    asyncio.run(drive())
    assert handed(talker) == [(0, REQUEST), (2, DONT)]
    assert fate(session, 1) == "went_on"


@pytest.mark.parametrize("words", ["uh huh", "okay", "yeah"], ids=["listening", "filler", "yes"])
def test_fillers_listening_sounds_or_a_yes_after_a_held_yes_keep_it(
    settings: VoiceSettings, rule: FakeRule, words: str
) -> None:
    io, _session, talker = call(settings)

    async def drive() -> None:
        await summary_played(io)
        await said(io, 1, "yes")
        await said(io, 2, words)
        await question_ends(io)
        await waited(io)

    asyncio.run(drive())
    assert handed(talker) == [(0, REQUEST), (1, "yes")]


@pytest.mark.parametrize("first", ["yes", "no"])
def test_words_count_in_the_order_said_not_the_order_heard(
    settings: VoiceSettings, rule: FakeRule, first: str
) -> None:
    io, _session, talker = call(settings)
    second = "no" if first == "yes" else "yes"

    async def drive() -> None:
        await summary_played(io)
        await io.turn_opened(1)  # `first` begins first
        await io.clock.advance(0.1)
        await io.turn_opened(2)
        await overlap_part(io, 2, second)  # but the later words are heard first
        await io.turn_closed(2)
        await io.transcribed(2, second, language="en")
        await overlap_part(io, 1, first)
        await io.turn_closed(1)
        await io.transcribed(1, first, language="en")
        await settle()
        await question_ends(io)
        await waited(io)

    asyncio.run(drive())
    if first == "yes":  # the no said after it takes it back, though heard before it
        assert handed(talker) == [(0, REQUEST)]
    else:  # a no said before the yes says nothing of it
        assert handed(talker) == [(0, REQUEST), (2, "yes")]

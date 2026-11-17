"""A yes held over an action's read-back (D-108; voice/session/held_yes.py) against the times
speech is reported at, adversarial (GP-08): a turn begun before the summary's end, which the
speech detector opens only once it has lasted `turns.vad_start_ms`, still cancels a yes held, the
booking waiting that long after the summary's end; words said over a clause of the same reply
before the summary, while the summary's audio is already queued behind it, are never held; and
words count in the order they were said, not the order their transcripts came, so a later
transcript of earlier words neither holds a yes after other words nor cancels the chat model's
request on a newer answer. The interruption rule is the tests' fake; every text is made up."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from typing import Any

import pytest
from t2_agentic_voice.agent.events import ReadBackRequested
from t2_agentic_voice.agent.talker import ModelReplied, ModelRequested, ReplyDone, SpokenClause
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.conversation import TalkerTurn
from t2_agentic_voice.domain.ports.chat_model import Usage
from t2_agentic_voice.testing.llm_fakes import Pause, ScriptedLLM

from tests.t2_agentic_voice.voice.session.held_yes_support import (
    ASKS,
    BOOK_WAIT_S,
    OTHER,
    UNPLACED,
    answered,
    call,
    scripted_rule,
    summary_plays,
)
from tests.t2_agentic_voice.voice.session.overlap_support import FakeRule, overlap_part
from tests.t2_agentic_voice.voice.session.read_back_support import PLAN, YES_TEXT, asked, over
from tests.t2_agentic_voice.voice.session.talker_support import MODEL, Step, answer, settle


@pytest.fixture
def rule(rule: FakeRule) -> FakeRule:
    """The rule as the held-yes tests script it (held_yes_support.py's `scripted_rule`)."""
    return scripted_rule(rule)


@pytest.mark.parametrize("later", ["no", OTHER], ids=["no", "other_word"])
def test_a_turn_begun_before_the_summary_ended_cancels_a_held_yes_though_it_opens_after(
    settings: VoiceSettings, rule: FakeRule, consent: list[dict[str, Any]], later: str
) -> None:
    io, session, _talker, jobs = call(settings)
    at_end: list[int] = []

    async def drive() -> None:
        await summary_plays(io)
        await over(io, 1, YES_TEXT)  # held
        await io.synthesizing(1, 1)
        await io.clause_queued(1, 1)  # the closing question queued behind the summary
        ended = io.clock.now()
        await io.clause_played(1, 0, audio_s=2.0)  # the summary ends
        await settle()
        at_end.append(len(jobs.runs))
        await io.clock.advance(0.05)  # the detector reports the turn begun 0.15 s before
        await io.turn_opened(2, speech_at=ended - 0.15)
        await overlap_part(io, 2, later)
        await io.turn_closed(2)
        await io.transcribed(2, later, language="en")
        await settle()
        await io.clock.advance(BOOK_WAIT_S)
        await settle()

    asyncio.run(drive())
    assert at_end == [0]  # never booked at the summary's end itself
    assert jobs.runs == [] and answered(io) == []
    assert session._confirming.active  # the read-back goes on, for the caller to answer


def _preamble(turn: TalkerTurn) -> Sequence[Step]:
    """Turn 0's reply says a clause of the talker's own, then reads `PLAN` back."""
    if turn.turn_id != 0:
        return answer("Made-up answer.")
    usage = Usage(input_tokens=1, output_tokens=1)
    return [
        ModelRequested(model=MODEL),
        ModelReplied(model=MODEL, usage=usage, first_token_s=0.1),
        SpokenClause(text="A made-up line of the talker's.", language="en"),
        ReadBackRequested(plan=PLAN),
        ReplyDone(),
    ]


@pytest.mark.parametrize(("when", "books"), [("before", False), ("over", True)])
def test_a_yes_said_while_the_summary_was_queued_behind_another_clause_is_never_held(
    settings: VoiceSettings,
    rule: FakeRule,
    consent: list[dict[str, Any]],
    when: str,
    books: bool,
) -> None:
    """Reply 1 says the talker's clause (0), then the summary (1) and the question (2); the
    summary's first audio is queued while clause 0 still plays, so it is heard only once that
    clause played."""
    io, session, _talker, jobs = call(settings, script=_preamble)

    async def drive() -> None:
        await asked(io)
        for index in (0, 1):
            await io.synthesizing(1, index)
            await io.clause_queued(1, index)
            await io.clock.advance(0.3)
        if when == "before":
            await over(io, 1, YES_TEXT)  # over the talker's clause: none of the summary heard
        await io.clause_played(1, 0, audio_s=1.5)  # the summary is heard from now
        await io.clock.advance(0.5)
        if when == "over":
            await over(io, 1, YES_TEXT)
        await io.clock.advance(1.5)
        await io.clause_played(1, 1, audio_s=2.0)  # the summary played whole
        await settle()
        await io.clock.advance(BOOK_WAIT_S)
        await settle()

    asyncio.run(drive())
    read_back = session._confirming.read_back
    if books:
        assert [(r.confirmed.turn_id, r.confirmed.words) for r in jobs.runs] == [(1, YES_TEXT)]
        return
    assert read_back is not None and read_back.summary == (1,)
    assert jobs.runs == [] and answered(io) == []


def test_a_yes_whose_transcript_comes_after_later_words_dropped_it_is_never_held(
    settings: VoiceSettings, rule: FakeRule, consent: list[dict[str, Any]]
) -> None:
    io, session, _talker, jobs = call(settings)

    async def drive() -> None:
        await summary_plays(io)
        await io.turn_opened(1)
        await overlap_part(io, 1, YES_TEXT)
        await io.turn_closed(1)  # its own transcript still to come
        await io.clock.advance(0.3)
        await over(io, 2, OTHER)  # said after the yes, its transcript first
        await io.transcribed(1, YES_TEXT, language="en")
        await settle()
        await io.clause_played(1, 0, audio_s=2.0)
        await settle()
        await io.clock.advance(BOOK_WAIT_S)
        await settle()

    asyncio.run(drive())
    assert jobs.runs == [] and answered(io) == []
    assert session._confirming.active


def test_a_late_transcript_over_the_summary_never_cancels_a_newer_answers_model_request(
    settings: VoiceSettings, rule: FakeRule, consent: list[dict[str, Any]]
) -> None:
    """The newer answer, over the closing question, waits on the chat model; the yes said over
    the summary before it, its transcript late, decides nothing."""
    llm = ScriptedLLM([(Pause(1.0), *ScriptedLLM.reply("yes"))])
    io, _session, _talker, jobs = call(settings, agent=ASKS, overlap_model=llm)
    llm.clock = io.clock

    async def drive() -> None:
        await summary_plays(io)
        await io.turn_opened(1)
        await overlap_part(io, 1, YES_TEXT)
        await io.turn_closed(1)  # its own transcript still to come
        await io.clause_played(1, 0, audio_s=2.0)  # the summary ends
        await settle()
        await io.synthesizing(1, 1)
        await io.clause_queued(1, 1)
        await io.clock.advance(0.3)
        await over(io, 2, UNPLACED)  # over the closing question: put to the model
        await io.transcribed(1, YES_TEXT, language="en")  # turn 1's, late
        await settle()
        await io.clock.advance(1.5)  # the model's word lands
        await settle()

    asyncio.run(drive())
    assert len(llm.requests) == 1
    assert [(r.confirmed.turn_id, r.confirmed.words) for r in jobs.runs] == [(2, UNPLACED)]
    assert answered(io) == [(2, "yes", "model")]

"""A yes over an action's read-back under `interruptions.yes_over_read_back` (D-108, the owner's
ruling of 2026-11-17, "Any yes books"; voice/session/held_yes.py, read_back_heard.py,
yes_turns.py; docs/SECURITY.md, invariant 1), on the real yes rule: a yes said over the summary
is held, the summary playing on, and books once the summary has played whole, the closing
question cut and the sending line said as the reply answering the yes; a second yes, a filler or
a listening sound keeps it held, and any other words drop it; a bare yes over the closing
question books; khalas beside a yes plays on and books, khalas alone still stops it; for an
agent that asks, unplaced words over the summary go to the chat model, its yes held, its no
declining the read-back. With the setting off each moment is as before (characterization).
Adversarial (GP-08): nothing is confirmed before the summary has played whole, from a yes
followed by other words, from words said before the read-back began, from the agent's own lines
heard back, or from a yes held on a read-back a new one replaced. The interruption rule is the
tests' fake (overlap_support.py); every text is made up."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.conversation import DeclinedAction
from t2_agentic_voice.voice.session.commands import StopSpeaking

from tests.t2_agentic_voice.voice.session.held_yes_support import (
    BARE_YES,
    LISTENING_WORD,
    OTHER,
    QUESTION_BACK,
    SENDING,
    answered,
    call,
    said_in,
    scripted_rule,
    summary_ends,
    summary_plays,
)
from tests.t2_agentic_voice.voice.session.overlap_support import (
    REPEAT_TEXT,
    FakeRule,
    overlap_part,
)
from tests.t2_agentic_voice.voice.session.read_back_support import (
    ACTION,
    CALLER_WORDS,
    DRAFT,
    YES_TEXT,
    asked,
    clause,
    over,
)
from tests.t2_agentic_voice.voice.session.talker_support import settle


@pytest.fixture
def rule(rule: FakeRule) -> FakeRule:
    """The rule as these tests script it (held_yes_support.py's `scripted_rule`)."""
    return scripted_rule(rule)


@pytest.mark.parametrize("on", [False, True], ids=["off", "on"])
@pytest.mark.parametrize("text", [YES_TEXT, BARE_YES, "send it"], ids=["yes", "bare", "send"])
def test_a_yes_over_the_summary_books_once_it_played_whole_only_under_the_setting(
    settings: VoiceSettings, rule: FakeRule, consent: list[dict[str, Any]], on: bool, text: str
) -> None:
    io, session, _talker, jobs = call(settings, on)
    before: list[int] = []

    async def drive() -> None:
        await summary_plays(io)
        await over(io, 1, text)
        before.append(len(jobs.runs))
        await summary_ends(io)

    asyncio.run(drive())
    assert before == [0]  # never before the summary has played whole
    if not on:  # as before: it counts for nothing, and the closing question is waited for
        assert jobs.runs == [] and answered(io) == []
        assert io.commands.of(StopSpeaking) == []
        assert session._confirming.active
        return
    (run,) = jobs.runs
    assert (run.confirmed.turn_id, run.confirmed.words, run.confirmed.draft_json) == (
        1,
        text,
        DRAFT,
    )
    assert run.confirmed.action == ACTION
    assert answered(io) == [(1, "yes", "words")]
    assert len(io.commands.of(StopSpeaking)) == 1  # the closing question cut, never played
    assert said_in(io, 2) == SENDING  # the sending line answers the yes
    assert not session._confirming.active
    assert [t.fate for t in session.history.turns()][1] == "answered"


def test_a_yes_whose_words_come_after_the_summary_ended_books_when_they_come(
    settings: VoiceSettings, rule: FakeRule, consent: list[dict[str, Any]]
) -> None:
    io, _session, _talker, jobs = call(settings)

    async def drive() -> None:
        await summary_plays(io)
        await io.turn_opened(1)
        await io.clock.advance(0.3)
        await summary_ends(io)
        assert jobs.runs == []  # its words not yet heard
        await overlap_part(io, 1, YES_TEXT)
        await io.turn_closed(1)
        await io.transcribed(1, YES_TEXT, language="en")
        await settle()

    asyncio.run(drive())
    (run,) = jobs.runs
    assert run.confirmed.turn_id == 1
    assert answered(io) == [(1, "yes", "words")]


@pytest.mark.parametrize(
    ("later", "books"),
    [
        (LISTENING_WORD, True),
        ("please", True),
        (BARE_YES, True),
        (OTHER, False),
        (QUESTION_BACK, False),
        ("no", False),
    ],
    ids=["listening", "filler", "second_yes", "other_word", "question", "no"],
)
def test_words_after_a_held_yes_keep_it_only_when_they_say_nothing_else(
    settings: VoiceSettings,
    rule: FakeRule,
    consent: list[dict[str, Any]],
    later: str,
    books: bool,
) -> None:
    """GP-08: a yes followed by other words before the summary's end never books."""
    io, session, _talker, jobs = call(settings)

    async def drive() -> None:
        await summary_plays(io)
        await over(io, 1, YES_TEXT)
        await io.clock.advance(0.2)
        await over(io, 2, later)
        await summary_ends(io)

    asyncio.run(drive())
    if books:
        (run,) = jobs.runs
        assert run.confirmed.turn_id == 1  # the first yes, held
        return
    assert jobs.runs == [] and answered(io) == []
    assert session._confirming.active  # the read-back goes on, for the caller to answer


def test_real_words_after_a_held_yes_stop_the_read_back_and_reach_the_talker(
    settings: VoiceSettings, rule: FakeRule, consent: list[dict[str, Any]]
) -> None:
    io, session, talker, jobs = call(settings)

    async def drive() -> None:
        await summary_plays(io)
        await over(io, 1, YES_TEXT)
        await over(io, 2, CALLER_WORDS)  # they stop it

    asyncio.run(drive())
    assert jobs.runs == []
    assert not session._confirming.active
    assert talker.turns[-1].declined == DeclinedAction(
        action=ACTION, kind="correction", words=CALLER_WORDS
    )


def test_a_held_yes_waits_while_later_words_are_still_being_said(
    settings: VoiceSettings, rule: FakeRule, consent: list[dict[str, Any]]
) -> None:
    io, _session, _talker, jobs = call(settings)

    async def drive() -> None:
        await summary_plays(io)
        await over(io, 1, YES_TEXT)
        await io.turn_opened(2)  # the caller speaks again, still at the summary's end
        await summary_ends(io)
        assert jobs.runs == []
        await overlap_part(io, 2, OTHER)
        await io.turn_closed(2)
        await io.transcribed(2, OTHER, language="en")
        await settle()

    asyncio.run(drive())
    assert jobs.runs == []  # its words were other words: the yes is dropped


def test_words_said_before_the_read_back_began_are_never_held(
    settings: VoiceSettings, rule: FakeRule, consent: list[dict[str, Any]]
) -> None:
    """GP-08: a yes begun in the gap before the summary's first audio declines it, as before."""
    io, _session, talker, jobs = call(settings)

    async def drive() -> None:
        await asked(io)
        await io.turn_opened(1)  # in the gap: nothing of the read-back has played yet
        await clause(io, 0)  # the summary plays whole over the caller
        await io.turn_closed(1)
        await io.transcribing(1)
        await io.transcribed(1, YES_TEXT, language="en")
        await settle()

    asyncio.run(drive())
    assert jobs.runs == [] and answered(io) == []
    assert talker.turns[-1].declined == DeclinedAction(
        action=ACTION, kind="correction", words=YES_TEXT
    )


@pytest.mark.parametrize("played", [{"audio_s": 0.0}, {"cut_short": True}], ids=["silent", "cut"])
def test_a_summary_that_did_not_play_whole_books_nothing(
    settings: VoiceSettings, rule: FakeRule, consent: list[dict[str, Any]], played: dict[str, Any]
) -> None:
    """GP-08: no receipt, no yes, whatever was held."""
    io, _session, _talker, jobs = call(settings)

    async def drive() -> None:
        await summary_plays(io)
        await over(io, 1, YES_TEXT)
        await summary_ends(io, **played)
        await clause(io, 1)
        await settle()

    asyncio.run(drive())
    assert jobs.runs == [] and answered(io) == []


def test_a_yes_held_on_a_read_back_said_again_never_books_the_new_one(
    settings: VoiceSettings, rule: FakeRule, consent: list[dict[str, Any]]
) -> None:
    """GP-08: a held yes is of one read-back only; a new reading needs its own yes."""
    io, session, _talker, jobs = call(settings)

    async def drive() -> None:
        await summary_plays(io)
        await over(io, 1, YES_TEXT)
        await over(io, 2, REPEAT_TEXT)  # said again: reply 2 is the read-back now
        for index in (0, 1):
            await io.synthesizing(2, index)
            await io.clause_queued(2, index)
            await io.clock.advance(0.5)
            await io.clause_played(2, index, audio_s=2.0)
        await settle()

    asyncio.run(drive())
    assert jobs.runs == [] and answered(io) == []
    assert session._confirming.active and session._confirming.read_back is not None
    assert session._confirming.read_back.reply_id == 2


@pytest.mark.parametrize("on", [False, True], ids=["off", "on"])
def test_a_bare_yes_over_the_closing_question_books_only_under_the_setting(
    settings: VoiceSettings, rule: FakeRule, consent: list[dict[str, Any]], on: bool
) -> None:
    io, _session, _talker, jobs = call(settings, on)

    async def drive() -> None:
        await asked(io)
        await clause(io, 0)
        await clause(io, 1, played=False)
        await over(io, 1, BARE_YES)

    asyncio.run(drive())
    if on:
        (run,) = jobs.runs
        assert run.confirmed.turn_id == 1 and answered(io) == [(1, "yes", "words")]
    else:  # the owner's 2026-11-10 ruling: asked again
        assert jobs.runs == [] and answered(io) == [(1, "asked_again", "words")]

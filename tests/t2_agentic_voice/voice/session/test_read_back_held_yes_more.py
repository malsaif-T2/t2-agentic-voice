"""A yes over an action's read-back under `interruptions.yes_over_read_back` (D-108), the rest of
test_read_back_held_yes.py's moments: khalas beside a yes and alone; for an agent that asks,
unplaced words over the summary judged by the chat model; the summary heard back never held;
and an answer after the summary beside a held yes. Every text is made up."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.conversation import DeclinedAction
from t2_agentic_voice.domain.yes_words import ConsentWords
from t2_agentic_voice.testing.llm_fakes import ScriptedLLM
from t2_agentic_voice.voice.session import read_back
from t2_agentic_voice.voice.session.call import CallSession
from t2_agentic_voice.voice.session.commands import StopSpeaking

from tests.t2_agentic_voice.session_fakes import FakeSessionIO
from tests.t2_agentic_voice.voice.session.held_yes_support import (
    ASKS,
    ECHO,
    KHALAS,
    KHALAS_YES,
    UNPLACED,
    answered,
    call,
    scripted_rule,
    summary_ends,
    summary_plays,
)
from tests.t2_agentic_voice.voice.session.overlap_support import (
    FakeRule,
    overlap_part,
)
from tests.t2_agentic_voice.voice.session.read_back_support import (
    ACTION,
    CONSENT,
    YES_TEXT,
    over,
)
from tests.t2_agentic_voice.voice.session.talker_support import FakeTalker, settle
from tests.t2_agentic_voice.voice.session.yes_support import FakeJobs


@pytest.fixture
def rule(rule: FakeRule) -> FakeRule:
    """The rule as these tests script it (held_yes_support.py's `scripted_rule`)."""
    return scripted_rule(rule)


@pytest.fixture
def khalas(monkeypatch: pytest.MonkeyPatch) -> None:
    """The yes rule's words as CONSENT's, khalas among the fillers, as the Arabic lists hold it."""
    fillers = (*CONSENT.fillers, KHALAS)
    words = ConsentWords(yes=CONSENT.yes, send=CONSENT.send, no=CONSENT.no, fillers=fillers)
    monkeypatch.setattr(read_back, "consent_words", lambda code, **given: words)


@pytest.mark.parametrize("on", [False, True], ids=["off", "on"])
def test_khalas_beside_a_yes_over_the_summary_plays_on_and_books_only_under_the_setting(
    settings: VoiceSettings, rule: FakeRule, khalas: None, on: bool
) -> None:
    io, session, talker, jobs = call(settings, on)

    async def drive() -> None:
        await summary_plays(io)
        await over(io, 1, KHALAS_YES)
        if on:  # off, it stopped the read-back
            await summary_ends(io)

    asyncio.run(drive())
    if on:
        (run,) = jobs.runs
        assert run.confirmed.words == KHALAS_YES
        return
    assert jobs.runs == []  # as before: a stop word, which stops the read-back
    assert talker.turns[-1].declined == DeclinedAction(
        action=ACTION, kind="stopped", words=KHALAS_YES
    )
    assert not session._confirming.active


def test_khalas_alone_still_stops_the_read_back_under_the_setting(
    settings: VoiceSettings, rule: FakeRule, khalas: None
) -> None:
    io, session, talker, jobs = call(settings)

    async def drive() -> None:
        await summary_plays(io)
        await over(io, 1, KHALAS)  # it stops the read-back

    asyncio.run(drive())
    assert jobs.runs == [] and not session._confirming.active
    assert talker.turns[-1].declined == DeclinedAction(action=ACTION, kind="stopped", words=KHALAS)


def _asking(
    settings: VoiceSettings, word: str
) -> tuple[FakeSessionIO, CallSession, FakeTalker, FakeJobs, ScriptedLLM]:
    llm = ScriptedLLM([ScriptedLLM.reply(word)])
    io, session, talker, jobs = call(settings, agent=ASKS, overlap_model=llm)
    llm.clock = io.clock
    return io, session, talker, jobs, llm


@pytest.mark.parametrize("word", ["yes", "send"])
def test_unplaced_words_over_the_summary_go_to_the_model_and_its_yes_is_held(
    settings: VoiceSettings, rule: FakeRule, consent: list[dict[str, Any]], word: str
) -> None:
    io, session, _talker, jobs, llm = _asking(settings, word)

    async def drive() -> None:
        await summary_plays(io)
        await over(io, 1, UNPLACED)
        assert jobs.runs == [] and session._confirming.active  # the summary plays on
        await summary_ends(io)

    asyncio.run(drive())
    assert len(llm.requests) == 1
    (run,) = jobs.runs
    assert (run.confirmed.turn_id, run.confirmed.words) == (1, UNPLACED)
    assert answered(io) == [(1, "yes", "model")]


def test_the_models_no_on_words_over_the_summary_declines_it_and_reaches_the_talker(
    settings: VoiceSettings, rule: FakeRule, consent: list[dict[str, Any]]
) -> None:
    io, session, talker, jobs, _llm = _asking(settings, "no")

    async def drive() -> None:
        await summary_plays(io)
        await over(io, 1, UNPLACED)  # the model's no stops it

    asyncio.run(drive())
    assert jobs.runs == [] and not session._confirming.active
    assert len(io.commands.of(StopSpeaking)) == 1  # the summary stopped
    assert talker.turns[-1].declined == DeclinedAction(action=ACTION, kind="no", words=UNPLACED)


@pytest.mark.parametrize("word", ["yes", "no"])
def test_the_summary_heard_back_is_never_held_nor_declines_it(
    settings: VoiceSettings, rule: FakeRule, consent: list[dict[str, Any]], word: str
) -> None:
    """GP-08: the echo rail, over the summary, on the model's yes and its no."""
    io, session, _talker, jobs, _llm = _asking(settings, word)

    async def drive() -> None:
        await summary_plays(io)
        await over(io, 1, ECHO)
        await summary_ends(io)

    asyncio.run(drive())
    assert jobs.runs == [] and answered(io) == []
    assert session._confirming.active and io.commands.of(StopSpeaking) == []


def test_an_agent_that_does_not_ask_counts_unplaced_words_over_the_summary_for_nothing(
    settings: VoiceSettings, rule: FakeRule, consent: list[dict[str, Any]]
) -> None:
    io, session, _talker, jobs = call(settings)

    async def drive() -> None:
        await summary_plays(io)
        await over(io, 1, YES_TEXT)
        await over(io, 2, UNPLACED)
        await summary_ends(io)

    asyncio.run(drive())
    assert jobs.runs == []  # other words after the yes: dropped
    assert session._confirming.active


@pytest.mark.parametrize(
    ("later", "books"), [("please", True), ("no", False)], ids=["filler", "no"]
)
def test_an_answer_after_the_summary_beside_a_held_yes_books_it_only_when_it_says_nothing(
    settings: VoiceSettings, rule: FakeRule, consent: list[dict[str, Any]], later: str, books: bool
) -> None:
    """A yes over the summary whose words come once the caller speaks again over the closing
    question: fillers alone then book the held yes; a no is the yes rule's, as any answer is."""
    io, _session, talker, jobs = call(settings)

    async def drive() -> None:
        await summary_plays(io)
        await io.turn_opened(1)
        await io.clock.advance(0.2)
        await summary_ends(io)
        await io.turn_opened(2)  # over the closing question
        await overlap_part(io, 1, YES_TEXT)
        await io.turn_closed(1)
        await io.transcribed(1, YES_TEXT, language="en")
        await settle()
        assert jobs.runs == []  # held, its later words still being said
        await overlap_part(io, 2, later)
        await io.turn_closed(2)
        await io.transcribed(2, later, language="en")
        await settle()

    asyncio.run(drive())
    if books:
        (run,) = jobs.runs
        assert run.confirmed.turn_id == 1
        return
    assert jobs.runs == []
    assert talker.turns[-1].declined == DeclinedAction(action=ACTION, kind="no", words=later)

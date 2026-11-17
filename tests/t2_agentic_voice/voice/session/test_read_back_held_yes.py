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
from t2_agentic_voice.core.events import ConfirmationAnswered
from t2_agentic_voice.domain.text.invisible import provider_text
from t2_agentic_voice.domain.words import PRESET_WORDS
from t2_agentic_voice.domain.yes_words import ConsentWords
from t2_agentic_voice.testing.llm_fakes import ScriptedLLM
from t2_agentic_voice.voice.session import read_back
from t2_agentic_voice.voice.session.call import CallSession
from t2_agentic_voice.voice.session.commands import StopSpeaking

from tests.t2_agentic_voice.session_fakes import FakeSessionIO
from tests.t2_agentic_voice.voice.session.overlap_support import (
    NEW_WORDS,
    REPEAT,
    REPEAT_TEXT,
    STOP,
    FakeRule,
    overlap_part,
    two_step,
)
from tests.t2_agentic_voice.voice.session.read_back_support import (
    ACTION,
    CALLER_WORDS,
    CONSENT,
    DRAFT,
    PLAN,
    SUMMARY_SPOKEN,
    YES_TEXT,
    asked,
    clause,
    over,
)
from tests.t2_agentic_voice.voice.session.session_support import emitted, speaks
from tests.t2_agentic_voice.voice.session.talker_support import AGENT, FakeTalker, settle
from tests.t2_agentic_voice.voice.session.yes_support import FakeJobs, confirm_call

SENDING = [provider_text(PLAN.sending.spoken)]
LISTENING_WORD = PRESET_WORDS["en"].backchannel[0]
BARE_YES = "made-up-yes"  # CONSENT's own yes word, said alone
OTHER = "made-up-word"  # one word on no list, which the fake rule lets go on
QUESTION_BACK = "made-up question?"
KHALAS = "خلاص"  # khalas, that's it: a stop word of the call's here, and a filler
KHALAS_YES = f"{KHALAS} yes"
ASKS = AGENT.model_copy(update={"ask_on_unlisted_answers": True})
UNPLACED = "sounds fine to me"  # words on none of CONSENT's lists
ECHO = provider_text(SUMMARY_SPOKEN)  # the summary heard back


@pytest.fixture
def rule(rule: FakeRule) -> FakeRule:
    """The rule as these tests script it: real words stop the agent, and so do khalas and
    khalas beside a yes, as the real rule's stop word does; a repeat request repeats."""
    rule.script |= {
        CALLER_WORDS: NEW_WORDS,
        REPEAT_TEXT: REPEAT,
        KHALAS: STOP,
        KHALAS_YES: STOP,
    }
    return rule


def _settings(settings: VoiceSettings, on: bool) -> VoiceSettings:
    """`settings` under two_step, the setting `on` or off, khalas a stop word of the call's."""
    words = settings.words.model_copy(update={"stop": {"en": (KHALAS,)}})
    return two_step(settings, yes_over_read_back=on).model_copy(update={"words": words})


def _call(
    settings: VoiceSettings, on: bool = True, **given: Any
) -> tuple[FakeSessionIO, CallSession, FakeTalker, FakeJobs]:
    jobs = FakeJobs()
    io, session, talker = confirm_call(_settings(settings, on), jobs, **given)
    return io, session, talker, jobs


def _answered(io: FakeSessionIO) -> list[tuple[int | None, str, str]]:
    return [(e.turn_id, e.decision, e.by) for e in emitted(io, ConfirmationAnswered)]


def _said(io: FakeSessionIO, reply_id: int) -> list[str]:
    return [speak.text for speak in speaks(io, reply_id)]


async def _summary_plays(io: FakeSessionIO) -> None:
    """The read-back (reply 1) is asked for, and its summary's first audio queued, 0.5 s ago."""
    await asked(io)
    await clause(io, 0, played=False)


async def _summary_ends(io: FakeSessionIO, **given: Any) -> None:
    await io.clause_played(1, 0, **{"audio_s": 2.0, **given})
    await settle()


@pytest.mark.parametrize("on", [False, True], ids=["off", "on"])
@pytest.mark.parametrize("text", [YES_TEXT, BARE_YES, "send it"], ids=["yes", "bare", "send"])
def test_a_yes_over_the_summary_books_once_it_played_whole_only_under_the_setting(
    settings: VoiceSettings, rule: FakeRule, consent: list[dict[str, Any]], on: bool, text: str
) -> None:
    io, session, _talker, jobs = _call(settings, on)
    before: list[int] = []

    async def drive() -> None:
        await _summary_plays(io)
        await over(io, 1, text)
        before.append(len(jobs.runs))
        await _summary_ends(io)

    asyncio.run(drive())
    assert before == [0]  # never before the summary has played whole
    if not on:  # as before: it counts for nothing, and the closing question is waited for
        assert jobs.runs == [] and _answered(io) == []
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
    assert _answered(io) == [(1, "yes", "words")]
    assert len(io.commands.of(StopSpeaking)) == 1  # the closing question cut, never played
    assert _said(io, 2) == SENDING  # the sending line answers the yes
    assert not session._confirming.active
    assert [t.fate for t in session.history.turns()][1] == "answered"


def test_a_yes_whose_words_come_after_the_summary_ended_books_when_they_come(
    settings: VoiceSettings, rule: FakeRule, consent: list[dict[str, Any]]
) -> None:
    io, _session, _talker, jobs = _call(settings)

    async def drive() -> None:
        await _summary_plays(io)
        await io.turn_opened(1)
        await io.clock.advance(0.3)
        await _summary_ends(io)
        assert jobs.runs == []  # its words not yet heard
        await overlap_part(io, 1, YES_TEXT)
        await io.turn_closed(1)
        await io.transcribed(1, YES_TEXT, language="en")
        await settle()

    asyncio.run(drive())
    (run,) = jobs.runs
    assert run.confirmed.turn_id == 1
    assert _answered(io) == [(1, "yes", "words")]


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
    io, session, _talker, jobs = _call(settings)

    async def drive() -> None:
        await _summary_plays(io)
        await over(io, 1, YES_TEXT)
        await io.clock.advance(0.2)
        await over(io, 2, later)
        await _summary_ends(io)

    asyncio.run(drive())
    if books:
        (run,) = jobs.runs
        assert run.confirmed.turn_id == 1  # the first yes, held
        return
    assert jobs.runs == [] and _answered(io) == []
    assert session._confirming.active  # the read-back goes on, for the caller to answer


def test_real_words_after_a_held_yes_stop_the_read_back_and_reach_the_talker(
    settings: VoiceSettings, rule: FakeRule, consent: list[dict[str, Any]]
) -> None:
    io, session, talker, jobs = _call(settings)

    async def drive() -> None:
        await _summary_plays(io)
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
    io, _session, _talker, jobs = _call(settings)

    async def drive() -> None:
        await _summary_plays(io)
        await over(io, 1, YES_TEXT)
        await io.turn_opened(2)  # the caller speaks again, still at the summary's end
        await _summary_ends(io)
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
    io, _session, talker, jobs = _call(settings)

    async def drive() -> None:
        await asked(io)
        await io.turn_opened(1)  # in the gap: nothing of the read-back has played yet
        await clause(io, 0)  # the summary plays whole over the caller
        await io.turn_closed(1)
        await io.transcribing(1)
        await io.transcribed(1, YES_TEXT, language="en")
        await settle()

    asyncio.run(drive())
    assert jobs.runs == [] and _answered(io) == []
    assert talker.turns[-1].declined == DeclinedAction(
        action=ACTION, kind="correction", words=YES_TEXT
    )


@pytest.mark.parametrize("played", [{"audio_s": 0.0}, {"cut_short": True}], ids=["silent", "cut"])
def test_a_summary_that_did_not_play_whole_books_nothing(
    settings: VoiceSettings, rule: FakeRule, consent: list[dict[str, Any]], played: dict[str, Any]
) -> None:
    """GP-08: no receipt, no yes, whatever was held."""
    io, _session, _talker, jobs = _call(settings)

    async def drive() -> None:
        await _summary_plays(io)
        await over(io, 1, YES_TEXT)
        await _summary_ends(io, **played)
        await clause(io, 1)
        await settle()

    asyncio.run(drive())
    assert jobs.runs == [] and _answered(io) == []


def test_a_yes_held_on_a_read_back_said_again_never_books_the_new_one(
    settings: VoiceSettings, rule: FakeRule, consent: list[dict[str, Any]]
) -> None:
    """GP-08: a held yes is of one read-back only; a new reading needs its own yes."""
    io, session, _talker, jobs = _call(settings)

    async def drive() -> None:
        await _summary_plays(io)
        await over(io, 1, YES_TEXT)
        await over(io, 2, REPEAT_TEXT)  # said again: reply 2 is the read-back now
        for index in (0, 1):
            await io.synthesizing(2, index)
            await io.clause_queued(2, index)
            await io.clock.advance(0.5)
            await io.clause_played(2, index, audio_s=2.0)
        await settle()

    asyncio.run(drive())
    assert jobs.runs == [] and _answered(io) == []
    assert session._confirming.active and session._confirming.read_back is not None
    assert session._confirming.read_back.reply_id == 2


@pytest.mark.parametrize("on", [False, True], ids=["off", "on"])
def test_a_bare_yes_over_the_closing_question_books_only_under_the_setting(
    settings: VoiceSettings, rule: FakeRule, consent: list[dict[str, Any]], on: bool
) -> None:
    io, _session, _talker, jobs = _call(settings, on)

    async def drive() -> None:
        await asked(io)
        await clause(io, 0)
        await clause(io, 1, played=False)
        await over(io, 1, BARE_YES)

    asyncio.run(drive())
    if on:
        (run,) = jobs.runs
        assert run.confirmed.turn_id == 1 and _answered(io) == [(1, "yes", "words")]
    else:  # the owner's 2026-11-10 ruling: asked again
        assert jobs.runs == [] and _answered(io) == [(1, "asked_again", "words")]


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
    io, session, talker, jobs = _call(settings, on)

    async def drive() -> None:
        await _summary_plays(io)
        await over(io, 1, KHALAS_YES)
        if on:  # off, it stopped the read-back
            await _summary_ends(io)

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
    io, session, talker, jobs = _call(settings)

    async def drive() -> None:
        await _summary_plays(io)
        await over(io, 1, KHALAS)  # it stops the read-back

    asyncio.run(drive())
    assert jobs.runs == [] and not session._confirming.active
    assert talker.turns[-1].declined == DeclinedAction(action=ACTION, kind="stopped", words=KHALAS)


def _asking(
    settings: VoiceSettings, word: str
) -> tuple[FakeSessionIO, CallSession, FakeTalker, FakeJobs, ScriptedLLM]:
    llm = ScriptedLLM([ScriptedLLM.reply(word)])
    io, session, talker, jobs = _call(settings, agent=ASKS, overlap_model=llm)
    llm.clock = io.clock
    return io, session, talker, jobs, llm


@pytest.mark.parametrize("word", ["yes", "send"])
def test_unplaced_words_over_the_summary_go_to_the_model_and_its_yes_is_held(
    settings: VoiceSettings, rule: FakeRule, consent: list[dict[str, Any]], word: str
) -> None:
    io, session, _talker, jobs, llm = _asking(settings, word)

    async def drive() -> None:
        await _summary_plays(io)
        await over(io, 1, UNPLACED)
        assert jobs.runs == [] and session._confirming.active  # the summary plays on
        await _summary_ends(io)

    asyncio.run(drive())
    assert len(llm.requests) == 1
    (run,) = jobs.runs
    assert (run.confirmed.turn_id, run.confirmed.words) == (1, UNPLACED)
    assert _answered(io) == [(1, "yes", "model")]


def test_the_models_no_on_words_over_the_summary_declines_it_and_reaches_the_talker(
    settings: VoiceSettings, rule: FakeRule, consent: list[dict[str, Any]]
) -> None:
    io, session, talker, jobs, _llm = _asking(settings, "no")

    async def drive() -> None:
        await _summary_plays(io)
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
        await _summary_plays(io)
        await over(io, 1, ECHO)
        await _summary_ends(io)

    asyncio.run(drive())
    assert jobs.runs == [] and _answered(io) == []
    assert session._confirming.active and io.commands.of(StopSpeaking) == []


def test_an_agent_that_does_not_ask_counts_unplaced_words_over_the_summary_for_nothing(
    settings: VoiceSettings, rule: FakeRule, consent: list[dict[str, Any]]
) -> None:
    io, session, _talker, jobs = _call(settings)

    async def drive() -> None:
        await _summary_plays(io)
        await over(io, 1, YES_TEXT)
        await over(io, 2, UNPLACED)
        await _summary_ends(io)

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
    io, _session, talker, jobs = _call(settings)

    async def drive() -> None:
        await _summary_plays(io)
        await io.turn_opened(1)
        await io.clock.advance(0.2)
        await _summary_ends(io)
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

"""Interruptions handed to the talker (voice/session/interrupter.py, talking.py; plan 006, "What
voice-first means here", items 2 and 7): real words over a reply stop it at once, as with no
talker, the stop going out before any model request, and reach the talker whole, the stop word
included (TD-103), beside the cut reply, which the history holds as the caller heard it; a stop
or pause request said whole is a command; a repeat request, over a reply or alone, is the
talker's; a listening sound lets the reply go on; words said while a search runs cancel it, and
the talker starts again with both turns; and a stop or the call's end cancels the talker's work.
The rule is the tests' fake (overlap_support.py's `FakeRule`)."""

from __future__ import annotations

import asyncio

import pytest
from t2_agentic_voice.agent.talker import ReplyDone, SpokenClause, ToolBegan
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.conversation import TalkerTurn
from t2_agentic_voice.core.events import Interrupted
from t2_agentic_voice.domain.words import PRESET_WORDS
from t2_agentic_voice.voice.session.commands import StopSpeaking

from tests.t2_agentic_voice.session_fakes import FakeSessionIO
from tests.t2_agentic_voice.voice.session.overlap_support import (
    LISTENING_TEXT,
    NEW_TEXT,
    REPEAT_TEXT,
    STOP,
    FakeRule,
    overlap_part,
    two_step,
)
from tests.t2_agentic_voice.voice.session.session_support import emitted, greeted, speaks
from tests.t2_agentic_voice.voice.session.talker_support import (
    FakeTalker,
    Step,
    Work,
    answer,
    ended,
    settle,
    talked,
    talker_call,
)

STOP_WORD = PRESET_WORDS["en"].stop[0]
SAID_WITH_STOP = f"my screen keeps saying {STOP_WORD} when I log in"  # TD-103's case, in English


def _two(turn: TalkerTurn) -> list[Step]:
    """A reply of two clauses to turn 0; one clause to any later turn."""
    if turn.turn_id == 0:
        return answer("Open Settings first.", "Then press Reset.")
    return answer("Made-up answer.")


async def _over_the_reply(io: FakeSessionIO, text: str) -> None:
    """Turn 0's reply (reply 1) plays its first clause; the caller says `text` over it (turn
    1), its whole overlap heard, then the turn closes and its own transcript reuses it."""
    await greeted(io)
    await talked(io, 0, "How do I reset my password?")
    await io.synthesizing(1, 0)
    await io.clause_queued(1, 0)
    await io.clock.advance(0.2)
    await io.turn_opened(1)
    await overlap_part(io, 1, text)
    await io.turn_closed(1)
    await io.transcribed(1, text, language="en")
    await settle()


@pytest.fixture
def stop_word(rule: FakeRule) -> FakeRule:
    """The rule, with the preset's stop word and TD-103's sentence a stop."""
    rule.script |= {STOP_WORD: STOP, SAID_WITH_STOP: STOP}
    return rule


def test_real_words_over_a_reply_stop_it_and_reach_the_talker_whole(
    settings: VoiceSettings, rule: FakeRule
) -> None:
    io, _session, talker = talker_call(two_step(settings), _two)
    asyncio.run(_over_the_reply(io, NEW_TEXT))
    stops = [i for i, c in enumerate(io.commands.commands) if isinstance(c, StopSpeaking)]
    assert len(stops) == 1 and stops[0] < talker.began_after[1]  # before any model request
    handed = talker.turns[1]
    assert (handed.words, handed.over_reply, handed.cut_reply) == (NEW_TEXT, 1, 1)
    cut = handed.conversation.replies[-1]  # the reply as the caller heard it
    assert cut.reply_id == 1 and [c.fate for c in cut.clauses] == ["cut", "unplayed"]
    assert [t.turn_id for t in handed.conversation.turns] == [0]
    assert [(s.reply_id, s.text) for s in speaks(io) if s.reply_id >= 2] == [(2, "Made-up answer.")]
    assert [(e.kind, e.reason) for e in emitted(io, Interrupted)] == [("new_words", "enough_words")]


def test_a_stop_word_said_whole_over_a_reply_is_a_command_answered_by_nothing(
    settings: VoiceSettings, stop_word: FakeRule
) -> None:
    io, session, talker = talker_call(two_step(settings), _two)
    asyncio.run(_over_the_reply(io, STOP_WORD))
    assert len(io.commands.of(StopSpeaking)) == 1
    assert [t.turn_id for t in talker.turns] == [0]  # the talker hears no stop
    assert [t.fate for t in session.history.turns()][1] == "command"


def test_a_stop_word_among_other_words_stops_the_reply_and_reaches_the_talker_whole(
    settings: VoiceSettings, stop_word: FakeRule
) -> None:
    """TD-103: a request that holds a stop word stops the agent at once, as the rule says, and
    is answered, its stop word included, never lost."""
    io, _, talker = talker_call(two_step(settings), _two)
    asyncio.run(_over_the_reply(io, SAID_WITH_STOP))
    assert len(io.commands.of(StopSpeaking)) == 1
    assert talker.turns[1].words == SAID_WITH_STOP and talker.turns[1].cut_reply == 1


def test_a_repeat_request_over_a_reply_goes_to_the_talker_not_to_the_fixed_repeat(
    settings: VoiceSettings, rule: FakeRule
) -> None:
    io, session, talker = talker_call(two_step(settings), _two)
    asyncio.run(_over_the_reply(io, REPEAT_TEXT))
    assert len(io.commands.of(StopSpeaking)) == 1
    assert talker.turns[1].words == REPEAT_TEXT
    assert {r.kind for r in (session._playback.reply(i) for i in range(3)) if r} == {
        "greeting",
        "answer",
    }  # no reply the session said again itself


def test_a_repeat_request_said_while_the_agent_is_silent_goes_to_the_talker(
    settings: VoiceSettings,
) -> None:
    io, _, talker = talker_call(two_step(settings))

    async def drive() -> None:
        await greeted(io)
        await talked(io, 0, "What are your hours?")
        for speak in speaks(io, 1):
            await io.clause_queued(1, speak.clause)
            await io.clause_played(1, speak.clause, audio_s=0.4)
        await io.clock.advance(1.0)
        await talked(io, 1, REPEAT_TEXT)

    asyncio.run(drive())
    assert [t.words for t in talker.turns] == ["What are your hours?", REPEAT_TEXT]


def test_a_listening_sound_over_a_reply_lets_it_go_on_unheard_by_the_talker(
    settings: VoiceSettings, rule: FakeRule
) -> None:
    io, session, talker = talker_call(two_step(settings), _two)
    asyncio.run(_over_the_reply(io, LISTENING_TEXT))
    assert io.commands.of(StopSpeaking) == []
    assert [t.turn_id for t in talker.turns] == [0]
    assert not ended(session, 1)  # the reply plays on
    assert [t.fate for t in session.history.turns()][1] == "went_on"


def test_words_said_while_a_search_runs_cancel_it_and_the_talker_starts_again_with_both(
    settings: VoiceSettings,
) -> None:
    def script(turn: TalkerTurn) -> list[Step]:
        if turn.turn_id == 0:
            return [ToolBegan(call_id="t-1", tool="search_help"), Work(3.0), ReplyDone()]
        return answer("Archiving is under Tickets.")

    io, session, talker = talker_call(two_step(settings), script)

    async def drive() -> None:
        await greeted(io)
        await talked(io, 0, "How do I reset my password?")
        await io.clock.advance(1.0)  # the search runs, nothing plays
        assert session._speaker.scope(1).running == 2
        await talked(io, 1, "actually, how do I archive a ticket?")

    asyncio.run(drive())
    assert talker.cancelled == [0]
    assert session._speaker.scope(1).cancelled and session._speaker.scope(1).running == 0
    handed = talker.turns[1]
    assert handed.cut_reply == 1
    assert [(t.turn_id, t.fate) for t in handed.conversation.turns] == [(0, "rolled_back")]
    assert [(e.turn_id, e.kind) for e in emitted(io, Interrupted)] == [(0, "new_words")]
    assert [s.text for s in speaks(io, 2)] == ["Archiving is under Tickets."]


@pytest.mark.parametrize("by", ["stop", "end"])
def test_a_stop_or_the_calls_end_cancels_the_talkers_work(settings: VoiceSettings, by: str) -> None:
    def script(turn: TalkerTurn) -> list[Step]:
        return [SpokenClause(text="Let me check.", language="en"), Work(5.0), ReplyDone()]

    io, session, talker = talker_call(two_step(settings), script)

    async def drive() -> None:
        await greeted(io)
        await talked(io, 0, "Where is my ticket?")
        await io.synthesizing(1, 0)
        await io.clause_queued(1, 0)
        if by == "stop":
            await io.client({"v": 1, "type": "stop"})
        else:
            await io.ending()
        await settle()

    asyncio.run(drive())
    assert talker.cancelled == [0]
    assert session._speaker.scope(1).running == 0
    assert ended(session, 1)


def test_a_talker_is_built_for_the_tests_with_its_scope(settings: VoiceSettings) -> None:
    """The fake talker meets the talker's protocol (mypy checks its shape)."""
    from t2_agentic_voice.agent.talker import Talker

    _, _, talker = talker_call(settings)
    built: Talker = talker
    assert isinstance(built, FakeTalker)

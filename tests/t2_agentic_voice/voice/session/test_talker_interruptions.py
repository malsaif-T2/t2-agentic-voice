"""Interruptions handed to the talker (voice/session/interrupter.py, talking.py; plan 006, "What
voice-first means here", items 2 and 7): real words over a reply stop it at once, as with no
talker, the stop going out before any model request, and reach the talker whole, the stop word
included (TD-103), beside the cut reply, which the history holds as the caller heard it, and
when its own transcript fails the `error` notice is said, as with no talker, and so after a
window's stop word or repeat request whose whole overlap holds new words; a stop or pause
request said whole is a command; a repeat request, over a reply or alone, is the
talker's; a listening sound lets the reply go on; words said while a search runs cancel it, and
the talker starts again with both turns; and a stop or the call's end cancels the talker's work,
the talker's stream closed in the reply's own task (D-060). The rule is the tests' fake
(overlap_support.py's `FakeRule`)."""

from __future__ import annotations

import asyncio

import pytest
from t2_agentic_voice.agent.talker import ReplyDone, SpokenClause, ToolBegan
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.conversation import TalkerTurn
from t2_agentic_voice.core.events import Interrupted
from t2_agentic_voice.domain.words import PRESET_WORDS
from t2_agentic_voice.voice.protocol import Notice
from t2_agentic_voice.voice.session.commands import StopSpeaking

from tests.t2_agentic_voice.session_fakes import FakeSessionIO
from tests.t2_agentic_voice.voice.session.overlap_support import (
    LISTENING_TEXT,
    NEW_TEXT,
    REPEAT_TEXT,
    STOP,
    STOP_TEXT,
    FakeRule,
    echo_playing,
    overlap_part,
    two_step,
)
from tests.t2_agentic_voice.voice.session.session_support import (
    call,
    emitted,
    greeted,
    sent,
    speaks,
)
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


def test_words_begun_in_a_played_replys_tail_reach_the_talker_with_no_cut_reply(
    settings: VoiceSettings, rule: FakeRule
) -> None:
    """Speech that begins within a reply's tail counts as over it, but a reply the caller heard
    whole was cut by nothing: the talker reads `over_reply` and no `cut_reply`."""
    io, session, talker = talker_call(two_step(settings), _two)

    async def drive() -> None:
        await greeted(io)
        await talked(io, 0, "How do I reset my password?")
        for speak in speaks(io, 1):
            await io.clause_queued(1, speak.clause)
            await io.clause_played(1, speak.clause, audio_s=0.4)
        assert ended(session, 1)
        await io.clock.advance(0.1)  # within the reply's tail
        await io.turn_opened(1)
        await overlap_part(io, 1, NEW_TEXT)
        await io.turn_closed(1)
        await io.transcribed(1, NEW_TEXT, language="en")
        await settle()

    asyncio.run(drive())
    assert io.commands.of(StopSpeaking) == []  # nothing was in progress to stop
    handed = talker.turns[1]
    assert (handed.words, handed.over_reply, handed.cut_reply) == (NEW_TEXT, 1, None)
    heard = handed.conversation.replies[-1]
    assert heard.reply_id == 1 and [c.fate for c in heard.clauses] == ["played", "played"]


@pytest.mark.parametrize(
    "window", [None, STOP_TEXT, REPEAT_TEXT], ids=["whole", "window_stop", "window_repeat"]
)
@pytest.mark.parametrize("talker", [True, False], ids=["talker", "echo"])
def test_words_that_stopped_a_reply_whose_own_transcript_failed_hear_the_error_notice(
    settings: VoiceSettings, rule: FakeRule, talker: bool, window: str | None
) -> None:
    """Real words over a reply stop it, or its window's stop word or repeat request stops it
    and the whole overlap holds new words; the caller goes on, and the turn's own request, its
    own, fails: the `error` notice is said, with a talker as with none, never a silent
    command."""
    io = talker_call(two_step(settings), _two)[0] if talker else call(two_step(settings))[0]

    async def drive() -> None:
        if talker:
            await greeted(io)
            await talked(io, 0, "How do I reset my password?")
            await io.synthesizing(1, 0)
            await io.clause_queued(1, 0)
            await io.clock.advance(0.2)
        else:
            await echo_playing(io)
        await io.turn_opened(1)
        if window is not None:
            await overlap_part(io, 1, window, part="window", audio_s=0.75)
        await overlap_part(io, 1, NEW_TEXT)
        await io.clock.advance(0.5)
        await io.turn_closed(1)
        await io.transcribing(1, audio_s=1.6)
        await io.transcribed(1, None, failure="timeout", retryable=True)
        await settle()

    asyncio.run(drive())
    assert len(io.commands.of(StopSpeaking)) == 1
    assert [n.kind for n in sent(io, Notice)] == ["error"]
    error = io.setup.language.notices["error"]
    assert [s.text for s in speaks(io, 2)] == [error]


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


def test_a_reply_stopped_while_its_next_event_waits_closes_the_talkers_stream_in_its_task(
    settings: VoiceSettings,
) -> None:
    """The talker's next event waits for a step of the session's, which stops the reply: the
    talker's stream, paused at that event, is closed in the reply's own task, so the model's
    request ends inside the reply's scope (D-060), not later in the event loop's finalizer."""

    def script(turn: TalkerTurn) -> list[Step]:
        return [
            SpokenClause(text="Let me check.", language="en"),
            Work(1.0),
            SpokenClause(text="Found it.", language="en"),
            ReplyDone(),
        ]

    io, session, talker = talker_call(settings, script)

    async def drive() -> None:
        await greeted(io)
        await talked(io, 0, "Where is my ticket?")
        async with session._lock:  # a step of the session's runs
            await io.clock.advance(1.0)  # the work ends: the next clause waits for the step
            await settle()
            await session._speaker.scope(1).cancel()  # and the step stops the reply
        await io.ending()
        await io.close()

    asyncio.run(drive())
    assert talker.closed_in.get(0) == "talker-0"
    assert [s.text for s in speaks(io, 1)] == ["Let me check."]


def test_a_talker_is_built_for_the_tests_with_its_scope(settings: VoiceSettings) -> None:
    """The fake talker meets the talker's protocol (mypy checks its shape)."""
    from t2_agentic_voice.agent.talker import Talker

    _, _, talker = talker_call(settings)
    built: Talker = talker
    assert isinstance(built, FakeTalker)

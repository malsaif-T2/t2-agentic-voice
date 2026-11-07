"""The reply kept behind the caller's newer turn, step by step on the fake session I/O
(voice/session/talking.py's kept reply; plan 006, Q19; test_talker_kept.py holds `TextCall`'s
cases): a clause due in the newer turn's Smart Turn hold is kept, played after a turn heard as
nothing, or never once the turn's held words have started its own answer; a reply opened while a
newer turn is still open is kept behind it, as is one whose first audio came after that turn's
speech began (no overlap), whose next clause waits; a newer turn whose own request failed hears
the `error` notice, then the kept reply goes on; the client's Stop stops a kept reply, and
nothing it kept plays; and once the call is ending or has ended nothing kept plays, the model
request it kept counted in the call's usage. The talker is the tests' fake (talker_support.py)."""

from __future__ import annotations

import asyncio

import pytest
from t2_agentic_voice.agent.talker import ReplyDone, SpokenClause, ToolBegan
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.conversation import TalkerTurn
from t2_agentic_voice.core.settings.limits import LimitSettings
from t2_agentic_voice.voice.protocol import Notice, State

from tests.t2_agentic_voice.session_fakes import FakeSessionIO
from tests.t2_agentic_voice.voice.session.overlap_support import two_step
from tests.t2_agentic_voice.voice.session.session_support import (
    greeted,
    play,
    report,
    sent,
    speaks,
)
from tests.t2_agentic_voice.voice.session.talker_support import (
    MODEL,
    Step,
    Work,
    answer,
    settle,
    talked,
    talker_call,
)

SEARCHED = "How do I reset my password?"
WORDS = "no, how do I export a ticket"


def _search(turn: TalkerTurn) -> list[Step]:
    """Turn 0's reply searches for 1 s, then says one clause; any later turn's says one."""
    if turn.turn_id == 0:
        return [ToolBegan(call_id="t-1", tool="search_help"), Work(1.0), *answer("Found it.")]
    return answer("Exporting is under Tickets.")


async def _searching(io: FakeSessionIO) -> None:
    """The greeting played, turn 0 asked and its reply's search begun; turn 1 opens 0.3 s
    into the search, while nothing of the reply plays."""
    await greeted(io)
    await talked(io, 0, SEARCHED)
    await io.clock.advance(0.3)
    await io.turn_opened(1)


async def _heard(io: FakeSessionIO, turn_id: int, text: str) -> None:
    """The turn closes, its request goes, and its transcript (`text`, maybe empty) comes."""
    await io.turn_closed(turn_id)
    await io.transcribing(turn_id)
    await io.transcribed(turn_id, text, language="en")
    await settle()


@pytest.mark.parametrize("held", [None, WORDS], ids=["nothing", "words"])
def test_a_clause_due_in_the_newer_turns_hold_is_kept(
    settings: VoiceSettings, held: str | None
) -> None:
    """The search ends while turn 1 is in its hold: the reply's clause is kept. Heard as
    nothing, it plays once the turn is taken; the hold's words start turn 1's own answer, which
    stops the kept reply at the hold's end, so it never plays."""
    io, session, talker = talker_call(two_step(settings), _search)

    async def drive() -> None:
        await _searching(io)
        await io.clock.advance(0.5)
        await io.turn_held(1)
        await io.transcribing(1, part="held")
        await io.clock.advance(0.3)  # the search ends in the hold: the reply's clause is due
        await io.transcribed(1, held, language="en", part="held")
        await settle()
        assert speaks(io, 1) == []
        await io.clock.advance(0.3)
        await io.turn_closed(1)
        await io.transcribed(1, held, language="en")
        await settle()

    asyncio.run(drive())
    fates = [turn.fate for turn in session.history.turns()]
    if held is None:
        assert [s.text for s in speaks(io, 1)] == ["Found it."]
        assert fates == ["pending", "answered"]  # its reply still to play
    else:
        assert speaks(io, 1) == [] and fates[0] == "rolled_back"
        assert [s.text for s in speaks(io, 2)] == ["Exporting is under Tickets."]
        assert talker.turns[1].words == WORDS


@pytest.mark.parametrize("later", ["", WORDS], ids=["nothing", "words"])
def test_a_reply_opened_while_a_newer_turn_is_open_is_kept_behind_it(
    settings: VoiceSettings, later: str
) -> None:
    """Turn 1 opens before turn 0's transcript comes: turn 0's reply, opened after turn 1's
    speech began, is kept behind it; heard as nothing, turn 1 lets it play; heard with words,
    it stops the reply and the talker answers both."""
    io, _, talker = talker_call(two_step(settings))

    async def drive() -> None:
        await greeted(io)
        await io.turn_opened(0)
        await io.clock.advance(1.0)
        await io.turn_closed(0)
        await io.transcribing(0)
        await io.clock.advance(0.2)
        await io.turn_opened(1)  # the caller goes on before turn 0's transcript comes
        await io.clock.advance(0.2)
        await io.transcribed(0, SEARCHED, language="en")
        await settle()
        assert speaks(io, 1) == [] and sent(io, State)[-1].state == "thinking"
        await io.clock.advance(1.0)
        await _heard(io, 1, later)

    asyncio.run(drive())
    if not later:
        assert [s.text for s in speaks(io, 1)] == ["Made-up answer."]
        return
    assert speaks(io, 1) == [] and [s.text for s in speaks(io, 2)] == ["Made-up answer."]
    handed = talker.turns[1]
    assert handed.cut_reply == 1
    assert [(t.turn_id, t.fate) for t in handed.conversation.turns] == [(0, "rolled_back")]


def test_a_reply_whose_first_audio_came_after_the_newer_turns_speech_began_keeps_the_rest(
    settings: VoiceSettings,
) -> None:
    """Turn 1's speech began just before the reply's first audio (no overlap of it, as the
    drop rule and the overlaps read it): the clause asked for plays on, and the next one, given
    while turn 1 is open, is kept until the turn is heard as nothing."""

    def script(turn: TalkerTurn) -> list[Step]:
        return [
            SpokenClause(text="Let me check.", language="en"),
            Work(1.0),
            SpokenClause(text="Found it.", language="en"),
            ReplyDone(),
        ]

    io, _, _ = talker_call(two_step(settings), script)

    async def drive() -> None:
        await greeted(io)
        await talked(io, 0, "Where is my ticket?")
        began = io.clock.now()
        await io.clock.advance(0.1)
        await io.synthesizing(1, 0)
        await io.clause_queued(1, 0)  # its first audio, after turn 1's speech began
        await io.clock.advance(0.2)
        await io.turn_opened(1, speech_at=began)
        await io.clock.advance(1.0)  # the work ends: the next clause is due
        await settle()
        assert [s.text for s in speaks(io, 1)] == ["Let me check."]
        await io.clause_played(1, 0, audio_s=0.4)
        await io.clock.advance(0.5)
        await _heard(io, 1, "")

    asyncio.run(drive())
    assert io.overlaps == set()
    assert [s.text for s in speaks(io, 1)] == ["Let me check.", "Found it."]


def test_a_newer_turn_whose_transcript_failed_hears_the_error_notice_then_the_kept_reply(
    settings: VoiceSettings,
) -> None:
    """Turn 1's own request fails: nothing was heard, so the kept reply goes on, as a failed
    turn always left the reply in progress; the `error` notice is asked for first."""
    io, _, _ = talker_call(two_step(settings), _search)

    async def drive() -> None:
        await _searching(io)
        await io.clock.advance(1.0)  # the search ends: its clause kept
        assert speaks(io, 1) == []
        await io.turn_closed(1)
        await io.transcribing(1)
        await io.transcribed(1, None, failure="timeout", retryable=True)
        await settle()

    asyncio.run(drive())
    assert [n.kind for n in sent(io, Notice)] == ["error"]
    error = io.setup.language.notices["error"]
    assert [(s.reply_id, s.text) for s in speaks(io) if s.reply_id] == [
        (2, error),
        (1, "Found it."),
    ]


def test_the_clients_stop_stops_a_kept_reply_and_nothing_it_kept_plays(
    settings: VoiceSettings,
) -> None:
    io, session, _ = talker_call(two_step(settings), _search)

    async def drive() -> None:
        await _searching(io)
        await io.clock.advance(1.0)  # the search ends: its clause kept
        await io.client({"v": 1, "type": "stop"})
        await io.clock.advance(0.5)
        await _heard(io, 1, "")

    asyncio.run(drive())
    assert speaks(io, 1) == []
    assert [turn.fate for turn in session.history.turns()] == ["rolled_back", "answered"]


@pytest.mark.parametrize("by", ["limit", "caller_left"])
def test_nothing_kept_plays_once_the_call_is_ending_and_its_request_is_counted(
    settings: VoiceSettings, by: str
) -> None:
    """The call reaches its limit while turn 1 is open (its `ended` notice asked for), or the
    caller leaves: nothing the reply kept plays, even once turn 1 is heard as nothing; the model
    request it kept went, so the call's usage counts it."""
    limits = LimitSettings(max_call_s=4.0, idle_s=60.0)
    io, _, _ = talker_call(two_step(settings).model_copy(update={"limits": limits}), _search)

    async def drive() -> None:
        await _searching(io)
        await io.clock.advance(1.0)  # the search ends: its clause kept
        assert speaks(io, 1) == []
        if by == "limit":
            await io.clock.advance(1.0)  # the limit, 4 s into the call: its notice asked for
            assert [n.kind for n in sent(io, Notice)] == ["ended"]
            await _heard(io, 1, "")
            await play(io, 2)  # the notice plays, and the call hangs up
        else:
            await io.ending()
        await io.close()

    asyncio.run(drive())
    assert speaks(io, 1) == []
    assert {u.model: u.requests for u in report(io).usage}.get(MODEL) == 1

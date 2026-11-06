"""The early start (voice/session/talking.py, io.py's early start; plan 006, Q2), on the fake
clock: a turn's `held` transcript, sent when Smart Turn called it complete, starts the talker at
once, and nothing plays before the hold ends with the turn's `TurnClosed`; the turn's own
transcript, reusing it, starts nothing more; speech that resumes in the hold cancels that work,
and the turn, joined, reaches the talker as one; a stop request said whole starts nothing; an
overlap's turn and a call with no talker are as they were. What the hold kept plays event by
event, one that fails logged and the rest still played, the reply closed; and nothing it kept
plays after a client's stop in the hold, which cancels its work, or over the `ended` notice."""

from __future__ import annotations

import asyncio

from t2_agentic_voice.agent.talker import ProgressDue, ReplyDone, SpokenClause
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.conversation import TalkerTurn
from t2_agentic_voice.core.settings.limits import LimitSettings
from t2_agentic_voice.core.settings.tts import LanguageTag
from t2_agentic_voice.domain.ports.text_to_speech import AudioChunk
from t2_agentic_voice.domain.words import PRESET_WORDS
from t2_agentic_voice.voice.protocol import Notice
from t2_agentic_voice.voice.session.commands import Speak

from tests.t2_agentic_voice.fakes import FakePhrases
from tests.t2_agentic_voice.session_fakes import FakeSessionIO
from tests.t2_agentic_voice.voice.session.overlap_support import two_step
from tests.t2_agentic_voice.voice.session.session_support import (
    call,
    greeted,
    play,
    sent,
    speaks,
)
from tests.t2_agentic_voice.voice.session.talker_support import (
    PROGRESS,
    Step,
    Work,
    answer,
    ended,
    phrases,
    settle,
    talker_call,
)

HOLD_S = 0.6
FIRST, REST = "I want to reset", "my password please"


async def _held(io: FakeSessionIO, turn_id: int, text: str) -> None:
    """The caller's turn opens, Smart Turn calls it complete and its hold begins, and its
    `held` request goes and is heard, 0.3 s into the hold."""
    await io.turn_opened(turn_id)
    await io.clock.advance(1.0)
    await io.turn_held(turn_id)
    await io.transcribing(turn_id, part="held")
    await io.clock.advance(0.3)
    await io.transcribed(turn_id, text, language="en", part="held")
    await settle()


async def _closed(io: FakeSessionIO, turn_id: int, text: str, *, reused: bool = True) -> None:
    """The hold ends: the turn closes, and its own transcript comes, reusing the `held` one
    when no speech followed it, else its own request's."""
    await io.clock.advance(HOLD_S - 0.3)
    await io.turn_closed(turn_id)
    if not reused:
        await io.transcribing(turn_id)
    await io.transcribed(turn_id, text, language="en")
    await settle()


def test_the_talker_starts_at_complete_and_nothing_plays_before_the_hold_ends(
    settings: VoiceSettings,
) -> None:
    io, session, talker = talker_call(two_step(settings))

    async def drive() -> None:
        await greeted(io)
        await _held(io, 0, FIRST)
        assert [t.words for t in talker.turns] == [FIRST]  # started in the hold
        assert speaks(io, 1) == [] and session._playback.reply(1) is None  # nothing asked
        await _closed(io, 0, FIRST)
        assert [s.text for s in speaks(io, 1)] == ["Made-up answer."]
        await play(io, 1)
        await io.ending()
        await io.close()

    asyncio.run(drive())
    assert len(talker.turns) == 1  # the turn's own transcript started nothing more
    assert [t.fate for t in session.history.turns()] == ["answered"]
    (closed,) = [e for e in io.events if type(e).__name__ == "TurnClosed"]
    first = next(c for c in io.commands.commands if isinstance(c, Speak) and c.reply_id == 1)
    assert io.commands.commands.index(first) > 0 and closed.at >= 101.0


def test_speech_resumed_in_the_hold_cancels_the_early_work_and_joins_the_turn(
    settings: VoiceSettings,
) -> None:
    def script(turn: TalkerTurn) -> list[Step]:
        return [Work(1.0), *answer("Made-up answer.")]

    io, session, talker = talker_call(two_step(settings), script)

    async def drive() -> None:
        await greeted(io)
        await _held(io, 0, FIRST)
        await io.hold_resumed(0)
        await settle()
        assert talker.cancelled == [0]
        await io.clock.advance(1.5)  # the caller goes on; the early work does nothing more
        assert speaks(io, 1) == []
        await io.turn_held(0)
        await _closed(io, 0, f"{FIRST} {REST}", reused=False)
        await io.clock.advance(1.0)
        await settle()

    asyncio.run(drive())
    assert [t.words for t in talker.turns] == [FIRST, f"{FIRST} {REST}"]  # one turn, whole
    assert [s.text for s in speaks(io, 1)] == ["Made-up answer."]
    assert session._playback.reply(2) is None  # one reply for the turn


def test_a_stop_request_said_whole_starts_nothing_early(settings: VoiceSettings) -> None:
    io, _, talker = talker_call(two_step(settings))

    async def drive() -> None:
        await greeted(io)
        await _held(io, 0, PRESET_WORDS["en"].stop[0])

    asyncio.run(drive())
    assert talker.turns == []


def test_a_call_with_no_talker_starts_nothing_in_the_hold(settings: VoiceSettings) -> None:
    """The echo answers at the turn's own transcript, as it did."""
    io, _ = call(two_step(settings))

    async def drive() -> None:
        await greeted(io)
        await _held(io, 0, FIRST)
        assert speaks(io, 1) == []
        await _closed(io, 0, FIRST)

    asyncio.run(drive())
    assert speaks(io, 1)[-1].text == FIRST


class _UnreadablePhrases(FakePhrases):
    """The phrase audio, its English progress line unreadable (as a file the cache cannot
    read)."""

    def audio(self, text: str, *, language: LanguageTag) -> AudioChunk:
        if text == PROGRESS["en"]:
            raise OSError("made-up unreadable phrase")
        return super().audio(text, language=language)


def test_a_held_event_that_fails_is_logged_and_the_rest_plays_and_the_reply_closes(
    settings: VoiceSettings, step_failures: None
) -> None:
    def script(turn: TalkerTurn) -> list[Step]:
        return [
            ProgressDue(tool="search_help", key="looking", language="en"),
            SpokenClause(text="Found it.", language="en"),
            ReplyDone(),
        ]

    unreadable = _UnreadablePhrases(phrases().declared)
    io, session, _ = talker_call(two_step(settings), script, phrases=unreadable)

    async def drive() -> None:
        await greeted(io)
        await _held(io, 0, FIRST)
        await _closed(io, 0, FIRST)
        assert [s.text for s in speaks(io, 1)] == ["Found it."]
        await play(io, 1)
        assert ended(session, 1)  # closed, not left open and thinking
        await io.ending()
        await io.close()

    asyncio.run(drive())
    assert [t.fate for t in session.history.turns()] == ["answered"]


def test_a_client_stop_in_the_hold_cancels_the_early_work_and_nothing_answers_the_turn(
    settings: VoiceSettings,
) -> None:
    def script(turn: TalkerTurn) -> list[Step]:
        return [Work(1.0), *answer("Made-up answer.")]

    io, session, talker = talker_call(two_step(settings), script)

    async def drive() -> None:
        await greeted(io)
        await _held(io, 0, FIRST)
        await io.client({"v": 1, "type": "stop"})
        await settle()
        assert talker.cancelled == [0]  # the work it began, cancelled at the stop
        await _closed(io, 0, FIRST)
        await io.clock.advance(1.5)
        await settle()
        await io.ending()
        await io.close()

    asyncio.run(drive())
    assert speaks(io, 1) == [] and session._playback.reply(1) is None
    assert len(talker.turns) == 1  # the turn's own transcript started nothing more
    assert [t.fate for t in session.history.turns()] == ["rolled_back"]


def test_a_held_reply_never_plays_over_the_ended_notice(settings: VoiceSettings) -> None:
    limits = LimitSettings(max_call_s=5.0, idle_s=60.0)
    io, _, _ = talker_call(two_step(settings).model_copy(update={"limits": limits}))

    async def drive() -> None:
        await greeted(io)
        await _held(io, 0, FIRST)
        await io.clock.advance(limits.max_call_s)  # the limit, in the hold: its notice asked
        assert [n.kind for n in sent(io, Notice)] == ["ended"]
        await _closed(io, 0, FIRST)
        await play(io, 1)  # the notice plays, and the call hangs up
        await io.close()

    asyncio.run(drive())
    assert [s.reply_id for s in speaks(io)] == [0, 1]  # the greeting and the notice alone

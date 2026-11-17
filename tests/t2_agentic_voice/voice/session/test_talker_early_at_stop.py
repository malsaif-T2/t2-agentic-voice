"""The session's side of plan 010's 2.2 on the fake session I/O: under `turns.early_at_stop` a
turn's `held` request goes at the detector's stop, so its `Transcribing` comes before `TurnHeld`,
and one dropped at a pause Smart Turn called unfinished names nothing of the turn: the report
names the language of the request its hold kept, or of the turn's own when no hold came
(turn_book.py). Under `session.early_over_reply` a turn held while a reply to an earlier turn is
still in progress starts the talker early too: that reply is stopped first, as the turn's answer
would stop it, so the talker reads it as cut and its turn as rolled back (TD-117), nothing plays
before the hold ends, and the turn's own transcript starts nothing more; speech resumed in the
hold drops that early work and the turn is answered once, whole; while the call is confirming,
or with the setting off, the turn starts nothing early, as before."""

from __future__ import annotations

import asyncio

import pytest
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.events import Interrupted, LanguageBy
from t2_agentic_voice.core.settings.session import SessionSettings
from t2_agentic_voice.voice.session.read_back import Confirming
from t2_agentic_voice.voice.session.session_events import Transcribing
from t2_agentic_voice.voice.session.yes_turns import YesTurns

from tests.t2_agentic_voice.session_fakes import FakeSessionIO
from tests.t2_agentic_voice.voice.session.overlap_support import two_step
from tests.t2_agentic_voice.voice.session.session_support import emitted, greeted, speaks
from tests.t2_agentic_voice.voice.session.talker_support import settle, talker_call
from tests.t2_agentic_voice.voice.session.test_talker_kept_steps import (
    SEARCHED,
    WORDS,
    _search,
    _searching,
)


async def _sent(io: FakeSessionIO, turn_id: int, part: str, language: str, by: LanguageBy) -> None:
    """A request of the turn's `part` goes now, naming `language`, chosen `by`."""
    at = io.clock.now()
    held = part == "held"
    event = Transcribing(
        turn_id=turn_id,
        at=at,
        audio_s=2.0,
        part="held" if held else "turn",
        language=language,
        language_by=by,
    )
    await io._hand(event)


@pytest.mark.parametrize("held", [True, False], ids=["a hold kept one", "no hold came"])
def test_a_request_dropped_at_an_unfinished_pause_names_nothing_of_the_turn(
    settings: VoiceSettings, held: bool
) -> None:
    io, session, _ = talker_call(two_step(settings))

    async def drive() -> None:
        await greeted(io)
        await io.turn_opened(0)
        await io.clock.advance(1.0)
        await _sent(io, 0, "held", "ar", "late")  # at the stop; Smart Turn then says unfinished
        await io.clock.advance(1.0)
        if held:
            await _sent(io, 0, "held", "en", "classified")  # at the next stop
            await io.turn_held(0)
            await io.transcribed(0, "please check my ticket", language="en", part="held")
            await io.clock.advance(0.6)
            await io.turn_closed(0)
        else:  # the fallback ends the turn: its own request goes
            await io.turn_closed(0)
            await _sent(io, 0, "turn", "en", "classified")
        await io.transcribed(0, "please check my ticket", language="en")
        await settle()

    asyncio.run(drive())
    turn = session._turns.turn(0)
    assert (turn.language, turn.language_by) == ("en", "classified")


def _over_reply(settings: VoiceSettings, *, on: bool = True) -> VoiceSettings:
    group = SessionSettings(early_over_reply=on)
    return two_step(settings).model_copy(update={"session": group})


async def _held(io: FakeSessionIO, text: str) -> None:
    """Turn 1's hold begins 0.5 s into turn 0's search, and its held words come 0.3 s later."""
    await io.clock.advance(0.5)
    await io.turn_held(1)
    await io.transcribing(1, part="held")
    await io.clock.advance(0.3)
    await io.transcribed(1, text, language="en", part="held")
    await settle()


async def _closed(io: FakeSessionIO, text: str) -> None:
    await io.clock.advance(0.3)
    await io.turn_closed(1)
    await io.transcribed(1, text, language="en")
    await settle()


def test_a_turn_held_over_a_reply_in_progress_starts_early_once_that_reply_is_stopped(
    settings: VoiceSettings,
) -> None:
    io, _, talker = talker_call(_over_reply(settings), _search)
    early: list[list[int]] = []

    async def drive() -> None:
        await _searching(io)
        await _held(io, WORDS)
        early.append([t.turn_id for t in talker.turns])
        assert speaks(io, 2) == []  # nothing asked of the voice before the hold ends
        await _closed(io, WORDS)

    asyncio.run(drive())
    assert early == [[0, 1]]  # started on the held words, in the hold
    handed = talker.turns[1]
    assert (handed.words, handed.cut_reply) == (WORDS, 1)
    assert [(t.turn_id, t.fate) for t in handed.conversation.turns] == [(0, "rolled_back")]
    assert [s.text for s in speaks(io, 2)] == ["Exporting is under Tickets."]
    assert len(talker.turns) == 2  # the turn's own transcript started nothing more
    assert [e.turn_id for e in emitted(io, Interrupted)] == [0]


def test_speech_resumed_after_an_early_start_over_a_reply_answers_the_turn_once(
    settings: VoiceSettings,
) -> None:
    io, _, talker = talker_call(_over_reply(settings), _search)
    whole = f"{WORDS} please"

    async def drive() -> None:
        await _searching(io)
        await _held(io, WORDS)
        await io.hold_resumed(1)  # the early work dropped; turn 0's reply stays stopped
        await settle()
        await io.clock.advance(0.5)
        await io.turn_held(1)
        await io.transcribing(1, part="held")
        await io.transcribed(1, whole, language="en", part="held")
        await settle()
        await _closed(io, whole)

    asyncio.run(drive())
    assert [t.words for t in talker.turns] == [SEARCHED, WORDS, whole]
    assert [s.text for s in speaks(io)][-1] == "Exporting is under Tickets."
    assert {s.reply_id for s in speaks(io)} == {0, 2}  # the dropped start opened no reply
    assert talker.turns[2].cut_reply == 1
    assert [e.turn_id for e in emitted(io, Interrupted)] == [0]


@pytest.mark.parametrize("why", ["off", "confirming"])
def test_off_or_while_confirming_a_turn_over_a_reply_starts_nothing_early(
    settings: VoiceSettings, why: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    io, _, talker = talker_call(_over_reply(settings, on=why != "off"), _search)
    if why == "confirming":  # a read-back current, the turn not the yes rule's
        monkeypatch.setattr(Confirming, "active", property(lambda self: True))
        monkeypatch.setattr(YesTurns, "takes", lambda self, heard, turn: False)
    early: list[list[int]] = []

    async def drive() -> None:
        await _searching(io)
        await _held(io, WORDS)
        early.append([t.turn_id for t in talker.turns])

    asyncio.run(drive())
    assert early == [[0]]

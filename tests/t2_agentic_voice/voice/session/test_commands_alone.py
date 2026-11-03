"""A turn said while the agent was silent (voice/session/interrupter.py's `alone`; plan 005's
Track B review), with Track A's rule and words, not a fake: under `interruptions.mode =
"two_step"` a repeat request says the last reply the caller heard again and a stop or pause
request is never said back, each a command, while a sentence holding one of their words is
answered; under `drop` every one is said back, as plan 003's echo says it. The rehearsal's stop
and repeat steps (docs/project/DESCRIPTION.md, steps 1 and 2) run whole. A lone word is built
from the lists, so no test writes an item's text."""

from __future__ import annotations

import asyncio

import pytest
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.events import Interrupted
from t2_agentic_voice.domain.interruption_words import NOISY_SPELLINGS
from t2_agentic_voice.domain.words import PRESET_WORDS
from t2_agentic_voice.voice.protocol import Unduck
from t2_agentic_voice.voice.session.commands import Send, StopSpeaking
from t2_agentic_voice.voice.session.history import HeardTurn

from tests.t2_agentic_voice.session_fakes import FakeSessionIO
from tests.t2_agentic_voice.voice.session.overlap_support import overlap_part, two_step
from tests.t2_agentic_voice.voice.session.session_support import (
    GAP_S,
    HEARD,
    HEARD_AR,
    call,
    captions,
    emitted,
    greeted,
    play,
    speaks,
    turn,
)

ENGLISH, ARABIC = PRESET_WORDS["en"], PRESET_WORDS["ar"]
# Commands said whole, each built from the lists: a stop word twice, a pause word with a
# listening sound, a spelling only Whisper writes for the stop word with a polite word.
STOPS = [
    f"{ENGLISH.stop[0]} {ENGLISH.stop[0]}",
    f"{ENGLISH.backchannel[0]}, {ENGLISH.wait[0]}",
    f"{sorted(s for s in NOISY_SPELLINGS if s.isascii())[0]}, please",
]
REPEAT = f"please, {ENGLISH.repeat[1]}"  # a repeat request with a polite word
SENTENCE = f"the printer will not {ENGLISH.stop[0]} beeping"


async def _answered(io: FakeSessionIO) -> None:
    """The call is greeted, and the caller's turn 0 is said back whole (reply 1)."""
    await greeted(io)
    await turn(io, 0, HEARD)
    await play(io, 1)
    await io.clock.advance(GAP_S)


def test_a_repeat_request_said_while_silent_says_the_last_reply_again(
    settings: VoiceSettings,
) -> None:
    io, session = call(two_step(settings))

    async def drive() -> None:
        await _answered(io)
        await turn(io, 1, REPEAT)
        await play(io, 2)
        await io.ending()
        await io.close()

    asyncio.run(drive())
    first, again = speaks(io, 1), speaks(io, 2)
    assert [(s.text, s.audio is not None) for s in again] == [
        (s.text, s.audio is not None) for s in first
    ]
    assert {s.turn_id for s in again} == {1}
    assert session.history.turns()[1] == HeardTurn(
        turn_id=1, words=REPEAT, fate="command", reply_id=2
    )
    assert [c.turn_id for c in captions(io, "caller")] == [0]  # a command is not shown back
    assert emitted(io, Interrupted) == [] and io.overlaps == set()


@pytest.mark.parametrize("text", STOPS, ids=["stop-twice", "wait", "noisy"])
def test_a_stop_or_pause_request_said_while_silent_is_never_said_back(
    settings: VoiceSettings, text: str
) -> None:
    io, session = call(two_step(settings))

    async def drive() -> None:
        await _answered(io)
        await turn(io, 1, text)
        await io.ending()
        await io.close()

    asyncio.run(drive())
    assert speaks(io, 2) == [] and [c.turn_id for c in captions(io, "caller")] == [0]
    assert session.history.turns()[1] == HeardTurn(turn_id=1, words=text, fate="command")


def test_a_sentence_holding_a_stop_word_is_answered(settings: VoiceSettings) -> None:
    io, session = call(two_step(settings))

    async def drive() -> None:
        await _answered(io)
        await turn(io, 1, SENTENCE)
        await play(io, 2)
        await io.ending()
        await io.close()

    asyncio.run(drive())
    assert {s.turn_id for s in speaks(io, 2)} == {1}
    assert session.history.turns()[1].fate == "answered"


@pytest.mark.parametrize("text", [*STOPS, REPEAT], ids=["stop-twice", "wait", "noisy", "repeat"])
def test_under_drop_every_whole_command_is_said_back(settings: VoiceSettings, text: str) -> None:
    io, session = call(settings)

    async def drive() -> None:
        await _answered(io)
        await turn(io, 1, text)
        await play(io, 2)
        await io.ending()
        await io.close()

    asyncio.run(drive())
    assert {s.turn_id for s in speaks(io, 2)} == {1}
    assert [c.turn_id for c in captions(io, "caller")] == [0, 1]
    assert session.history.turns()[1].fate == "answered"


def test_the_rehearsals_stop_then_repeat_requests_in_an_arabic_call(
    settings: VoiceSettings,
) -> None:
    """Step 1: the stop word over an answer stops it at once, never said back. Step 2: a repeat
    request said after it, then another with a question mark, each says the last reply again,
    the one cut first, then the one said again."""
    io, session = call(two_step(settings), language="ar-SA")
    stop, short, polite = ARABIC.stop[0], ARABIC.repeat[1], f"{ARABIC.repeat[13]}؟"

    async def drive() -> None:
        await greeted(io)
        await turn(io, 0, HEARD_AR, language="ar")
        await io.clause_queued(1, 0)  # the answer plays
        await io.clock.advance(0.2)
        await io.turn_opened(1)
        await overlap_part(io, 1, stop, part="window", audio_s=0.75)
        await overlap_part(io, 1, stop)
        await io.turn_closed(1)
        await io.transcribed(1, stop, language="ar")
        await io.clock.advance(GAP_S)
        await turn(io, 2, short, language="ar")
        await play(io, 2)
        await io.clock.advance(GAP_S)
        await turn(io, 3, polite, language="ar")
        await play(io, 3)
        await io.ending()
        await io.close()

    asyncio.run(drive())
    stopped = io.commands.commands.index(StopSpeaking(reply_id=1))
    assert io.commands.commands[stopped + 1] == Send(message=Unduck())
    (interrupted,) = emitted(io, Interrupted)
    assert (interrupted.kind, interrupted.reason) == ("stop", "stop_word")
    answer = [s.text for s in speaks(io, 1)]
    assert [s.text for s in speaks(io, 2)] == answer == [s.text for s in speaks(io, 3)]
    assert [(t.fate, t.reply_id) for t in session.history.turns()] == [
        ("rolled_back", 1),
        ("command", None),
        ("command", 2),
        ("command", 3),
    ]
    assert [c.turn_id for c in captions(io, "caller")] == [0]

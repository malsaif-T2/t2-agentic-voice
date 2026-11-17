"""Which progress line a call says, and the beat after it (voice/session/talker_play.py and
open_reply.py; plan 010's 1.15): a line of several wordings is said in one of them, never the one
the call said last for its key; the silence after it is `session.progress_beat_ms` from the end
of its speech, its take's own silence after the speech cut (echo.py's `beat_after`), and unset,
the take as it is, then the beat of 400 ms around every fixed line (`BEAT_S`, D-077). The fake
talker is the tests' own (talker_support.py)."""

from __future__ import annotations

import asyncio
from itertools import pairwise

from t2_agentic_voice.agent.talker import ProgressDue
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.conversation import TalkerTurn
from t2_agentic_voice.core.settings.session import SessionSettings
from t2_agentic_voice.domain.declaration import Language, VoiceAgent
from t2_agentic_voice.domain.ports.text_to_speech import AudioChunk
from t2_agentic_voice.voice.session.commands import Speak
from t2_agentic_voice.voice.session.echo import BEAT_S, FALL_S, beat_after

from tests.t2_agentic_voice.fakes import tone
from tests.t2_agentic_voice.session_fakes import FakeSessionIO
from tests.t2_agentic_voice.voice.session.session_support import greeted, play, speaks
from tests.t2_agentic_voice.voice.session.talker_support import (
    Step,
    Work,
    answer,
    settle,
    talked,
    talker_call,
)

WORDINGS = ("Let me check.", "Checking now.")
AGENT = VoiceAgent(
    name="talker-test",
    languages=[Language.english(greeting="Welcome to the line", progress={"looking": WORDINGS})],
    instructions="Answer briefly.",
)
LINE = ProgressDue(tool="search_help", key="looking", language="en")
FOUND = "Found it."


def _script(turn: TalkerTurn) -> list[Step]:
    return [LINE, Work(0.5), *answer(FOUND)]


async def _searched(io: FakeSessionIO, turn_id: int) -> Speak:
    """The caller asks again; the progress line said at once, the answer after, both played."""
    await talked(io, turn_id, f"Where is ticket {turn_id}?")
    await io.clock.advance(0.5)
    await settle()
    line, found = speaks(io, turn_id + 1)
    assert found.text == FOUND
    await play(io, turn_id + 1)
    return line


def _lines(settings: VoiceSettings, searches: int) -> tuple[FakeSessionIO, list[Speak]]:
    io, _, _ = talker_call(settings, _script, agent=AGENT)
    said: list[Speak] = []

    async def drive() -> None:
        await greeted(io)
        for turn_id in range(searches):
            said.append(await _searched(io, turn_id))
        await io.ending()
        await io.close()

    asyncio.run(drive())
    return io, said


def test_a_line_of_two_wordings_is_said_in_each_by_turns(settings: VoiceSettings) -> None:
    _, said = _lines(settings, 4)
    texts = [line.text for line in said]
    assert set(texts) == set(WORDINGS)
    assert all(this != after for this, after in pairwise(texts))


def _beat_s(io: FakeSessionIO, line: Speak) -> float:
    phrase = io.setup.phrases.audio(line.text, language="en")
    assert line.audio is not None
    return (len(line.audio.pcm16) - len(phrase.pcm16)) / 2 / phrase.sample_rate


def test_the_beat_after_a_line_is_the_fixed_lines_beat_by_default(settings: VoiceSettings) -> None:
    """A characterization of the default (GP-18): the beat D-077 puts around every fixed line,
    after the take as it is."""
    assert settings.session.progress_beat_ms is None
    io, [line] = _lines(settings, 1)
    assert _beat_s(io, line) == BEAT_S


def test_the_beat_after_a_line_is_the_settings(settings: VoiceSettings) -> None:
    shorter = settings.model_copy(update={"session": SessionSettings(progress_beat_ms=100)})
    io, [line] = _lines(shorter, 1)
    assert _beat_s(io, line) == 0.1


RATE = 24_000


def _take(sound_s: float, silence_s: float) -> AudioChunk:
    return AudioChunk(
        pcm16=tone(sound_s, RATE) + bytes(2 * round(silence_s * RATE)), sample_rate=RATE
    )


def _length_s(audio: AudioChunk) -> float:
    return len(audio.pcm16) / 2 / RATE


def test_a_beat_counted_from_the_speech_cuts_the_takes_own_silence_after_it() -> None:
    """The take's silence after its last sound becomes the beat, its first `FALL_S` kept."""
    found = beat_after(_take(0.5, 0.3), 0.1)
    assert abs(_length_s(found) - 0.6) <= 0.01
    assert found.pcm16[: len(tone(0.5, RATE))] == tone(0.5, RATE)
    assert set(found.pcm16[-2 * round((0.1 - FALL_S) * RATE) :]) == {0}


def test_a_take_with_no_sound_gets_the_beat_after_it_and_a_short_one_is_kept() -> None:
    assert _length_s(beat_after(_take(0.0, 0.2), 0.1)) == 0.3
    assert abs(_length_s(beat_after(_take(0.5, 0.0), 0.1)) - 0.6) <= 0.01

"""What follows a window's repeat request, and a decision that fails (voice/session/interrupter.py,
overlap.py; plan 005's Track B review), the rule a fake (conftest.py's `rule`): a repeat request
the window heard stops the reply and brings the voice back at once, but says the last reply again
only once the whole overlap's transcript has come, so never while the caller still speaks, and
answers new words the whole overlap holds instead; a rule that raises decides its overlap as going
on, logged with no text, so the voice comes back and no later overlap's `unduck` waits on it."""

from __future__ import annotations

import asyncio
import logging

import pytest
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.events import Interrupted
from t2_agentic_voice.voice.protocol import Duck, Unduck
from t2_agentic_voice.voice.session.commands import HearOverlap, Send, StopSpeaking

from tests.t2_agentic_voice.session_fakes import FakeSessionIO
from tests.t2_agentic_voice.voice.session.overlap_support import (
    FAILING_TEXT,
    LISTENING_TEXT,
    NEW_TEXT,
    REPEAT_TEXT,
    FakeRule,
    echo_playing,
    overlap_part,
    two_step,
)
from tests.t2_agentic_voice.voice.session.session_support import (
    call,
    captions,
    emitted,
    play,
    sent,
    speaks,
)


async def _window_asked_again(io: FakeSessionIO) -> None:
    """Over the echo, the caller's turn 1 opens and its window holds a repeat request: the
    reply stops and the voice comes back at once, nothing said again yet."""
    await echo_playing(io)
    await io.turn_opened(1)
    await overlap_part(io, 1, REPEAT_TEXT, part="window", audio_s=0.75)
    window = HearOverlap(turn_id=1, window_ms=750)
    given = io.commands.commands
    assert given[given.index(window) + 1 :][:2] == [
        StopSpeaking(reply_id=1),
        Send(message=Unduck()),
    ]
    assert speaks(io, 2) == []


@pytest.mark.parametrize(
    "whole", [REPEAT_TEXT, LISTENING_TEXT, ""], ids=["repeat", "listening", "nothing"]
)
def test_a_windows_repeat_request_says_the_reply_again_once_the_whole_overlap_came(
    settings: VoiceSettings, rule: FakeRule, whole: str
) -> None:
    """Whatever the whole overlap holds but new words (a repeat request, a listening sound, or
    nothing), the reply is said again once it comes, and the turn is a command."""
    io, session = call(two_step(settings))

    async def drive() -> None:
        await _window_asked_again(io)
        await io.clock.advance(0.5)  # the caller still speaks
        assert speaks(io, 2) == []
        await overlap_part(io, 1, whole)
        assert {s.turn_id for s in speaks(io, 2)} == {1}
        await play(io, 2)
        await io.turn_closed(1)
        await io.transcribed(1, whole, language="en")
        await io.ending()
        await io.close()

    asyncio.run(drive())
    assert rule.texts == [REPEAT_TEXT, whole]  # the whole overlap judged still
    (interrupted,) = emitted(io, Interrupted)
    assert (interrupted.kind, interrupted.reason) == ("new_words", "repeat_word")
    assert len(sent(io, Unduck)) == 1
    assert [(t.fate, t.reply_id) for t in session.history.turns()][1] == ("command", 2)


def test_a_repeat_request_the_whole_overlap_heard_says_the_reply_again_at_once(
    settings: VoiceSettings, rule: FakeRule
) -> None:
    """The window went on; the whole overlap, its speech over, decides: said again at once."""
    io, session = call(two_step(settings))

    async def drive() -> None:
        await echo_playing(io)
        await io.turn_opened(1)
        await overlap_part(io, 1, LISTENING_TEXT, part="window", audio_s=0.75)
        await overlap_part(io, 1, REPEAT_TEXT)
        assert {s.turn_id for s in speaks(io, 2)} == {1}
        await play(io, 2)
        await io.turn_closed(1)
        await io.transcribed(1, REPEAT_TEXT, language="en")
        await io.ending()
        await io.close()

    asyncio.run(drive())
    assert io.commands.of(StopSpeaking) == [StopSpeaking(reply_id=1)]
    assert [(t.fate, t.reply_id) for t in session.history.turns()][1] == ("command", 2)


def test_new_words_in_the_whole_overlap_are_answered_instead_of_the_repeat(
    settings: VoiceSettings, rule: FakeRule
) -> None:
    io, session = call(two_step(settings))

    async def drive() -> None:
        await _window_asked_again(io)
        await overlap_part(io, 1, NEW_TEXT)
        assert speaks(io, 2) == []  # answered from the turn's own transcript
        await io.turn_closed(1)
        await io.transcribed(1, NEW_TEXT, language="en")
        await play(io, 2)
        await io.ending()
        await io.close()

    asyncio.run(drive())
    assert speaks(io, 2)[-1].text == NEW_TEXT and {s.turn_id for s in speaks(io, 2)} == {1}
    assert [c.turn_id for c in captions(io, "caller")] == [0, 1]
    assert len(emitted(io, Interrupted)) == 1 and len(sent(io, Unduck)) == 1
    assert session.history.turns()[1].fate == "answered"


def test_the_turns_own_transcript_waits_for_the_whole_overlap_after_a_windows_repeat(
    settings: VoiceSettings, rule: FakeRule
) -> None:
    """The turn's own transcript comes first: held, then taken once the whole overlap has come
    and the reply was said again."""
    io, session = call(two_step(settings))

    async def drive() -> None:
        await _window_asked_again(io)
        await io.transcribing(1, audio_s=1.2, part="overlap")
        await io.turn_closed(1)
        await io.transcribing(1, audio_s=1.4)
        await io.transcribed(1, REPEAT_TEXT, language="en")
        assert speaks(io, 2) == []
        await io.transcribed(1, REPEAT_TEXT, language="en", part="overlap")
        await play(io, 2)
        await io.ending()
        await io.close()

    asyncio.run(drive())
    assert {s.turn_id for s in speaks(io, 2)} == {1}
    assert session.history.turns()[1].fate == "command"


def test_with_no_whole_overlap_the_turns_own_transcript_says_the_reply_again(
    settings: VoiceSettings, rule: FakeRule
) -> None:
    io, session = call(two_step(settings))

    async def drive() -> None:
        await _window_asked_again(io)
        await io.turn_closed(1)
        await io.transcribing(1, audio_s=1.4)
        await io.transcribed(1, REPEAT_TEXT, language="en")
        await play(io, 2)
        await io.ending()
        await io.close()

    asyncio.run(drive())
    assert {s.turn_id for s in speaks(io, 2)} == {1}
    assert session.history.turns()[1].fate == "command"


def test_a_rule_that_raises_lets_the_reply_go_on_and_withholds_no_unduck(
    settings: VoiceSettings, rule: FakeRule, caplog: pytest.LogCaptureFixture
) -> None:
    """Two overlaps over one reply, both undecided; the rule raises on the first one's window,
    which decides it as going on (no `unduck` while the second is undecided), and the second's
    verdict brings both `unduck`s, one for each `duck`. The failure is logged by its kind, with
    no text."""
    io, session = call(two_step(settings))

    async def drive() -> None:
        await echo_playing(io)
        await io.turn_opened(1)
        await io.turn_opened(2)
        await overlap_part(io, 1, FAILING_TEXT, part="window", audio_s=0.75)
        assert sent(io, Unduck) == [] and session.history.turns()[1].fate == "went_on"
        await overlap_part(io, 1, NEW_TEXT)  # decided already: changes nothing
        await overlap_part(io, 2, LISTENING_TEXT)
        assert io.commands.commands[-2:] == [Send(message=Unduck())] * 2
        await io.ending()
        await io.close()

    asyncio.run(drive())
    assert len(sent(io, Duck)) == len(sent(io, Unduck)) == 2
    assert io.commands.of(StopSpeaking) == [] and speaks(io, 2) == []
    assert rule.texts == [FAILING_TEXT, LISTENING_TEXT]  # nothing judged after the failure
    assert [(e.kind, e.reason) for e in emitted(io, Interrupted)] == [
        ("false", "no_words"),
        ("false", "listening"),
    ]
    (failed,) = [r for r in caplog.records if r.getMessage() == "overlap_judge_failed"]
    fields = getattr(failed, "fields", {})
    assert failed.levelno == logging.ERROR and fields["failure"] == "RuntimeError"
    assert (fields["turn_id"], fields["part"]) == (1, "window")
    assert FAILING_TEXT not in repr(fields) and "text" not in fields

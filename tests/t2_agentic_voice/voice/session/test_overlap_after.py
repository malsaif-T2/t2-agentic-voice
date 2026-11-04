"""What follows a stop word or a repeat request over a reply (voice/session/interrupter.py's what
followed, overlap.py's `asked_again`; plan 005's whole-plan review), with Track A's rule and
words, not a fake: a window that reads a request's first word as the stop word stops the reply,
and the whole overlap's new words are answered; the words said after a stop word in the same
turn (Smart Turn holding it open) are read with the stop taken off, a whole repeat request saying
the last reply again, a stop or nothing leaving the turn a command, anything else answered
without the stop; new words after a repeat request are answered, after the reply said again or
instead of it, and anything else leaves the repeat. The rehearsal's stop and repeat steps
(docs/project/DESCRIPTION.md, steps 1 and 2) run as one turn and as two. A lone word is built
from the lists, so no test writes an item's text."""

from __future__ import annotations

import asyncio

import pytest
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.events import Interrupted
from t2_agentic_voice.domain.interruption_words import NOISY_SOUNDS, NOISY_SPELLINGS
from t2_agentic_voice.domain.words import PRESET_WORDS
from t2_agentic_voice.voice.protocol import Unduck
from t2_agentic_voice.voice.session.commands import Send, StopSpeaking

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
    said_back,
    sent,
    speaks,
    turn,
)

ENGLISH, ARABIC = PRESET_WORDS["en"], PRESET_WORDS["ar"]
STOP, REPEAT = ENGLISH.stop[0], f"please, {ENGLISH.repeat[1]}"
REQUEST = "made-up fresh request of several words"
NOISY = sorted(spelling for spelling in NOISY_SPELLINGS if spelling.isascii())[0]
# The stop word as Whisper wrote it, "I stopped" (its first letters the stop word's), and a noun
# that ends as the stop word does: each the first word of a request written for the test.
STOPPED = next(sound for sound in sorted(NOISY_SOUNDS) if sound.startswith(ARABIC.stop[0]))
FIRST_WORDS = {
    "i-stopped": (STOPPED, f"{STOPPED} السياره قدام البوابه من الصبح"),
    "the-parking": ("الموقف", "الموقف زحمه اليوم مره"),
}


async def _answer_plays(io: FakeSessionIO, language: str = "en") -> None:
    """The call is greeted, the caller's turn 0 is heard, and its answer (reply 1, the echo)
    begins to play."""
    await greeted(io)
    await turn(io, 0, HEARD if language == "en" else HEARD_AR, language=language)
    await io.clause_queued(1, 0)
    await io.clock.advance(0.2)


async def _then(io: FakeSessionIO, window: str, said: str, language: str = "en") -> None:
    """Over the answer, the caller's turn 1 opens, its window and its whole overlap holding
    `window` (the detector heard the speech stop); the caller speaks again a moment later,
    Smart Turn holding the turn open, so the turn's own request goes, and its transcript holds
    `said`."""
    await io.turn_opened(1)
    await overlap_part(io, 1, window, part="window", audio_s=0.75)
    await overlap_part(io, 1, window)
    await io.clock.advance(1.5)
    await io.turn_closed(1)
    await io.transcribing(1, audio_s=2.6)
    await io.transcribed(1, said, language=language)


@pytest.mark.parametrize("held", [False, True], ids=["in-order", "turn-first"])
@pytest.mark.parametrize("first", list(FIRST_WORDS), ids=list(FIRST_WORDS))
def test_a_window_that_reads_a_requests_first_word_as_a_stop_still_answers_it(
    settings: VoiceSettings, first: str, held: bool
) -> None:
    """The window holds only the request's first word, the stop word as Whisper mishears it:
    the reply stops at once; the whole overlap, judged still, holds new words, so the turn is
    answered from its own transcript, whichever of the two comes first."""
    window, request = FIRST_WORDS[first]
    io, session = call(two_step(settings), language="ar-SA")

    async def drive() -> None:
        await _answer_plays(io, "ar")
        await io.turn_opened(1)
        await overlap_part(io, 1, window, part="window", audio_s=0.75)
        assert io.commands.of(StopSpeaking) == [StopSpeaking(reply_id=1)]
        await io.transcribing(1, audio_s=1.6, part="overlap")
        await io.turn_closed(1)
        if held:  # the turn's own request goes too, and its transcript comes first
            await io.transcribing(1, audio_s=1.6)
            await io.transcribed(1, request, language="ar")
            assert speaks(io, 2) == []
        await io.transcribed(1, request, language="ar", part="overlap")
        if not held:  # the turn's own transcript reuses the whole overlap's
            await io.transcribed(1, request, language="ar")
        await play(io, 2)
        await io.ending()
        await io.close()

    asyncio.run(drive())
    assert io.commands.of(StopSpeaking) == [StopSpeaking(reply_id=1)]
    (interrupted,) = emitted(io, Interrupted)
    assert (interrupted.kind, interrupted.reason) == ("stop", "stop_word")
    assert [s.text for s in speaks(io, 2)][1:] == said_back(io, request)
    assert {s.turn_id for s in speaks(io, 2)} == {1}
    assert [c.turn_id for c in captions(io, "caller")] == [0, 1]
    assert [(t.fate, t.reply_id) for t in session.history.turns()][1] == ("answered", 2)


@pytest.mark.parametrize("one_turn", [True, False], ids=["one-turn", "two-turns"])
def test_the_rehearsals_stop_and_repeat_steps_as_one_turn_and_as_two(
    settings: VoiceSettings, one_turn: bool
) -> None:
    """Step 1: the stop word over the answer stops it at once, never said back. Step 2: the
    repeat request, said a moment later in the same turn or as a turn of its own, says the cut
    answer again; the second, with a question mark, says it again once more."""
    io, session = call(two_step(settings), language="ar-SA")
    stop, short, polite = ARABIC.stop[0], ARABIC.repeat[1], f"{ARABIC.repeat[13]}؟"

    async def drive() -> None:
        await _answer_plays(io, "ar")
        if one_turn:
            await _then(io, stop, f"{stop} {short}", "ar")
        else:
            await io.turn_opened(1)
            await overlap_part(io, 1, stop, part="window", audio_s=0.75)
            await overlap_part(io, 1, stop)
            await io.turn_closed(1)
            await io.transcribed(1, stop, language="ar")
            await io.clock.advance(GAP_S)
            await turn(io, 2, short, language="ar")
        await play(io, 2)
        await io.clock.advance(GAP_S)
        await turn(io, 2 if one_turn else 3, polite, language="ar")
        await play(io, 3)
        await io.ending()
        await io.close()

    asyncio.run(drive())
    stopped = io.commands.commands.index(StopSpeaking(reply_id=1))
    assert io.commands.commands[stopped + 1] == Send(message=Unduck())
    assert io.commands.of(StopSpeaking) == [StopSpeaking(reply_id=1)]
    (interrupted,) = emitted(io, Interrupted)
    assert (interrupted.kind, interrupted.reason) == ("stop", "stop_word")
    answer = [s.text for s in speaks(io, 1)]
    assert [s.text for s in speaks(io, 2)] == answer == [s.text for s in speaks(io, 3)]
    alone = [] if one_turn else [("command", None)]  # the stop's own turn, said alone
    fates = [(t.fate, t.reply_id) for t in session.history.turns()]
    assert fates == [("rolled_back", 1), *alone, ("command", 2), ("command", 3)]
    assert [c.turn_id for c in captions(io, "caller")] == [0]


def test_a_request_said_after_a_stop_word_in_the_same_turn_is_answered_without_it(
    settings: VoiceSettings,
) -> None:
    io, session = call(two_step(settings))

    async def drive() -> None:
        await _answer_plays(io)
        await _then(io, STOP, f"{STOP}, {REQUEST}")
        await play(io, 2)
        await io.ending()
        await io.close()

    asyncio.run(drive())
    assert speaks(io, 2)[-1].text == REQUEST and {s.turn_id for s in speaks(io, 2)} == {1}
    assert [c.text for c in captions(io, "caller")][1:] == [REQUEST]
    assert len(emitted(io, Interrupted)) == 1
    assert [(t.fate, t.reply_id) for t in session.history.turns()][1] == ("answered", 2)


@pytest.mark.parametrize(
    "after", [STOP, "okay", "please", NOISY], ids=["stop", "listening", "polite", "noisy"]
)
def test_a_stop_or_nothing_said_after_a_stop_word_leaves_the_turn_a_command(
    settings: VoiceSettings, after: str
) -> None:
    io, session = call(two_step(settings))

    async def drive() -> None:
        await _answer_plays(io)
        await _then(io, STOP, f"{STOP}, {after}")
        await io.ending()
        await io.close()

    asyncio.run(drive())
    assert speaks(io, 2) == [] and [c.turn_id for c in captions(io, "caller")] == [0]
    assert [(t.fate, t.reply_id) for t in session.history.turns()][1] == ("command", None)


@pytest.mark.parametrize(
    ("after", "answered"),
    [(REQUEST, True), ("thanks", False), (STOP, False), ("okay", False)],
    ids=["new-words", "one-word", "stop", "listening"],
)
def test_new_words_after_a_repeat_request_are_answered_after_the_reply_said_again(
    settings: VoiceSettings, after: str, answered: bool
) -> None:
    """The window's repeat request stops the answer, which is said again once the whole overlap
    has come; new words the turn's own transcript holds after the request are answered next,
    and anything else (one word, a stop, a listening sound) leaves the repeat."""
    io, session = call(two_step(settings))

    async def drive() -> None:
        await _answer_plays(io)
        await _then(io, REPEAT, f"{REPEAT} {after}")
        await play(io, 2)
        if answered:
            await play(io, 3)
        await io.ending()
        await io.close()

    asyncio.run(drive())
    assert [s.text for s in speaks(io, 2)] == [s.text for s in speaks(io, 1)]
    assert {s.turn_id for s in speaks(io, 2)} == {1}
    if answered:
        assert speaks(io, 3)[-1].text == after and {s.turn_id for s in speaks(io, 3)} == {1}
    else:
        assert speaks(io, 3) == []
    fate = ("answered", 3) if answered else ("command", 2)
    assert [(t.fate, t.reply_id) for t in session.history.turns()][1] == fate
    assert len(emitted(io, Interrupted)) == 1 and len(sent(io, Unduck)) == 1


def test_new_words_after_a_windows_repeat_request_with_no_whole_overlap_are_answered_instead(
    settings: VoiceSettings,
) -> None:
    """No whole overlap came, so the repeat still waited: the words that followed it are
    answered instead of the reply said again."""
    io, session = call(two_step(settings))

    async def drive() -> None:
        await _answer_plays(io)
        await io.turn_opened(1)
        await overlap_part(io, 1, REPEAT, part="window", audio_s=0.75)
        await io.turn_closed(1)
        await io.transcribing(1, audio_s=2.6)
        await io.transcribed(1, f"{REPEAT} {REQUEST}", language="en")
        await play(io, 2)
        await io.ending()
        await io.close()

    asyncio.run(drive())
    assert speaks(io, 2)[-1].text == REQUEST and speaks(io, 3) == []
    assert [(t.fate, t.reply_id) for t in session.history.turns()][1] == ("answered", 2)

"""When an overlap is one, and the order its transcripts come in (voice/session/interrupter.py,
overlap.py; io.py's overlaps), under `interruptions.mode = "two_step"`, the rule a fake
(conftest.py's `rule`): speech in the 300 ms tail after a reply is an overlap (D-037), later speech
is not, and none follows the caller's own `stop` (TD-060), under either mode; a second overlap's
`unduck` waits until no overlap is undecided; speech after a listening sound, in the same turn,
still stops the agent; the turn's own transcript that comes before its overlap's is held until
the overlap decides; one whose whole overlap was never asked for decides it, and an empty overlap
part after it changes nothing; a window after the whole overlap changes nothing; a failed request
is reported once, not again by the turn's transcript that reuses it; and a part of a turn never
marked an overlap changes nothing."""

from __future__ import annotations

import asyncio

import pytest
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.events import Interrupted, ProviderFailed
from t2_agentic_voice.voice.protocol import Caption, Duck, Notice, Unduck
from t2_agentic_voice.voice.session.commands import HearOverlap, Send, StopSpeaking
from t2_agentic_voice.voice.session.playback import DROP_AFTER_S
from t2_agentic_voice.voice.session.session_events import Transcribed, TranscriptPart

from tests.t2_agentic_voice.voice.session.overlap_support import (
    LISTENING_TEXT,
    NEW_TEXT,
    SHORT_TEXT,
    STOP,
    STOP_TEXT,
    FakeRule,
    echo_playing,
    overlap_part,
    two_step,
)
from tests.t2_agentic_voice.voice.session.session_support import (
    HEARD,
    call,
    captions,
    emitted,
    greeted,
    play,
    report,
    sent,
    speaks,
    turn,
)


@pytest.mark.parametrize(
    ("after_s", "overlap"),
    [(DROP_AFTER_S - 0.1, True), (DROP_AFTER_S + 0.1, False)],
    ids=["in-the-tail", "after-it"],
)
def test_speech_in_the_tail_after_a_reply_is_an_overlap(
    settings: VoiceSettings, rule: FakeRule, after_s: float, overlap: bool
) -> None:
    """Within 300 ms after the echo played, the caller's speech is an overlap: its stop word
    stops nothing (nothing plays) and brings the voice back; later, it is a turn answered."""
    io, _ = call(two_step(settings))

    async def drive() -> None:
        await greeted(io)
        await turn(io, 0, HEARD)
        await play(io, 1)
        await io.clock.advance(after_s)
        await io.turn_opened(1)
        if overlap:
            await overlap_part(io, 1, STOP_TEXT)
        await io.turn_closed(1)
        if not overlap:
            await io.transcribing(1)
        await io.transcribed(1, STOP_TEXT, language="en")
        await io.ending()
        await io.close()

    asyncio.run(drive())
    assert bool(io.commands.of(HearOverlap)) is overlap
    assert io.commands.of(StopSpeaking) == []
    assert sent(io, Unduck) == ([Unduck()] if overlap else [])
    assert bool(speaks(io, 2)) is not overlap
    assert [e.kind for e in emitted(io, Interrupted)] == (["stop"] if overlap else [])


@pytest.mark.parametrize("mode", ["drop", "two_step"])
def test_no_tail_follows_the_callers_own_stop(settings: VoiceSettings, mode: str) -> None:
    """Speech begun 100 ms after the caller's `stop` is not the agent's voice heard back, since
    nothing of it plays on: it is answered, under either mode (TD-060). Under `two_step` the stop
    also sends the playing caption again marked cut; under `drop` it gives the drop rule's
    commands."""
    custom = two_step(settings) if mode == "two_step" else settings
    io, _ = call(custom)

    async def drive() -> None:
        await echo_playing(io)
        await io.client({"v": 1, "type": "stop"})
        await io.clock.advance(0.1)
        await turn(io, 1, "made-up words after the stop")
        await io.ending()
        await io.close()

    asyncio.run(drive())
    assert io.commands.of(HearOverlap) == [] and speaks(io, 2)
    assert not report(io).turns[1].dropped
    cut = [(c.reply_id, c.clause) for c in captions(io) if c.cut]
    assert cut == ([(1, 0)] if mode == "two_step" else [])
    (stopped,) = emitted(io, Interrupted)
    assert (stopped.turn_id, stopped.kind, stopped.reason) == (0, "stop", None)


def test_a_second_overlaps_unduck_waits_until_none_is_undecided(
    settings: VoiceSettings, rule: FakeRule
) -> None:
    """Two listening sounds over one long reply, the second begun before the first is judged:
    the first's verdict raises no voice while the second is undecided; the second's brings
    both `unduck`s, one for each `duck`."""
    io, _ = call(two_step(settings))

    async def drive() -> None:
        await echo_playing(io)
        await io.turn_opened(1)
        await io.clock.advance(0.5)
        await io.turn_closed(1)
        await io.turn_opened(2)
        await overlap_part(io, 1, LISTENING_TEXT)
        assert sent(io, Unduck) == []
        await overlap_part(io, 2, LISTENING_TEXT)
        unduck = Send(message=Unduck())
        assert io.commands.commands[-2:] == [unduck, unduck]
        await io.ending()
        await io.close()

    asyncio.run(drive())
    assert len(sent(io, Duck)) == len(sent(io, Unduck)) == 2
    assert [e.kind for e in emitted(io, Interrupted)] == ["false", "false"]


@pytest.mark.parametrize(
    ("own_request", "then", "stopped"),
    [(True, STOP_TEXT, True), (True, "made-up murmur", False), (False, None, False)],
    ids=["then-a-stop-word", "then-more-murmur", "nothing-after"],
)
def test_speech_after_a_listening_sound_in_the_same_turn_is_judged_too(
    settings: VoiceSettings,
    rule: FakeRule,
    own_request: bool,
    then: str | None,
    stopped: bool,
) -> None:
    """The whole overlap was a listening sound, so the reply went on; the turn went on with
    more speech, which its own transcript holds (its own request went): judged again, at no
    request of the overlap's, a stop word in it stops the agent, with no second `unduck`. A
    turn whose transcript reused the overlap's is not judged again."""
    whole = LISTENING_TEXT if then is None else f"{LISTENING_TEXT} {then}"
    rule.script[f"{LISTENING_TEXT} {STOP_TEXT}"] = STOP
    io, session = call(two_step(settings))

    async def drive() -> None:
        await echo_playing(io)
        await io.turn_opened(1)
        await overlap_part(io, 1, LISTENING_TEXT)
        await io.clock.advance(0.8)
        await io.turn_closed(1)
        if own_request:
            await io.transcribing(1, audio_s=1.6)
        await io.transcribed(1, whole, language="en")
        await io.ending()
        await io.close()

    asyncio.run(drive())
    assert rule.texts == ([LISTENING_TEXT, whole] if own_request else [LISTENING_TEXT])
    assert bool(io.commands.of(StopSpeaking)) is stopped
    assert sent(io, Unduck) == [Unduck()] and speaks(io, 2) == []
    kinds = [e.kind for e in emitted(io, Interrupted)]
    assert kinds == (["false", "stop"] if stopped else ["false"])
    assert session.history.turns()[1].fate == ("command" if stopped else "went_on")
    if stopped:
        assert rule.judged[-1].speech_s == pytest.approx(1.0)  # to the end of its speech


def test_a_turns_transcript_that_comes_before_its_overlaps_is_held_until_it_decides(
    settings: VoiceSettings, rule: FakeRule
) -> None:
    io, _ = call(two_step(settings))
    whole = f"{NEW_TEXT} and more of it"

    async def drive() -> None:
        await echo_playing(io)
        await io.turn_opened(1)
        await io.clock.advance(0.6)
        await io.transcribing(1, audio_s=0.6, part="overlap")
        await io.clock.advance(0.9)
        await io.turn_closed(1)
        await io.transcribing(1, audio_s=1.5)
        await io.transcribed(1, whole, language="en")  # before the overlap's
        assert speaks(io, 2) == [] and io.commands.of(StopSpeaking) == []
        await io.transcribed(1, NEW_TEXT, language="en", part="overlap")
        await play(io, 2)
        await io.ending()
        await io.close()

    asyncio.run(drive())
    assert io.commands.of(StopSpeaking) == [StopSpeaking(reply_id=1)]
    assert speaks(io, 2)[-1].text == whole and rule.texts == [NEW_TEXT]
    assert [c.turn_id for c in captions(io, "caller")] == [0, 1]
    assert rule.judged[0].speech_s == pytest.approx(0.4)  # to its request, less the stop delay


def test_an_overlap_whose_whole_transcript_was_never_asked_for_is_decided_by_the_turn(
    settings: VoiceSettings, rule: FakeRule
) -> None:
    io, _ = call(two_step(settings))

    async def drive() -> None:
        await echo_playing(io)
        await io.turn_opened(1)
        await overlap_part(io, 1, SHORT_TEXT, part="window", audio_s=0.75)
        await io.clock.advance(0.5)
        await io.turn_closed(1)
        await io.transcribing(1, audio_s=1.2)
        await io.transcribed(1, STOP_TEXT, language="en")
        await io.ending()
        await io.close()

    asyncio.run(drive())
    assert rule.texts == [SHORT_TEXT, STOP_TEXT]
    assert io.commands.of(StopSpeaking) == [StopSpeaking(reply_id=1)]
    assert sent(io, Unduck) == [Unduck()] and speaks(io, 2) == []


def test_a_part_of_a_turn_never_marked_an_overlap_changes_nothing(
    settings: VoiceSettings, rule: FakeRule
) -> None:
    io, session = call(two_step(settings))

    async def drive() -> None:
        await greeted(io)
        given = len(io.commands.commands)
        at = io.clock.now()
        await session.handle(
            Transcribed(turn_id=4, at=at, audio_s=0.7, sent_at=at, transcript=None, part="window")
        )
        assert len(io.commands.commands) == given
        await io.ending()
        await io.close()

    asyncio.run(drive())
    assert rule.judged == [] and not [c for c in sent(io, Caption) if c.speaker == "caller"]


def test_a_window_that_comes_after_the_whole_overlap_changes_nothing(
    settings: VoiceSettings, rule: FakeRule
) -> None:
    """The parts may come in either order: once the whole overlap decided, a late window, even
    one holding a stop word, is not judged."""
    io, _ = call(two_step(settings))

    async def drive() -> None:
        await echo_playing(io)
        await io.turn_opened(1)
        await io.transcribing(1, audio_s=0.75, part="window")
        await io.transcribing(1, audio_s=0.9, part="overlap")
        await io.transcribed(1, LISTENING_TEXT, language="en", part="overlap")
        await io.transcribed(1, STOP_TEXT, language="en", part="window")
        await io.ending()
        await io.close()

    asyncio.run(drive())
    assert rule.texts == [LISTENING_TEXT] and io.commands.of(StopSpeaking) == []
    assert sent(io, Unduck) == [Unduck()]


def test_a_turns_transcript_before_any_overlap_request_decides_and_a_later_empty_part_does_not(
    settings: VoiceSettings, rule: FakeRule
) -> None:
    """The `HearOverlap` reached the bridge after the turn closed: the turn's own transcript
    comes first, with no overlap request in flight, and decides; the empty overlap part the
    bridge sends after it (no words) changes nothing."""
    io, _ = call(two_step(settings))

    async def drive() -> None:
        await echo_playing(io)
        await io.turn_opened(1)
        await io.clock.advance(0.4)
        await io.turn_closed(1)
        await io.transcribing(1, audio_s=0.4)
        await io.transcribed(1, STOP_TEXT, language="en")
        await io.transcribed(1, None, part="overlap")
        await io.ending()
        await io.close()

    asyncio.run(drive())
    assert rule.texts == [STOP_TEXT] and io.commands.of(StopSpeaking) == [StopSpeaking(reply_id=1)]
    assert sent(io, Unduck) == [Unduck()] and speaks(io, 2) == []


def test_a_failed_request_is_reported_once_and_the_turn_reusing_it_not_again(
    settings: VoiceSettings, rule: FakeRule
) -> None:
    """The whole overlap's request failed: one `ProviderFailed`, the rule reading no words; the
    turn's own transcript reuses the failed result, with no request of its own, and reports
    nothing more, nor counts a request."""
    io, _ = call(two_step(settings))

    async def drive() -> None:
        await echo_playing(io)
        await io.turn_opened(1)
        await io.clock.advance(0.6)
        await io.transcribing(1, audio_s=0.6, part="overlap")
        await io.transcribed(1, None, failure="timeout", retryable=True, part="overlap")
        await io.turn_closed(1)
        await io.transcribed(1, None, failure="timeout", retryable=True)
        await io.ending()
        await io.close()

    asyncio.run(drive())
    assert [(e.turn_id, e.kind) for e in emitted(io, ProviderFailed)] == [(1, "timeout")]
    assert rule.texts == [""] and sent(io, Unduck) == [Unduck()]
    assert report(io).usage[0].requests == 2  # turn 0's and the overlap's
    assert speaks(io, 2) == [] and sent(io, Notice) == []


@pytest.mark.parametrize("turn_first", [True, False], ids=["turn-first", "overlap-first"])
def test_an_overlap_heard_after_its_turn_closed_is_decided_once_from_the_turns_result(
    settings: VoiceSettings, rule: FakeRule, turn_first: bool
) -> None:
    """A short sound over the echo: the `HearOverlap` reached the bridge after the turn closed,
    so the turn's own request went, and its whole overlap reuses that result, with no request
    of its own, after the turn's transcript (as the bridge sends it) or before it. Either way
    the overlap is decided once, its speech timed to when the turn's speech ended, the voice
    comes back once, and the turn is not answered."""
    io, session = call(two_step(settings))

    async def drive() -> None:
        await echo_playing(io)
        await io.turn_opened(1)
        await io.clock.advance(0.4)
        await io.turn_closed(1)
        await io.clock.advance(0.5)  # the turn analyzer's decision
        await io.transcribing(1, audio_s=0.4)
        parts: list[TranscriptPart] = ["turn", "overlap"] if turn_first else ["overlap", "turn"]
        for part in parts:
            await io.transcribed(1, SHORT_TEXT, language="en", part=part)
        await io.ending()
        await io.close()

    asyncio.run(drive())
    assert rule.texts == [SHORT_TEXT] and rule.judged[0].speech_s == pytest.approx(0.4)
    assert sent(io, Unduck) == [Unduck()] and io.commands.of(StopSpeaking) == []
    assert speaks(io, 2) == [] and session.history.turns()[1].fate == "went_on"
    assert report(io).usage[0].requests == 2  # turn 0's and turn 1's own

"""The time to first audio per turn (voice/session/turn_book.py, report.py; plan 006): from the end
of the caller's speech, the detector's stop less its delay, to the first audible frame of the
reply sent, a silent first chunk not counted (TD-090), and to the browser's playback of it; a
progress line counted apart; the talker's first token; the end of the turn, to Smart Turn's
"complete" and to the turn's close (D-083); on the turn's span and in the report, and each
model's usage so far with the turn's `TurnMetrics`. A call whose output taps no audio times the
reply's first audio queued."""

from __future__ import annotations

import asyncio

import pytest
from t2_agentic_voice.agent.talker import ProgressDue, ReplyDone, SpokenClause
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.conversation import TalkerTurn
from t2_agentic_voice.core.events import TurnMetrics
from t2_agentic_voice.voice.session.audible import audible
from t2_agentic_voice.voice.session.session_events import AgentAudio

from tests.t2_agentic_voice.fakes import tone
from tests.t2_agentic_voice.session_fakes import FakeSessionIO
from tests.t2_agentic_voice.voice.session.session_support import (
    HEARD,
    call,
    emitted,
    greeted,
    play,
    report,
    spans,
    traced,
    turn,
)
from tests.t2_agentic_voice.voice.session.talker_support import (
    Step,
    Work,
    answer,
    settle,
    talker_call,
)

SILENT = bytes(960)  # 20 ms of digital silence at 24 kHz


async def _tap(io: FakeSessionIO, pcm16: bytes) -> None:
    """The output sends `pcm16` of the agent's audio now."""
    await io._hand(AgentAudio(pcm16=pcm16, sample_rate=24_000, at=io.clock.now()))


def test_the_first_audible_frame_ends_the_time_to_first_audio_and_the_browser_its_playback(
    settings: VoiceSettings,
) -> None:
    io, session, exporter = traced(settings)
    stop_s = settings.turns.vad_stop_ms / 1000

    async def drive() -> None:
        await greeted(io)
        await turn(io, 0, HEARD)  # its speech's end reached the session at 102.0
        await io.clock.advance(0.2)
        await io.clause_queued(1, 0)
        await _tap(io, SILENT)  # the take's silent lead is not audible
        await io.clock.advance(0.3)
        await _tap(io, tone(0.02, 24_000))
        await io.clock.advance(0.1)
        played = {"v": 1, "type": "playback", "reply_id": 1, "clause": 0, "event": "started"}
        await io.client(played)
        await io.clause_played(1, 0)  # the echo's frame, then the words heard
        await io.synthesizing(1, 1)
        await io.clause_queued(1, 1)
        await io.clause_played(1, 1)
        await io.ending()
        await io.close()

    asyncio.run(drive())
    times = report(io).turns[0].times
    assert times.ttfa_ms == pytest.approx((0.5 + stop_s) * 1000)
    assert times.played_ms == pytest.approx((0.6 + stop_s) * 1000)
    (metrics,) = emitted(io, TurnMetrics)
    assert metrics.ttfa_ms == times.ttfa_ms
    (span,) = [s for s in spans(session, exporter) if (s.attributes or {}).get("turn.ttfa_ms")]
    assert span.attributes is not None and span.attributes["turn.ttfa_ms"] == times.ttfa_ms


def test_the_end_of_turn_is_timed_to_smart_turns_complete_and_to_the_turns_close(
    settings: VoiceSettings,
) -> None:
    io, _ = call(settings)
    stop_s = settings.turns.vad_stop_ms / 1000

    async def drive() -> None:
        await greeted(io)
        await io.turn_opened(0)
        await io.clock.advance(1.0)
        stopped = io.clock.now()  # the detector's stop, `stop_s` after the speech's end
        await io.clock.advance(0.2)
        await io.turn_held(0)  # complete, too soon: the caller goes on
        await io.clock.advance(0.1)
        await io.hold_resumed(0)
        await io.clock.advance(0.1)
        await io.turn_held(0)  # complete again, the hold begins
        await io.clock.advance(0.6)
        await io.turn_closed(0, speech_ended_at=stopped)
        await io.transcribing(0)
        await io.transcribed(0, HEARD, language="en")
        await play(io, 1)
        await io.ending()
        await io.close()

    asyncio.run(drive())
    times = report(io).turns[0].times
    assert times.turn_complete_ms == pytest.approx((0.4 + stop_s) * 1000)
    assert times.end_of_turn_ms == pytest.approx((1.0 + stop_s) * 1000)
    (metrics,) = emitted(io, TurnMetrics)
    assert (metrics.end_of_turn_ms, metrics.turn_complete_ms) == (
        times.end_of_turn_ms,
        times.turn_complete_ms,
    )
    stt = {u.model: u for u in metrics.usage}[settings.stt.model]
    assert stt.requests == 1


def test_a_turn_whose_hold_was_resumed_and_never_held_again_has_no_complete_time(
    settings: VoiceSettings,
) -> None:
    io, _ = call(settings)

    async def drive() -> None:
        await greeted(io)
        await io.turn_opened(0)
        await io.turn_held(0)
        await io.hold_resumed(0)
        await io.clock.advance(1.0)
        await io.turn_closed(0)
        await io.transcribing(0)
        await io.transcribed(0, HEARD, language="en")
        await io.ending()
        await io.close()

    asyncio.run(drive())
    times = report(io).turns[0].times
    assert times.turn_complete_ms is None and times.end_of_turn_ms is not None


def test_a_call_whose_output_taps_no_audio_times_the_first_audio_queued(
    settings: VoiceSettings,
) -> None:
    io, _ = call(settings)
    stop_s = settings.turns.vad_stop_ms / 1000

    async def drive() -> None:
        await greeted(io)
        await turn(io, 0, HEARD)
        await io.clock.advance(0.25)
        await io.clause_queued(1, 0)
        await io.ending()
        await io.close()

    asyncio.run(drive())
    times = report(io).turns[0].times
    assert times.ttfa_ms == pytest.approx((0.25 + stop_s) * 1000) and times.played_ms is None


def test_a_progress_line_is_timed_apart_and_the_talkers_first_token_on_its_own(
    settings: VoiceSettings,
) -> None:
    def script(turn: TalkerTurn) -> list[Step]:
        return [
            ProgressDue(tool="search_help", key="looking", language="en"),
            Work(2.0),
            *answer("Found it.")[:2],  # its one model request, and its usage
            SpokenClause(text="Found it.", language="en"),
            ReplyDone(),
        ]

    io, _, _ = talker_call(settings, script)
    stop_s = settings.turns.vad_stop_ms / 1000

    async def drive() -> None:
        await greeted(io)
        await turn(io, 0, "Where is my ticket?")
        await settle()
        await io.clock.advance(0.1)
        await io.clause_queued(1, 0)  # the progress line, 0.1 s after the speech's end came
        await io.clause_played(1, 0, audio_s=1.0)
        await io.clock.advance(1.9)
        await settle()
        await io.clock.advance(0.4)
        await io.synthesizing(1, 1)
        await io.clause_queued(1, 1)  # the answer, 2.4 s after
        await io.clause_played(1, 1)
        await io.ending()
        await io.close()

    asyncio.run(drive())
    times = report(io).turns[0].times
    assert times.progress_ms == pytest.approx((0.1 + stop_s) * 1000)
    assert times.ttfa_ms == pytest.approx((2.4 + stop_s) * 1000)
    # the request went once the work was done, 2.0 s after; its first token 0.3 s later
    assert times.llm_first_token_ms == pytest.approx((2.3 + stop_s) * 1000)


def test_a_frame_is_audible_only_past_the_floor() -> None:
    assert not audible(SILENT) and not audible(b"") and not audible(b"\x01")
    assert audible(tone(0.02, 24_000))
    assert not audible((300).to_bytes(2, "little", signed=True) * 10)

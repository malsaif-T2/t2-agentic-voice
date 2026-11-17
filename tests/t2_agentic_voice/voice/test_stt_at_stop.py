"""The held request sent at the speech detector's stop (`turns.early_at_stop`; voice/stt_held.py,
turn_hold.py's `TurnUnfinishedFrame`; plan 010's 2.2): the real turn processors signal a pause
Smart Turn calls unfinished behind the detector's stop, only when asked; the bridge sends the
turn's speech so far at the stop, its `Transcribing` before `TurnHeld`, and hands its answer
only once Smart Turn calls the turn complete, after `TurnHeld` even when it came first, the
turn's own transcript reusing it with no request; a pause called unfinished drops it unhanded,
in flight or done, and the next stop sends again with the whole turn; speech resumed in the hold
drops it; a turn marked an overlap sends none, and one marked after its stop drops it; a dropped
request is never cancelled, so it runs out (its connection kept warm), unless the call ends
first; and with the setting off the bridge does as it did, whatever frames come."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING

import pytest
from t2_agentic_voice.core.settings.turns import TurnSettings
from t2_agentic_voice.domain.ports.speech_to_text import AudioClip, Transcript
from t2_agentic_voice.voice.pipecat_events import FailureReport
from t2_agentic_voice.voice.session.io import SYSTEM_CLOCK
from t2_agentic_voice.voice.session.session_events import (
    HoldResumed,
    Transcribed,
    Transcribing,
    TurnHeld,
)
from t2_agentic_voice.voice.session_bridge import EventStream
from t2_agentic_voice.voice.stt_bridge import TurnSTTBridge
from t2_agentic_voice.voice.turn_hold import HoldResumedFrame, TurnHeldFrame, TurnUnfinishedFrame
from t2_agentic_voice.voice.turns import stops_early, turn_processors

from tests.t2_agentic_voice.fakes import FakeSpeechToText
from tests.t2_agentic_voice.voice.kit import (
    START_S,
    STOP_S,
    PauseAnalyzer,
    Recorder,
    Tail,
    ToneVAD,
    audio_frames,
    run_pipeline,
    until,
)

if TYPE_CHECKING:
    from pipecat.frames.frames import Frame
    from pipecat.pipeline.worker import PipelineWorker

FULL = "I want to reset my password"
# A step of a test's feed: a frame queued, seconds waited (a verdict's time), or a call on the
# bridge (an overlap marked).
type Step = Frame | float | Callable[[TurnSTTBridge], None]


class _Watched(FakeSpeechToText):
    """The fake, counting the requests that ran out (`finished`) and those cancelled."""

    def __init__(self, script: Sequence[str], *, delay_s: float = 0.0) -> None:
        super().__init__(script, delay_s=delay_s)
        self.finished = self.cancelled = 0

    async def transcribe(
        self, clip: AudioClip, *, language: str | None, prompt: str | None
    ) -> Transcript:
        try:
            heard = await super().transcribe(clip, language=language, prompt=prompt)
        except asyncio.CancelledError:
            self.cancelled += 1
            raise
        self.finished += 1
        return heard


def _signals(*, unfinished: bool) -> list[str]:
    """The frames the real turn processors push for a pause Smart Turn calls unfinished, then
    one it calls complete, held 600 ms."""
    from pipecat.frames.frames import UserStoppedSpeakingFrame

    vad, user_turns = turn_processors(
        ToneVAD(), PauseAnalyzer(incomplete=1), TurnSettings(), unfinished=unfinished
    )
    tail = Tail()

    async def feed(worker: PipelineWorker) -> None:
        for frame in audio_frames(0.2, loud=False):
            await worker.queue_frame(frame)
        for tone_s, silence_s in [(0.4, 0.3), (0.4, 0.8)]:
            for frame in [*audio_frames(tone_s), *audio_frames(silence_s, loud=False)]:
                await worker.queue_frame(frame)
        await until(lambda: bool(tail.of(UserStoppedSpeakingFrame)))
        await asyncio.sleep(0.05)

    asyncio.run(run_pipeline([vad, user_turns, tail], feed))
    names = {"VADUserStoppedSpeakingFrame", "TurnUnfinishedFrame", "TurnHeldFrame"}
    return [type(f).__name__ for f, _ in tail.frames if type(f).__name__ in names]


def test_a_pause_called_unfinished_is_signalled_behind_the_stop_only_when_asked() -> None:
    stop, held = "VADUserStoppedSpeakingFrame", "TurnHeldFrame"
    assert _signals(unfinished=True) == [stop, "TurnUnfinishedFrame", stop, held]
    assert _signals(unfinished=False) == [stop, stop, held]


@pytest.mark.parametrize(
    ("turns", "analyzer", "early"),
    [
        (TurnSettings(early_at_stop=True), True, True),
        (TurnSettings(), True, False),
        (TurnSettings(early_at_stop=True, complete_hold_ms=0), True, False),
        (TurnSettings(early_at_stop=True), False, False),
    ],
    ids=["on", "off by default", "no hold", "no smart turn"],
)
def test_the_request_goes_at_the_stop_only_under_the_hold(
    turns: TurnSettings, analyzer: bool, early: bool
) -> None:
    assert stops_early(turns, PauseAnalyzer() if analyzer else None) is early


def _opened(speech_s: float = 0.4) -> list[Frame]:
    from pipecat.frames.frames import UserStartedSpeakingFrame, VADUserStartedSpeakingFrame

    return [
        *audio_frames(1.0, loud=False),
        *audio_frames(START_S),
        VADUserStartedSpeakingFrame(start_secs=START_S),
        UserStartedSpeakingFrame(),
        *audio_frames(speech_s),
    ]


def _stopped() -> list[Frame]:
    from pipecat.frames.frames import VADUserStoppedSpeakingFrame

    return [*audio_frames(STOP_S, loud=False), VADUserStoppedSpeakingFrame(stop_secs=STOP_S)]


def _resumed(*, held: bool, speech_s: float = 0.6) -> list[Frame]:
    from pipecat.frames.frames import VADUserStartedSpeakingFrame

    resumed: list[Frame] = [HoldResumedFrame()] if held else []
    start = VADUserStartedSpeakingFrame(start_secs=START_S)
    return [*audio_frames(START_S), start, *resumed, *audio_frames(speech_s)]


def _closed() -> list[Frame]:
    from pipecat.frames.frames import UserStoppedSpeakingFrame

    return [*audio_frames(0.2, loud=False), UserStoppedSpeakingFrame()]


def _bridge(
    port: FakeSpeechToText, steps: Sequence[Step], *, at_stop: bool = True, ended: bool = False
) -> Recorder:
    """The bridge of a talker call, its held request at the stop with `at_stop`, fed `steps`;
    returned once the turn's own transcript came, or with `ended` once the call ended after them."""
    events, session = EventStream(SYSTEM_CLOCK), Recorder()
    report = FailureReport(call_id="call-1", emit=lambda event: None, clock=SYSTEM_CLOCK)
    stt = TurnSTTBridge(
        stt=port, events=events, report=report, start_s=START_S, early=True, at_stop=at_stop
    )

    async def feed(worker: PipelineWorker) -> None:
        events.start(session)
        for step in steps:
            if isinstance(step, float):
                await asyncio.sleep(step)
            elif callable(step):
                step(stt)
            else:
                await worker.queue_frame(step)
        if ended:
            await stt.drop()
        else:
            await until(lambda: bool(_own(session)))
        await asyncio.sleep(0.4)  # any answer still to come (none should)
        await events.close()

    asyncio.run(run_pipeline([stt], feed))
    return session


def _own(session: Recorder) -> list[Transcribed]:
    return [e for e in session.of(Transcribed) if e.part == "turn"]


def _part(session: Recorder, part: str) -> list[Transcribed]:
    return [e for e in session.of(Transcribed) if e.part == part]


def _sent(session: Recorder) -> list[str]:
    return [e.part for e in session.of(Transcribing)]


def _at(session: Recorder, kind: type[object], part: str | None = None) -> int:
    """The index of the first event of `kind` (of `part`) among the session's events."""
    for index, event in enumerate(session.events):
        if isinstance(event, kind) and (part is None or getattr(event, "part", None) == part):
            return index
    raise AssertionError(f"no {kind.__name__}")


def test_the_request_goes_at_the_stop_and_its_answer_is_handed_once_held() -> None:
    port = FakeSpeechToText([FULL], delay_s=0.2)
    session = _bridge(port, [*_opened(), *_stopped(), 0.1, TurnHeldFrame(), *_closed()])
    assert _at(session, Transcribing) < _at(session, TurnHeld) < _at(session, Transcribed, "held")
    (held,), (own,) = _part(session, "held"), _own(session)
    assert _sent(session) == ["held"] and len(port.calls) == 1  # the turn reuses it
    assert own.transcript == held.transcript and held.sent_at is not None


def test_an_answer_that_comes_before_the_verdict_waits_for_it() -> None:
    port = FakeSpeechToText([FULL])
    seen: list[int] = []
    steps: list[Step] = [*_opened(), *_stopped(), 0.2]
    steps += [lambda _: seen.append(len(port.calls)), TurnHeldFrame(), *_closed()]
    session = _bridge(port, steps)
    assert seen == [1]  # the request had gone, and answered, before Smart Turn's verdict
    assert _at(session, TurnHeld) < _at(session, Transcribed, "held")


@pytest.mark.parametrize("delay_s", [0.3, 0.0], ids=["in flight", "answered"])
def test_a_pause_called_unfinished_drops_the_request_and_the_next_stop_sends_all(
    delay_s: float,
) -> None:
    port = _Watched(["I want to", FULL], delay_s=delay_s)
    steps: list[Step] = [*_opened(), *_stopped(), 0.1, TurnUnfinishedFrame()]
    steps += [*_resumed(held=False), *_stopped(), 0.1, TurnHeldFrame(), *_closed()]
    session = _bridge(port, steps)
    (held,), (own,) = _part(session, "held"), _own(session)
    assert held.transcript is not None and held.transcript.text == FULL  # one answer
    assert own.transcript == held.transcript and len(port.calls) == 2
    first, second = session.of(Transcribing)
    assert (first.part, second.part) == ("held", "held") and second.audio_s > first.audio_s
    assert len(session.of(TurnHeld)) == 1 and session.of(HoldResumed) == []
    assert (port.finished, port.cancelled) == (2, 0)  # the dropped one ran out, never cancelled


def test_the_calls_end_cancels_a_dropped_request_still_in_flight() -> None:
    port, seen = _Watched(["I want to"], delay_s=0.5), list[tuple[int, int]]()
    steps: list[Step] = [*_opened(), *_stopped(), 0.1, TurnUnfinishedFrame(), 0.1]
    steps.append(lambda _: seen.append((port.finished, port.cancelled)))
    session = _bridge(port, steps, ended=True)
    assert seen == [(0, 0)] and (port.finished, port.cancelled) == (0, 1)  # cancelled at the end
    assert _sent(session) == ["held"] and _part(session, "held") == []


def test_speech_resumed_in_the_hold_drops_the_request_sent_at_the_stop() -> None:
    port = _Watched(["I want to", FULL], delay_s=0.3)
    steps: list[Step] = [*_opened(), *_stopped(), 0.05, TurnHeldFrame()]
    steps += [*_resumed(held=True), *_stopped(), 0.05, TurnHeldFrame(), *_closed()]
    session = _bridge(port, steps)
    assert len(session.of(HoldResumed)) == 1 and len(port.calls) == 2
    (held,) = _part(session, "held")  # the first ran out, never answering
    assert held.transcript is not None and held.transcript.text == FULL
    assert _at(session, HoldResumed) < _at(session, Transcribed, "held")
    assert (port.finished, port.cancelled) == (2, 0)


def test_a_turn_marked_an_overlap_before_its_stop_sends_no_held_request() -> None:
    port = FakeSpeechToText(["wait", "wait, no"], delay_s=0.1)
    mark: Step = lambda stt: stt.hear_overlap(0, 750)  # noqa: E731
    session = _bridge(port, [*_opened(), 0.1, mark, *_stopped(), 0.05, TurnHeldFrame(), *_closed()])
    assert _sent(session) == ["window", "overlap"] and session.of(TurnHeld) == []
    assert _part(session, "held") == [] and len(port.calls) == 2  # the turn reuses its overlap


def test_a_turn_marked_an_overlap_after_its_stop_drops_the_request() -> None:
    port = _Watched(["wait", "wait, no"], delay_s=0.2)
    mark: Step = lambda stt: stt.hear_overlap(0, 750)  # noqa: E731
    session = _bridge(port, [*_opened(), *_stopped(), 0.05, mark, TurnHeldFrame(), *_closed()])
    assert _sent(session) == ["held", "overlap"] and session.of(TurnHeld) == []
    assert _part(session, "held") == [] and port.cancelled == 0  # it ran out, never answering
    (overlap,), (own,) = _part(session, "overlap"), _own(session)
    assert overlap.transcript is not None and overlap.transcript.text == "wait, no"
    assert own.transcript == overlap.transcript and len(port.calls) == 2


def test_with_the_setting_off_the_bridge_sends_at_the_verdict_and_ignores_unfinished() -> None:
    port = FakeSpeechToText([FULL])
    steps: list[Step] = [*_opened(), *_stopped(), 0.1, TurnUnfinishedFrame()]
    steps += [*_resumed(held=False), *_stopped(), 0.1, TurnHeldFrame(), *_closed()]
    session = _bridge(port, steps, at_stop=False)
    assert _at(session, TurnHeld) < _at(session, Transcribing)
    assert _sent(session) == ["held"] and len(port.calls) == 1

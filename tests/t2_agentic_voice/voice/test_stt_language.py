"""Each turn's language in the speech-to-text bridge (voice/stt_language.py's `TurnLanguages`, in
voice/stt_bridge.py; plan 007's Block H, Q17 and Q18), with a fake classifier
(tests/t2_agentic_voice/language_fakes.py) and a fake speech-to-text: classification starts once
the turn's audio holds `from_s` from its speech's first byte, never on the clock, at most once a
turn, and a shorter turn never asks; each request names the language in hand as it goes, its
`Transcribing` carrying it, never waiting on the classifier: the held request in the same step
as `TurnHeld`, a verdict still running `late`, a classifier that blocks 2 s delaying no frame
and no request; an overlap's parts name the current language with a verdict in hand; the turn's
own request names what its hold decided, in a call with no talker too; resumed speech decides
again; `drop` cancels the classification and a late result is never used; a busy or failing
classifier keeps the language; and only `classified` moves the call's current language."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest
from t2_agentic_voice.core.errors import ProviderError
from t2_agentic_voice.domain.turn_language import LanguageRule
from t2_agentic_voice.voice.calls import TICKER_BOUND_S
from t2_agentic_voice.voice.pipecat_events import FailureReport
from t2_agentic_voice.voice.session.io import SYSTEM_CLOCK
from t2_agentic_voice.voice.session.session_events import (
    Transcribed,
    Transcribing,
    TurnClosed,
    TurnHeld,
)
from t2_agentic_voice.voice.session_bridge import CallEvents
from t2_agentic_voice.voice.stt_bridge import TurnSTTBridge
from t2_agentic_voice.voice.stt_language import TurnLanguages
from t2_agentic_voice.voice.turn_hold import HoldResumedFrame, TurnHeldFrame

from tests.t2_agentic_voice.fakes import FakeSpeechToText, tone
from tests.t2_agentic_voice.language_fakes import Answer, FakeLanguageClassifier
from tests.t2_agentic_voice.voice.kit import (
    START_S,
    STOP_S,
    Recorder,
    audio_frames,
    run_pipeline,
    until,
)

if TYPE_CHECKING:
    from pipecat.frames.frames import Frame
    from pipecat.pipeline.worker import PipelineWorker

RULE = LanguageRule(from_s=2.0, min_share=0.7)
ENGLISH = {"ar": 0.1, "en": 0.9}
PROMPTS = {"ar": "arabic prompt", "en": "english prompt"}


@dataclass
class Rig:
    session: Recorder
    stt: TurnSTTBridge
    port: FakeSpeechToText
    classifier: FakeLanguageClassifier

    def sent(self, part: str | None = None) -> list[Transcribing]:
        return [e for e in self.session.of(Transcribing) if part is None or e.part == part]


Body = Callable[[Rig, "PipelineWorker"], Awaitable[None]]


def _run(classifier: FakeLanguageClassifier, body: Body, *, early: bool = False) -> Rig:
    """The bridge with `TurnLanguages` of Arabic and English on `classifier`, the call named
    Arabic, fed by `body`."""
    events, session = CallEvents(SYSTEM_CLOCK), Recorder()
    report = FailureReport(call_id="call-1", emit=lambda event: None, clock=SYSTEM_CLOCK)
    port = FakeSpeechToText(["heard"] * 8, delay_s=0.05)
    languages = TurnLanguages(
        clock=SYSTEM_CLOCK, classifier=classifier, codes=("ar", "en"), rule=RULE
    )
    stt = TurnSTTBridge(
        stt=port,
        events=events,
        report=report,
        start_s=START_S,
        early=early,
        prompts=PROMPTS,
        languages=languages,
    )
    rig = Rig(session, stt, port, classifier)

    async def feed(worker: PipelineWorker) -> None:
        events.start(session)
        stt.listen_in("ar")
        await body(rig, worker)
        await asyncio.sleep(0.1)
        await events.close()

    asyncio.run(run_pipeline([stt], feed))
    return rig


def _opened(speech_s: float) -> list[Frame]:
    """A turn's pre-roll of silence, the detector's start, the turn's start and `speech_s` of
    speech."""
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


def _resumed(speech_s: float) -> list[Frame]:
    from pipecat.frames.frames import VADUserStartedSpeakingFrame

    return [
        *audio_frames(START_S),
        VADUserStartedSpeakingFrame(start_secs=START_S),
        HoldResumedFrame(),
        *audio_frames(speech_s),
    ]


async def _queue(worker: PipelineWorker, frames: Sequence[Frame]) -> None:
    for frame in frames:
        await worker.queue_frame(frame)


async def _closed(rig: Rig, worker: PipelineWorker, turns: int = 1) -> None:
    """The turn ends; return once `turns` turns have their own transcript."""
    from pipecat.frames.frames import UserStoppedSpeakingFrame

    await _queue(worker, [*audio_frames(0.2, loud=False), UserStoppedSpeakingFrame()])

    def own() -> list[Transcribed]:
        return [e for e in rig.session.of(Transcribed) if e.part == "turn"]

    await until(lambda: len(own()) >= turns)


def test_classification_starts_at_from_s_of_the_speechs_bytes_once_a_turn() -> None:
    """Five seconds of speech queued at once, far faster than real time: one classification,
    of the 2.0 s from the speech's first byte, the call's two codes asked."""
    classifier = FakeLanguageClassifier([ENGLISH])

    async def body(rig: Rig, worker: PipelineWorker) -> None:
        await _queue(worker, _opened(5.0))
        await until(lambda: rig.classifier.answered == 1)
        await _queue(worker, _stopped())
        await _closed(rig, worker)

    rig = _run(classifier, body)
    ((clip, among),) = rig.classifier.calls
    assert among == ("ar", "en") and clip.sample_rate == 16_000
    assert clip.pcm16 == (tone(START_S, 16_000) + tone(5.0, 16_000))[: 2 * 32_000]
    (sent,) = rig.sent()
    assert (sent.language, sent.language_by, sent.share) == ("en", "classified", 0.9)
    assert rig.port.calls[0][1:] == ("en", "english prompt")


def test_a_turn_shorter_than_from_s_never_asks_and_is_short() -> None:
    classifier = FakeLanguageClassifier([ENGLISH])

    async def body(rig: Rig, worker: PipelineWorker) -> None:
        await _queue(worker, [*_opened(1.0 - START_S), *_stopped()])
        await _closed(rig, worker)

    rig = _run(classifier, body)
    assert rig.classifier.calls == []
    (sent,) = rig.sent()
    assert (sent.language, sent.language_by, sent.share, sent.verdict_at) == (
        "ar",
        "short",
        None,
        None,
    )
    assert rig.port.calls[0][1:] == ("ar", "arabic prompt")


def test_the_held_request_names_the_verdict_in_hand_and_a_later_short_turn_keeps_it() -> None:
    classifier = FakeLanguageClassifier([ENGLISH])

    async def body(rig: Rig, worker: PipelineWorker) -> None:
        await _queue(worker, _opened(2.5))
        await until(lambda: rig.classifier.answered == 1)
        await _queue(worker, [*_stopped(), TurnHeldFrame()])
        await _closed(rig, worker)
        await _queue(worker, [*_opened(0.8), *_stopped(), TurnHeldFrame()])
        await _closed(rig, worker, turns=2)

    rig = _run(classifier, body, early=True)
    first, second = rig.sent("held")
    assert (first.language, first.language_by, first.share) == ("en", "classified", 0.9)
    assert first.verdict_at is not None and first.verdict_at <= first.at
    assert rig.sent("turn") == []  # each turn reuses its held result, with no request
    assert (second.language, second.language_by) == ("en", "short")  # Q17
    assert [call[1:] for call in rig.port.calls] == [("en", "english prompt")] * 2


def test_a_verdict_still_running_is_late_and_the_held_request_goes_with_turn_held() -> None:
    gate = asyncio.Event()
    classifier = FakeLanguageClassifier([ENGLISH], gate=gate)

    async def body(rig: Rig, worker: PipelineWorker) -> None:
        await _queue(worker, _opened(2.5))
        await until(lambda: len(rig.classifier.calls) == 1)
        await _queue(worker, [*_stopped(), TurnHeldFrame()])
        await until(lambda: bool(rig.sent("held")))  # the verdict still held back
        await _closed(rig, worker)
        gate.set()

    rig = _run(classifier, body, early=True)
    (held,) = rig.sent("held")
    assert (held.language, held.language_by, held.share) == ("ar", "late", None)
    kinds = [type(e).__name__ for e in rig.session.events]
    assert kinds[kinds.index("TurnHeld") + 1] == "Transcribing"
    (began,) = rig.session.of(TurnHeld)
    assert held.at - began.at < 0.05 and rig.classifier.answered == 1  # it came after


def test_a_classifier_that_blocks_two_seconds_delays_no_frame_and_no_request() -> None:
    """At real-time pace, with a 20 ms ticker on the loop: the classifier works on a thread for
    2 s from the turn's second second; the turn closes and its request goes, `late`, while it
    works, and no tick is late by more than voice's bound."""
    from pipecat.frames.frames import UserStoppedSpeakingFrame

    classifier = FakeLanguageClassifier([ENGLISH], block_s=2.0)
    worst: list[float] = []
    closed_at: list[float] = []

    async def ticker(stop: asyncio.Event) -> None:
        while not stop.is_set():
            due = time.monotonic() + 0.02
            await asyncio.sleep(0.02)
            worst.append(time.monotonic() - due)

    async def body(rig: Rig, worker: PipelineWorker) -> None:
        stop = asyncio.Event()
        ticks = asyncio.create_task(ticker(stop))
        for frame in [*_opened(2.5), *_stopped(), TurnHeldFrame()]:
            await worker.queue_frame(frame)
            await asyncio.sleep(0.02 if hasattr(frame, "audio") else 0)
        closed_at.append(time.monotonic())
        await worker.queue_frame(UserStoppedSpeakingFrame())
        await until(lambda: bool(rig.sent("turn")))
        sent_at = time.monotonic()
        assert rig.classifier.answered == 0 and sent_at - closed_at[0] < 0.5
        await until(lambda: rig.classifier.answered == 1, timeout=5)
        stop.set()
        await ticks

    rig = _run(classifier, body)
    (sent,) = rig.sent("turn")
    assert (sent.language, sent.language_by) == ("ar", "late")
    assert max(worst) < TICKER_BOUND_S
    (closed,) = rig.session.of(TurnClosed)
    assert closed.at <= sent.at


def test_an_overlaps_parts_name_the_current_language_with_a_verdict_in_hand() -> None:
    classifier = FakeLanguageClassifier([ENGLISH])

    async def body(rig: Rig, worker: PipelineWorker) -> None:
        await _queue(worker, _opened(2.5))
        await until(lambda: rig.classifier.answered == 1)
        rig.stt.hear_overlap(0, 750)
        await _queue(worker, _stopped())
        await _closed(rig, worker)
        await _queue(worker, [*_opened(0.8), *_stopped()])
        await _closed(rig, worker, turns=2)

    rig = _run(classifier, body)
    parts = [(e.turn_id, e.part, e.language, e.language_by) for e in rig.sent()]
    assert parts == [
        (0, "window", "ar", "overlap"),
        (0, "overlap", "ar", "overlap"),
        (1, "turn", "ar", "short"),  # an overlap's verdict never moved the call's language
    ]


def test_an_echo_calls_hold_decides_the_turns_own_request() -> None:
    """With no talker the bridge sends no held request, but the hold's start still decides:
    the verdict that lands in the hold is not the turn's, which goes `late`, and no event is
    added."""
    gate = asyncio.Event()
    classifier = FakeLanguageClassifier([ENGLISH], gate=gate)

    async def body(rig: Rig, worker: PipelineWorker) -> None:
        await _queue(worker, _opened(2.5))
        await until(lambda: len(rig.classifier.calls) == 1)
        await _queue(worker, [*_stopped(), TurnHeldFrame()])
        await asyncio.sleep(0.1)
        gate.set()
        await until(lambda: rig.classifier.answered == 1)
        await _closed(rig, worker)

    rig = _run(classifier, body)
    (sent,) = rig.sent()
    assert (sent.part, sent.language, sent.language_by) == ("turn", "ar", "late")
    assert rig.session.of(TurnHeld) == []


def test_a_turn_with_no_hold_decides_at_its_close() -> None:
    classifier = FakeLanguageClassifier([ENGLISH])

    async def body(rig: Rig, worker: PipelineWorker) -> None:
        await _queue(worker, _opened(2.5))
        await until(lambda: rig.classifier.answered == 1)
        await _queue(worker, _stopped())
        await _closed(rig, worker)

    rig = _run(classifier, body)
    (sent,) = rig.sent()
    assert (sent.part, sent.language, sent.language_by) == ("turn", "en", "classified")


def test_resumed_speech_decides_again_with_the_verdict_that_came_meanwhile() -> None:
    gate = asyncio.Event()
    classifier = FakeLanguageClassifier([ENGLISH], gate=gate)

    async def body(rig: Rig, worker: PipelineWorker) -> None:
        await _queue(worker, _opened(2.5))
        await until(lambda: len(rig.classifier.calls) == 1)
        await _queue(worker, [*_stopped(), TurnHeldFrame()])
        await until(lambda: len(rig.sent("held")) == 1)
        gate.set()
        await until(lambda: rig.classifier.answered == 1)
        await _queue(worker, [*_resumed(0.6), *_stopped(), TurnHeldFrame()])
        await until(lambda: len(rig.sent("held")) == 2)
        await _closed(rig, worker)

    rig = _run(classifier, body, early=True)
    first, second = rig.sent("held")
    assert (first.language, first.language_by) == ("ar", "late")
    assert (second.language, second.language_by) == ("en", "classified")
    assert len(rig.classifier.calls) == 1  # once a turn


def test_drop_cancels_the_classification_and_its_result_is_never_used() -> None:
    gate = asyncio.Event()
    classifier = FakeLanguageClassifier([ENGLISH], gate=gate)

    async def body(rig: Rig, worker: PipelineWorker) -> None:
        await _queue(worker, _opened(2.5))
        await until(lambda: len(rig.classifier.calls) == 1)
        await rig.stt.drop()
        gate.set()
        await asyncio.sleep(0.1)

    rig = _run(classifier, body)
    assert rig.classifier.cancelled == 1 and rig.classifier.answered == 0
    assert rig.sent() == []


@pytest.mark.parametrize(
    ("answer", "by"),
    [
        (None, "busy"),
        (ProviderError("server_error", True), "failed"),
        (object(), "failed"),  # an answer that does not parse
        ({"ar": 0.4, "en": 0.6}, "unsure"),
    ],
)
def test_a_busy_failing_or_unsure_classifier_keeps_the_language(answer: Answer, by: str) -> None:
    classifier = FakeLanguageClassifier([answer])

    async def body(rig: Rig, worker: PipelineWorker) -> None:
        await _queue(worker, _opened(2.5))
        await until(lambda: rig.classifier.answered == 1)
        await _queue(worker, _stopped())
        await _closed(rig, worker)

    rig = _run(classifier, body)
    (sent,) = rig.sent()
    assert (sent.language, sent.language_by) == ("ar", by)
    assert sent.share == (0.6 if by == "unsure" else None)

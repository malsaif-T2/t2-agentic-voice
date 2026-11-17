"""The held request sent at the detector's stop (`turns.early_at_stop`; voice/stt_held.py) under
each way a call follows the caller's language (`stt.live_language`): under `classified` the
turn's language is decided at the stop, undone when Smart Turn calls the pause unfinished, and
decided again at the next stop with the verdict that came meanwhile; under `detected` a long
turn's request goes twice at the stop, both dropped at once by an unfinished pause (running out
unhanded, so the dropped pair moves nothing), and the kept pair's detected language moves the
call; under `hinted` the kept answer's move holds for the turn's reuse of it, the dropped answer
moving nothing. Each turn's words are answered once."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

from t2_agentic_voice.domain.language_hint import HintRule
from t2_agentic_voice.domain.language_switch import DetectRule
from t2_agentic_voice.domain.ports.speech_to_text import SpeechToText
from t2_agentic_voice.domain.turn_language import LanguageRule
from t2_agentic_voice.voice.pipecat_events import FailureReport
from t2_agentic_voice.voice.session.io import SYSTEM_CLOCK
from t2_agentic_voice.voice.session.session_events import Transcribed, Transcribing
from t2_agentic_voice.voice.session_bridge import EventStream
from t2_agentic_voice.voice.stt_bridge import TurnSTTBridge
from t2_agentic_voice.voice.stt_language import TurnLanguages
from t2_agentic_voice.voice.stt_requests import SwitchRule
from t2_agentic_voice.voice.turn_hold import TurnHeldFrame, TurnUnfinishedFrame

from tests.t2_agentic_voice.language_fakes import FakeLanguageClassifier
from tests.t2_agentic_voice.voice.kit import Recorder, run_pipeline, until
from tests.t2_agentic_voice.voice.test_stt_at_stop import _closed, _opened, _resumed, _stopped
from tests.t2_agentic_voice.voice.test_stt_detect import PROMPTS, QUESTION, TRANSLATED, Whisper
from tests.t2_agentic_voice.voice.test_stt_hinted import Scribe

if TYPE_CHECKING:
    from pipecat.frames.frames import Frame
    from pipecat.pipeline.worker import PipelineWorker

Body = Callable[[Recorder, "PipelineWorker"], Awaitable[None]]


def _run(
    port: SpeechToText,
    body: Body,
    *,
    languages: TurnLanguages | None = None,
    detect: SwitchRule | None = None,
) -> Recorder:
    """A talker call's bridge, its held request at the stop, the call named Arabic, fed by
    `body`."""
    events, session = EventStream(SYSTEM_CLOCK), Recorder()
    report = FailureReport(call_id="call-1", emit=lambda event: None, clock=SYSTEM_CLOCK)
    stt = TurnSTTBridge(
        stt=port,
        events=events,
        report=report,
        start_s=0.2,
        early=True,
        prompts=PROMPTS,
        languages=languages,
        detect=detect,
        at_stop=True,
    )

    async def feed(worker: PipelineWorker) -> None:
        events.start(session)
        stt.listen_in("ar")
        await body(session, worker)
        await asyncio.sleep(0.2)
        await events.close()

    asyncio.run(run_pipeline([stt], feed))
    return session


async def _queue(worker: PipelineWorker, *frames: Frame) -> None:
    for frame in frames:
        await worker.queue_frame(frame)


async def _held_turn(session: Recorder, worker: PipelineWorker, turns: int = 1) -> None:
    """The open turn's next pause is called complete, and the turn ends: return once `turns`
    turns have their own transcript."""
    await _queue(worker, *_stopped())
    await asyncio.sleep(0.05)
    await _queue(worker, TurnHeldFrame(), *_closed())
    await until(lambda: len(_own(session)) >= turns)


def _own(session: Recorder) -> list[Transcribed]:
    return [e for e in session.of(Transcribed) if e.part == "turn"]


def _held(session: Recorder) -> list[Transcribed]:
    return [e for e in session.of(Transcribed) if e.part == "held"]


def test_classified_decides_at_the_stop_and_again_after_an_unfinished_pause() -> None:
    gate = asyncio.Event()
    classifier = FakeLanguageClassifier([{"ar": 0.1, "en": 0.9}], gate=gate)
    rule = LanguageRule(from_s=2.0, min_share=0.7)
    languages = TurnLanguages(
        clock=SYSTEM_CLOCK, classifier=classifier, codes=("ar", "en"), rule=rule
    )

    async def body(session: Recorder, worker: PipelineWorker) -> None:
        await _queue(worker, *_opened(2.5))
        await until(lambda: len(classifier.calls) == 1)
        await _queue(worker, *_stopped())
        await until(lambda: bool(session.of(Transcribing)))  # the verdict still gated
        await _queue(worker, TurnUnfinishedFrame())
        gate.set()
        await until(lambda: classifier.answered == 1)
        await _queue(worker, *_resumed(held=False))
        await _held_turn(session, worker)

    port = Whisper(told=["the first part", "the whole turn"], delay_s=0.5)  # the first runs out
    session = _run(port, body, languages=languages)
    first, second = session.of(Transcribing)
    assert (first.part, first.language, first.language_by) == ("held", "ar", "late")
    assert (second.part, second.language, second.language_by) == ("held", "en", "classified")
    assert first.decided_at is not None and second.decided_at is not None
    assert second.decided_at > first.decided_at  # decided again, at the second stop
    (held,) = _held(session)
    assert held.transcript is not None and held.transcript.text == "the whole turn"


def test_detected_sends_twice_at_the_stop_and_an_unfinished_pause_drops_both() -> None:
    told = ["Which", TRANSLATED, "fine"]  # the dropped pair's answers first: they run out
    port = Whisper(told=told, detected=[("Which", "English"), (QUESTION, "English")], delay_s=0.3)
    in_flight: list[int] = []

    async def body(session: Recorder, worker: PipelineWorker) -> None:
        await _queue(worker, *_opened(2.0), *_stopped())
        await until(lambda: port.held == 2)  # the named and the detecting request, at once
        await _queue(worker, TurnUnfinishedFrame())
        await asyncio.sleep(0.1)
        in_flight.append(port.held)
        await _queue(worker, *_resumed(held=False))
        await _held_turn(session, worker)
        await _queue(worker, *_opened(0.4))
        await _held_turn(session, worker, turns=2)

    session = _run(port, body, detect=DetectRule(from_s=1.2, codes=("ar", "en")))
    assert in_flight == [2]  # both still running after the verdict, never cancelled
    assert port.calls[:4] == [("ar", "arabic prompt"), (None, None)] * 2
    (held, short) = _held(session)
    assert held.switched and _own(session)[0].switched  # the kept pair moved the call
    assert port.calls[-1] == ("en", "english prompt") and not short.switched


def test_hinted_keeps_the_held_answers_move_and_the_dropped_one_moves_nothing() -> None:
    port = Scribe(answers=[("Which", "en", 0.5), (QUESTION, "en", 0.95), ("fine", "en", 0.9)])
    rule = HintRule(min_probability=0.8, codes=("ar", "en"))

    async def body(session: Recorder, worker: PipelineWorker) -> None:
        await _queue(worker, *_opened(2.0), *_stopped())
        await until(lambda: len(port.calls) == 1)
        await _queue(worker, TurnUnfinishedFrame(), *_resumed(held=False))
        await _held_turn(session, worker)
        await _queue(worker, *_opened(0.4))
        await _held_turn(session, worker, turns=2)

    session = _run(port, body, detect=rule)
    assert port.calls[:2] == [("ar", "arabic prompt", ("en",))] * 2  # the drop moved nothing
    held, short = _held(session)
    assert held.transcript is not None and held.transcript.text == QUESTION and held.switched
    assert _own(session)[0].switched and not short.switched
    assert port.calls[-1] == ("en", "english prompt", ("ar",))

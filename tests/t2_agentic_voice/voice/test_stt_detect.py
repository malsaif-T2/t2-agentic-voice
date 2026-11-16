"""Whisper's own detection in the speech-to-text bridge, under `stt.live_language = "detected"`
(voice/stt_requests.py, voice/stt_bridge.py; domain/language_switch.py's rule), against a fake
Whisper that writes each request in the language it is told, or, told none, in the one it
detects: a turn with `detect_from_s` of voiced speech goes twice at once, the second naming no
language and carrying no prompt; an English question in an Arabic call is the turn's words and
moves the call, so the next short turn is sent in English; a short reply heard as English moves
nothing; a turn whose voiced speech is short goes once, however long the silence after it (the
classifier's length gate counted silence: D-086's amendment); the held request detects and the
turn's own reuse of it moves the call; a failed detecting request changes nothing and logs no
words; and by default (`session`) a long turn goes once (GP-18)."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import pytest
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.errors import ProviderError
from t2_agentic_voice.core.settings.stt import SttSettings
from t2_agentic_voice.domain.language_switch import DetectRule
from t2_agentic_voice.domain.ports.speech_to_text import AudioClip, Transcript
from t2_agentic_voice.voice.pipecat_events import FailureReport
from t2_agentic_voice.voice.session.io import SYSTEM_CLOCK
from t2_agentic_voice.voice.session.session_events import Transcribed, Transcribing
from t2_agentic_voice.voice.session_bridge import EventStream
from t2_agentic_voice.voice.stt_bridge import TurnSTTBridge
from t2_agentic_voice.voice.stt_requests import detect_rule
from t2_agentic_voice.voice.turn_hold import TurnHeldFrame

from tests.leaks import holding, shown
from tests.t2_agentic_voice.fakes import FAKE_FLOW
from tests.t2_agentic_voice.session_fakes import AGENT
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

RULE = DetectRule(from_s=1.2, codes=("ar", "en"))
PROMPTS = {"ar": "arabic prompt", "en": "english prompt"}
QUESTION = "Which flights go to Dubai tomorrow?"
# The same question, told Arabic: fluent Arabic, wrongly (what Whisper does).
TRANSLATED = "ما هي الرحلات الى دبي"
YES = "ايه"  # eh, yes: alef, yeh, heh


@dataclass
class Whisper:
    """A fake Whisper: told a language, it writes the next of `told`; told none, the next of
    `detected` (text and the language it heard, or an error), each after `delay_s`; it records
    each request's language and prompt, and the most requests it held at once."""

    told: list[str]
    detected: list[tuple[str, str] | ProviderError] = field(default_factory=list)
    delay_s: float = 0.1
    calls: list[tuple[str | None, str | None]] = field(default_factory=list)
    held: int = 0
    most: int = 0
    name: str = "fake"
    data_flow = FAKE_FLOW

    async def transcribe(
        self, clip: AudioClip, *, language: str | None, prompt: str | None
    ) -> Transcript:
        self.calls.append((language, prompt))
        self.held += 1
        self.most = max(self.most, self.held)
        try:
            await asyncio.sleep(self.delay_s)
        finally:
            self.held -= 1
        if language is not None:
            return Transcript(text=self.told.pop(0), language=language, billed_seconds=10.0)
        entry = self.detected.pop(0)
        if isinstance(entry, ProviderError):
            raise entry
        return Transcript(text=entry[0], language=entry[1], billed_seconds=10.0)

    async def aclose(self) -> None:
        return None


Body = Callable[[Recorder, "PipelineWorker"], Awaitable[None]]


def _run(
    port: Whisper, body: Body, *, detect: DetectRule | None = RULE, early: bool = False
) -> Recorder:
    """The bridge with `port`, the call named Arabic, fed by `body`."""
    events, session = EventStream(SYSTEM_CLOCK), Recorder()
    report = FailureReport(call_id="call-1", emit=lambda event: None, clock=SYSTEM_CLOCK)
    stt = TurnSTTBridge(
        stt=port,
        events=events,
        report=report,
        start_s=START_S,
        early=early,
        prompts=PROMPTS,
        detect=detect,
    )

    async def feed(worker: PipelineWorker) -> None:
        events.start(session)
        stt.listen_in("ar")
        await body(session, worker)
        await asyncio.sleep(0.1)
        await events.close()

    asyncio.run(run_pipeline([stt], feed))
    return session


def _turn(speech_s: float, *, silence_s: float = 0.2, held: bool = False) -> list[Frame]:
    """A turn: a pre-roll of silence, `speech_s` of speech, the detector's stop, `silence_s` of
    silence (the fallback's, when long), then its end; held first when `held`."""
    from pipecat.frames.frames import (
        UserStartedSpeakingFrame,
        UserStoppedSpeakingFrame,
        VADUserStartedSpeakingFrame,
        VADUserStoppedSpeakingFrame,
    )

    return [
        *audio_frames(1.0, loud=False),
        *audio_frames(START_S),
        VADUserStartedSpeakingFrame(start_secs=START_S),
        UserStartedSpeakingFrame(),
        *audio_frames(speech_s),
        *audio_frames(STOP_S, loud=False),
        VADUserStoppedSpeakingFrame(stop_secs=STOP_S),
        *([TurnHeldFrame()] if held else []),
        *audio_frames(silence_s, loud=False),
        UserStoppedSpeakingFrame(),
    ]


async def _say(session: Recorder, worker: PipelineWorker, frames: Sequence[Frame]) -> None:
    """Queue a turn's frames and wait for its own transcript."""
    count = len(_own(session))
    for frame in frames:
        await worker.queue_frame(frame)
    await until(lambda: len(_own(session)) > count)


def _own(session: Recorder) -> list[Transcribed]:
    return [e for e in session.of(Transcribed) if e.part == "turn"]


def test_an_english_question_in_an_arabic_call_moves_it_and_the_next_yes_goes_in_english() -> None:
    port = Whisper(told=[TRANSLATED, "yes"], detected=[(QUESTION, "English")])

    async def body(session: Recorder, worker: PipelineWorker) -> None:
        await _say(session, worker, _turn(2.0))
        await _say(session, worker, _turn(0.4))

    session = _run(port, body)
    assert port.calls == [("ar", "arabic prompt"), (None, None), ("en", "english prompt")]
    assert port.most == 2  # both of the long turn's requests at once
    first, second = _own(session)
    assert first.switched and first.transcript is not None
    assert (first.transcript.text, first.transcript.language) == (QUESTION, "en")
    assert not second.switched and second.transcript is not None
    assert second.transcript.language == "en"
    sent = [(e.turn_id, e.language, e.language_by) for e in session.of(Transcribing)]
    assert sent == [(0, "ar", "session"), (0, None, "detected"), (1, "en", "session")]


def test_a_short_reply_heard_as_the_other_language_moves_nothing() -> None:
    port = Whisper(told=[YES, "next"], detected=[("Yes, okay, sure.", "English")])

    async def body(session: Recorder, worker: PipelineWorker) -> None:
        await _say(session, worker, _turn(2.0))
        await _say(session, worker, _turn(0.4))

    session = _run(port, body)
    first, _ = _own(session)
    assert not first.switched and first.transcript is not None
    assert (first.transcript.text, first.transcript.language) == (YES, "ar")
    assert port.calls[-1] == ("ar", "arabic prompt")


def test_a_short_word_before_a_long_silence_goes_once() -> None:
    """0.7 s of speech then the 3 s fallback's silence: 1.0 s of voiced speech, under 1.2 s."""
    port = Whisper(told=["okay"])

    async def body(session: Recorder, worker: PipelineWorker) -> None:
        await _say(session, worker, _turn(0.7, silence_s=3.0))

    _run(port, body)
    assert port.calls == [("ar", "arabic prompt")]


def test_the_held_request_detects_and_the_turns_own_reuse_moves_the_call() -> None:
    port = Whisper(told=[TRANSLATED, "fine"], detected=[(QUESTION, "English")])

    async def body(session: Recorder, worker: PipelineWorker) -> None:
        await _say(session, worker, _turn(2.0, held=True))
        await _say(session, worker, _turn(0.4))

    session = _run(port, body, early=True)
    held = [e for e in session.of(Transcribed) if e.part == "held"]
    assert [e.switched for e in held] == [True]
    assert _own(session)[0].switched
    assert port.calls[-1] == ("en", "english prompt")


def test_a_failed_detecting_request_changes_nothing_and_logs_no_words(
    caplog: pytest.LogCaptureFixture,
) -> None:
    error = ProviderError("timeout", retryable=True)
    port = Whisper(told=[TRANSLATED], detected=[error])

    async def body(session: Recorder, worker: PipelineWorker) -> None:
        await _say(session, worker, _turn(2.0))

    session = _run(port, body)
    (own,) = _own(session)
    assert not own.switched and own.failure is None and own.transcript is not None
    assert own.transcript.text == TRANSLATED
    assert [r.getMessage() for r in caplog.records].count("stt_detect_failed") == 1
    assert holding(TRANSLATED, shown(caplog=caplog)) == []


def test_by_default_a_long_turn_goes_once_in_the_calls_language() -> None:
    """GP-18: `session` stays the library's default, and no call of it detects."""
    assert SttSettings().live_language == "session" and SttSettings().detect_from_s == 1.2
    assert detect_rule(AGENT, VoiceSettings(env="test")) is None
    detected = VoiceSettings(env="test", stt=SttSettings(live_language="detected"))
    rule = detect_rule(AGENT, detected)
    assert rule is not None and (rule.from_s, set(rule.codes)) == (1.2, {"ar", "en"})
    port = Whisper(told=[TRANSLATED])

    async def body(session: Recorder, worker: PipelineWorker) -> None:
        await _say(session, worker, _turn(2.0))

    _run(port, body, detect=None)
    assert port.calls == [("ar", "arabic prompt")]

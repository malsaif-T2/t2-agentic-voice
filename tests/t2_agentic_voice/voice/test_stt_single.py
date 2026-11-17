"""The speech-to-text bridge under `stt.live_language = "single"` (voice/stt_requests.py,
domain/language_hint.py's `SingleRule`; D-117), against a fake Scribe that answers each request
with the next of its answers, the language it heard and its probability, as the adapter does: a
turn of `detect_from_s` voiced speech or more goes once, naming no language with the call
language's prompt and no other language, and its answer is the turn's words; an English
question heard surely in an Arabic call moves the call, so the next turn names English; an
answer under the threshold, with no probability, in the call's own language or one the agent
does not speak, or a short reply, moves nothing and its words stand; a shorter turn, however
long the silence after it, goes once naming the call's language and never moves the call; the
held request's move holds for the turn's reuse of it; a failed request is the turn's, with no
second request; an overlap's parts name the call's language and never move it; never two
requests at once; and the rule is given only on a provider that reports a language probability,
the default unchanged (GP-18), the start saying once when single runs as session."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import pytest
from t2_agentic_voice.api.providers import Providers, opened
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.errors import ProviderError
from t2_agentic_voice.core.settings.stt import SttSettings
from t2_agentic_voice.core.settings.words import LanguageCode
from t2_agentic_voice.domain.language_hint import HintRule, SingleRule
from t2_agentic_voice.domain.language_switch import DetectRule
from t2_agentic_voice.domain.ports.speech_to_text import AudioClip, Transcript
from t2_agentic_voice.voice.pipecat_events import FailureReport
from t2_agentic_voice.voice.session.io import SYSTEM_CLOCK
from t2_agentic_voice.voice.session.session_events import Transcribed, Transcribing
from t2_agentic_voice.voice.session_bridge import EventStream
from t2_agentic_voice.voice.stt_bridge import TurnSTTBridge
from t2_agentic_voice.voice.stt_requests import detect_rule

from tests.t2_agentic_voice.fakes import FAKE_FLOW, FakeSpeechToText, FakeTextToSpeech
from tests.t2_agentic_voice.session_fakes import AGENT
from tests.t2_agentic_voice.voice.kit import START_S, Recorder, run_pipeline, until
from tests.t2_agentic_voice.voice.test_stt_detect import PROMPTS, QUESTION, YES, _own, _say, _turn
from tests.t2_agentic_voice.voice.test_stt_overlap import Marking, _end, _opening, _speech

if TYPE_CHECKING:
    from pipecat.frames.frames import Frame
    from pipecat.pipeline.worker import PipelineWorker

CODES: tuple[LanguageCode, ...] = ("ar", "en")
RULE = SingleRule(
    gate=DetectRule(from_s=1.2, codes=CODES), hint=HintRule(min_probability=0.8, codes=CODES)
)
WHERE = "وين الرحلات بكره"  # wain al-rihlat bukra, where are tomorrow's flights
Heard = tuple[str, str | None, float | None]  # the text, the language heard, its probability


@dataclass
class Scribe:
    """A fake Scribe: each request answered with the next of `answers` (or its error), its
    `language` the request's, or the one heard for a request naming none (the adapter's), and
    the language heard in `heard_language`; each request's language, prompt and other languages
    recorded, and the most requests it held at once."""

    answers: list[Heard | ProviderError]
    calls: list[tuple[str | None, str | None, tuple[str, ...]]] = field(default_factory=list)
    held: int = 0
    most: int = 0
    name: str = "fake"
    data_flow = FAKE_FLOW

    async def transcribe(
        self, clip: AudioClip, *, language: str | None, prompt: str | None
    ) -> Transcript:
        self.calls.append((language, prompt, clip.other_languages))
        self.held += 1
        self.most = max(self.most, self.held)
        try:
            await asyncio.sleep(0.05)
        finally:
            self.held -= 1
        entry = self.answers.pop(0)
        if isinstance(entry, ProviderError):
            raise entry
        text, heard, probability = entry
        return Transcript(
            text=text,
            language=language or heard,
            heard_language=heard,
            language_probability=probability,
        )

    async def aclose(self) -> None:
        return None


def _bridge(port: Scribe, events: EventStream, *, held: bool = False) -> TurnSTTBridge:
    report = FailureReport(call_id="call-1", emit=lambda event: None, clock=SYSTEM_CLOCK)
    return TurnSTTBridge(
        stt=port,
        events=events,
        report=report,
        start_s=START_S,
        early=held,
        prompts=PROMPTS,
        detect=RULE,
    )


def _run(port: Scribe, *turns: Sequence[Frame], held: bool = False) -> Recorder:
    """The bridge under `RULE`, the call named Arabic, fed these turns."""
    events, session = EventStream(SYSTEM_CLOCK), Recorder()
    stt = _bridge(port, events, held=held)

    async def feed(worker: PipelineWorker) -> None:
        events.start(session)
        stt.listen_in("ar")
        for frames in turns:
            await _say(session, worker, frames)
        await asyncio.sleep(0.1)
        await events.close()

    asyncio.run(run_pipeline([stt], feed))
    return session


def test_a_long_english_question_goes_once_naming_none_and_moves_the_call() -> None:
    port = Scribe(answers=[(QUESTION, "en", 0.97), ("yes", "en", 0.6)])
    session = _run(port, _turn(2.0), _turn(0.4))
    assert port.calls == [(None, "arabic prompt", ()), ("en", "english prompt", ())]
    assert port.most == 1  # never two requests at once
    first, second = _own(session)
    assert first.switched and first.transcript is not None
    assert (first.transcript.text, first.transcript.language) == (QUESTION, "en")
    assert not second.switched and second.transcript is not None
    assert second.transcript.language == "en"
    sent = [(e.turn_id, e.language, e.language_by) for e in session.of(Transcribing)]
    assert sent == [(0, "ar", "session"), (1, "en", "session")]  # one request a turn


@pytest.mark.parametrize(
    "answer",
    [
        (QUESTION, "en", 0.79),
        (QUESTION, "en", None),
        ("Yes, okay, sure.", "en", 0.99),
        (WHERE, "ar", 0.99),
        (QUESTION, "fr", 0.99),
        (QUESTION, None, None),
    ],
    ids=[
        "under the threshold",
        "no probability",
        "a short reply",
        "the call's own language",
        "a language the agent does not speak",
        "no language heard",
    ],
)
def test_an_answer_that_does_not_move_the_call_is_still_the_turns_words(answer: Heard) -> None:
    port = Scribe(answers=[answer, (YES, "ar", 0.9)])
    session = _run(port, _turn(2.0), _turn(0.4))
    first, _ = _own(session)
    assert not first.switched and first.transcript is not None
    assert (first.transcript.text, first.transcript.language) == (answer[0], "ar")
    assert port.calls == [(None, "arabic prompt", ()), ("ar", "arabic prompt", ())]


@pytest.mark.parametrize(
    ("speech_s", "silence_s"), [(0.4, 0.2), (0.7, 3.0)], ids=["short", "short before a silence"]
)
def test_a_shorter_turn_names_the_calls_language_and_never_moves_it(
    speech_s: float, silence_s: float
) -> None:
    """Under 1.2 s of voiced speech (0.7 s then the fallback's 3 s of silence is 1.0 s voiced):
    one request in the call's language, an English question heard surely in it moving nothing."""
    port = Scribe(answers=[(QUESTION, "en", 0.99), (YES, "ar", 0.9)])
    session = _run(port, _turn(speech_s, silence_s=silence_s), _turn(0.4))
    first, _ = _own(session)
    assert not first.switched and first.transcript is not None
    assert first.transcript.language == "ar"
    assert port.calls == [("ar", "arabic prompt", ())] * 2


def test_the_held_requests_move_holds_for_the_turns_reuse_of_it() -> None:
    port = Scribe(answers=[(QUESTION, "en", 0.95), ("fine thanks", "en", 0.9)])
    session = _run(port, _turn(2.0, held=True), _turn(0.4, held=True), held=True)
    held = [e for e in session.of(Transcribed) if e.part == "held"]
    assert [e.switched for e in held] == [True, False]
    assert _own(session)[0].switched
    assert port.calls == [(None, "arabic prompt", ()), ("en", "english prompt", ())]


def test_a_failed_request_is_the_turns_and_sends_no_second_one() -> None:
    port = Scribe(answers=[ProviderError("timeout", retryable=True), (YES, "ar", 0.9)])
    session = _run(port, _turn(2.0), _turn(0.4))
    first, _ = _own(session)
    assert (first.switched, first.transcript, first.failure) == (False, None, "timeout")
    assert port.calls == [(None, "arabic prompt", ()), ("ar", "arabic prompt", ())]


def test_an_overlaps_parts_name_the_calls_language_and_never_move_it() -> None:
    """A long overlap over a reply: its window and its overlap part, the turn's own reusing the
    overlap's, each named Arabic though Scribe hears an English question surely."""
    port = Scribe(answers=[(QUESTION, "en", 0.99)] * 2)
    events = EventStream(SYSTEM_CLOCK)
    stt = _bridge(port, events)
    session = Marking(stt, mark=True)

    async def feed(worker: PipelineWorker) -> None:
        events.start(session)
        stt.listen_in("ar")
        for frame in _opening():
            await worker.queue_frame(frame)
        await until(lambda: session.marked)
        for frame in [*_speech(2.0), *_end()]:
            await worker.queue_frame(frame)
        await until(lambda: "turn" in session.parts(Transcribed))
        await events.close()

    asyncio.run(run_pipeline([stt], feed))
    assert sorted(session.parts(Transcribed)) == ["overlap", "turn", "window"]
    assert port.calls == [("ar", "arabic prompt", ())] * 2
    assert not any(e.switched for e in session.of(Transcribed))


def test_the_rule_holds_only_on_a_provider_that_gives_a_probability() -> None:
    """GP-18: `session` stays the default; single on another provider runs as session."""
    assert SttSettings().live_language == "session"
    single = SttSettings(live_language="single", detect_from_s=1.5, switch_min_probability=0.7)
    rule = detect_rule(AGENT, VoiceSettings(env="test", stt=single))
    assert isinstance(rule, SingleRule)
    assert (rule.gate.from_s, rule.hint.min_probability) == (1.5, 0.7)
    assert set(rule.gate.codes) == set(rule.hint.codes) == {"ar", "en"}
    assert single.single_holds() and single.language_moves() and not single.hints()
    for provider in ("groq", "soniox", "cohere", "speechmatics"):
        other = SttSettings(live_language="single", provider=provider)
        assert detect_rule(AGENT, VoiceSettings(env="test", stt=other)) is None
        assert not other.single_holds() and not other.language_moves()
    assert not SttSettings(live_language="hinted").single_holds()


@pytest.mark.parametrize(
    ("stt", "warned"),
    [
        (SttSettings(live_language="single", provider="groq"), 1),
        (SttSettings(live_language="single"), 0),
        (SttSettings(live_language="hinted", provider="groq"), 0),
        (SttSettings(provider="groq"), 0),
    ],
    ids=["single on groq", "single on scribe", "hinted on groq", "session"],
)
def test_the_start_says_once_when_single_runs_as_session(
    stt: SttSettings, warned: int, caplog: pytest.LogCaptureFixture
) -> None:
    providers = Providers(stt=FakeSpeechToText(), tts=FakeTextToSpeech())

    async def start() -> None:
        async with AsyncExitStack() as stack:
            await opened(providers, AGENT, VoiceSettings(env="test", stt=stt), stack)

    asyncio.run(start())
    assert [r.getMessage() for r in caplog.records].count("single_as_session") == warned

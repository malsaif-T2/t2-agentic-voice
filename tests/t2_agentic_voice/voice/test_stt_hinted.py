"""The speech-to-text bridge under `stt.live_language = "hinted"` (voice/stt_requests.py,
domain/language_hint.py; D-115), against a fake Scribe that answers each request with the next
of its answers, the language it heard and its probability: every turn goes once, naming the
call's language with the agent's other one beside it; an English question heard surely in an
Arabic call is the turn's words and moves the call, so the next turn names English with Arabic
beside it; an answer under the threshold, or a short reply, moves nothing; the held request's
move holds for the turn's reuse of it; and the rule is given only on a provider that reports a
language probability, the default unchanged (GP-18)."""

from __future__ import annotations

import asyncio
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import pytest
from t2_agentic_voice.api.providers import Providers, opened
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.settings.stt import REPORTS_PROBABILITY, SttSettings
from t2_agentic_voice.domain.language_hint import HintRule
from t2_agentic_voice.domain.ports.speech_to_text import AudioClip, Transcript
from t2_agentic_voice.voice.pipecat_events import FailureReport
from t2_agentic_voice.voice.session.io import SYSTEM_CLOCK
from t2_agentic_voice.voice.session.session_events import Transcribed, Transcribing
from t2_agentic_voice.voice.session_bridge import EventStream
from t2_agentic_voice.voice.stt_bridge import TurnSTTBridge
from t2_agentic_voice.voice.stt_requests import detect_rule

from tests.t2_agentic_voice.fakes import FAKE_FLOW, FakeSpeechToText, FakeTextToSpeech
from tests.t2_agentic_voice.session_fakes import AGENT
from tests.t2_agentic_voice.voice.kit import START_S, Recorder, run_pipeline
from tests.t2_agentic_voice.voice.test_stt_detect import PROMPTS, QUESTION, YES, _own, _say, _turn

if TYPE_CHECKING:
    from pipecat.pipeline.worker import PipelineWorker

RULE = HintRule(min_probability=0.8, codes=("ar", "en"))
Heard = tuple[str, str | None, float | None]  # the text, the language heard, its probability


@dataclass
class Scribe:
    """A fake Scribe: each request answered with the next of `answers`, its `language` the
    request's and the language heard in `heard_language`; each request's language, prompt and
    other languages recorded."""

    answers: list[Heard]
    calls: list[tuple[str | None, str | None, tuple[str, ...]]] = field(default_factory=list)
    name: str = "fake"
    data_flow = FAKE_FLOW

    async def transcribe(
        self, clip: AudioClip, *, language: str | None, prompt: str | None
    ) -> Transcript:
        self.calls.append((language, prompt, clip.other_languages))
        text, heard, probability = self.answers.pop(0)
        return Transcript(
            text=text, language=language, heard_language=heard, language_probability=probability
        )

    async def aclose(self) -> None:
        return None


def _run(port: Scribe, *turns: float, held: bool = False) -> Recorder:
    """The bridge under `RULE`, the call named Arabic, fed turns of these seconds of speech."""
    events, session = EventStream(SYSTEM_CLOCK), Recorder()
    report = FailureReport(call_id="call-1", emit=lambda event: None, clock=SYSTEM_CLOCK)
    stt = TurnSTTBridge(
        stt=port,
        events=events,
        report=report,
        start_s=START_S,
        early=held,
        prompts=PROMPTS,
        detect=RULE,
    )

    async def feed(worker: PipelineWorker) -> None:
        events.start(session)
        stt.listen_in("ar")
        for speech_s in turns:
            await _say(session, worker, _turn(speech_s, held=held))
        await asyncio.sleep(0.1)
        await events.close()

    asyncio.run(run_pipeline([stt], feed))
    return session


def test_an_english_question_heard_surely_moves_the_call_on_one_request() -> None:
    port = Scribe(answers=[(QUESTION, "en", 0.97), ("yes", "en", 0.6)])
    session = _run(port, 2.0, 0.4)
    assert port.calls == [("ar", "arabic prompt", ("en",)), ("en", "english prompt", ("ar",))]
    first, second = _own(session)
    assert first.switched and first.transcript is not None
    assert (first.transcript.text, first.transcript.language) == (QUESTION, "en")
    assert not second.switched and second.transcript is not None
    assert second.transcript.language == "en"
    sent = [(e.turn_id, e.language, e.language_by) for e in session.of(Transcribing)]
    assert sent == [(0, "ar", "session"), (1, "en", "session")]  # one request a turn


@pytest.mark.parametrize(
    "answer",
    [(QUESTION, "en", 0.79), (QUESTION, "en", None), ("Yes, okay, sure.", "en", 0.99)],
    ids=["under the threshold", "no probability", "a short reply"],
)
def test_an_unsure_answer_or_a_short_reply_moves_nothing(answer: Heard) -> None:
    port = Scribe(answers=[answer, (YES, "ar", 0.9)])
    session = _run(port, 2.0, 0.4)
    first, _ = _own(session)
    assert not first.switched and first.transcript is not None
    assert first.transcript.language == "ar"
    assert port.calls[-1] == ("ar", "arabic prompt", ("en",))


def test_the_held_requests_move_holds_for_the_turns_reuse_of_it() -> None:
    port = Scribe(answers=[(QUESTION, "en", 0.95), ("fine thanks", "en", 0.9)])
    session = _run(port, 2.0, 0.4, held=True)
    held = [e for e in session.of(Transcribed) if e.part == "held"]
    assert [e.switched for e in held] == [True, False]
    assert _own(session)[0].switched
    assert port.calls[-1] == ("en", "english prompt", ("ar",))


def test_the_rule_holds_only_on_a_provider_that_gives_a_probability() -> None:
    """GP-18: `session` stays the default; hinted on another provider runs as session."""
    assert SttSettings().live_language == "session"
    assert SttSettings().switch_min_probability == 0.8
    assert {"elevenlabs"} == REPORTS_PROBABILITY
    hinted = SttSettings(live_language="hinted", switch_min_probability=0.9)
    rule = detect_rule(AGENT, VoiceSettings(env="test", stt=hinted))
    assert isinstance(rule, HintRule) and (rule.min_probability, set(rule.codes)) == (
        0.9,
        {"ar", "en"},
    )
    assert hinted.hints() and hinted.language_moves()
    for provider in ("groq", "soniox", "cohere"):
        other = SttSettings(live_language="hinted", provider=provider)
        assert detect_rule(AGENT, VoiceSettings(env="test", stt=other)) is None
        assert not other.hints() and not other.language_moves()
    assert not SttSettings().language_moves()
    assert SttSettings(live_language="detected", provider="groq").language_moves()


@pytest.mark.parametrize(
    ("stt", "warned"),
    [
        (SttSettings(live_language="hinted", provider="groq"), 1),
        (SttSettings(live_language="hinted"), 0),
        (SttSettings(provider="groq"), 0),
    ],
    ids=["hinted on groq", "hinted on scribe", "session"],
)
def test_the_start_says_once_when_hinted_runs_as_session(
    stt: SttSettings, warned: int, caplog: pytest.LogCaptureFixture
) -> None:
    """D-115: on a provider that gives no language probability, the runtime's start logs, once,
    that hinted runs as session; nothing for Scribe, or for any other setting."""
    providers = Providers(stt=FakeSpeechToText(), tts=FakeTextToSpeech())

    async def start() -> None:
        async with AsyncExitStack() as stack:
            await opened(providers, AGENT, VoiceSettings(env="test", stt=stt), stack)

    asyncio.run(start())
    assert [r.getMessage() for r in caplog.records].count("hinted_as_session") == warned

"""The Whisper prompt a call sends (voice/stt_requests.py's `call_prompts`, voice/pipeline.py; plan
006, Q23): every speech-to-text request of a call, an overlap's window and overlap, its turn's
and the early start's `held`, carries `whisper_prompt` of the agent's vocabulary in the language
the request names, byte for byte the prompt run W's arm W1 measured, built once a call; with
`stt.send_prompt` off none carries one; a request that names no language carries none, as W1's
sent none. Through a whole call's pipeline, with the tests' tone detector and a turn analyzer
that ends each turn at its first pause, the session a scripted one."""

from __future__ import annotations

import asyncio
from collections import Counter
from collections.abc import Iterable
from typing import Any

import pytest
from t2_agentic_voice.agent.talker import TalkerCall
from t2_agentic_voice.core.clock import Clock
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.identity import Caller, Consent
from t2_agentic_voice.core.settings.stt import SttSettings
from t2_agentic_voice.core.settings.words import LanguageCode, WordSettings
from t2_agentic_voice.core.tracing import Tracing
from t2_agentic_voice.domain.declaration import Language, VoiceAgent
from t2_agentic_voice.domain.talker_declaration import Vocabulary
from t2_agentic_voice.domain.whisper_prompt import COMMAND_SPELLINGS
from t2_agentic_voice.languages import WhisperPrompt, whisper_prompt
from t2_agentic_voice.voice import stt_requests as requests_module
from t2_agentic_voice.voice.calls import VoiceCalls
from t2_agentic_voice.voice.session.commands import Command, HangUp, HearOverlap, ListenIn, Speak
from t2_agentic_voice.voice.session.session_events import (
    Connected,
    Ending,
    SessionEvent,
    Transcribed,
    Transcribing,
    TurnOpened,
)

from tests.t2_agentic_voice.fake_session import FakeSession
from tests.t2_agentic_voice.fakes import (
    Captured,
    FakePhrases,
    FakeSpeechToText,
    FakeTextToSpeech,
    capturing_output,
)
from tests.t2_agentic_voice.voice.kit import PauseAnalyzer, ToneVAD, audio_frames, until

TERMS = ("Outlook", "VPN", "LT-")
LANGUAGES = [
    Language.english(greeting="Welcome to the test line"),
    Language.saudi_arabic(greeting="أهلا بك في خط التجربة"),
]
ECHO = VoiceAgent(name="prompted", languages=LANGUAGES, vocabulary=Vocabulary(terms=TERMS))
TALKER = VoiceAgent(
    name="prompted",
    languages=LANGUAGES,
    vocabulary=Vocabulary(terms=TERMS),
    instructions="Be brief.",
)
CALLER, CONSENT = Caller(subject="made-up"), Consent(version=None, record_audio=False)
# The parts each call sends a request of: an overlap over the greeting (its window and its
# overlap), then a turn of its own, whose request is its `turn`'s, or with a talker the early
# start's `held` one, which the turn reuses.
SENT = {"echo": ["window", "overlap", "turn"], "talker": ["window", "overlap", "held"]}


def _no_talker(call: TalkerCall, clock: Clock) -> Any:
    """A call's talker the scripted session never asks: the call has one, so the early start's
    `held` request goes."""
    return object()


def _turns_own(event: SessionEvent, turn_id: int) -> bool:
    """Whether `event` is the turn `turn_id`'s own transcript, the last of its parts."""
    return isinstance(event, Transcribed) and (event.turn_id, event.part) == (turn_id, "turn")


def _call(settings: VoiceSettings, agent: VoiceAgent, code: str | None) -> list[tuple[str, Any]]:
    """One whole call of `agent`, its language named `code` (`ListenIn`): the greeting playing,
    the caller speaks over it (marked an overlap) and, once it is over, says a turn of its own;
    each request's part and the (language, prompt) it was sent with."""
    port = FakeSpeechToText()
    phrases = FakePhrases.of(agent)
    phrases.seconds = 2.0
    calls = VoiceCalls(
        agent=agent,
        settings=settings,
        stt=port,
        tts=FakeTextToSpeech(),
        phrases=phrases,
        tracing=Tracing(),
        emit=lambda event: None,
        talker=_no_talker if agent.instructed else None,
    )
    greeting = agent.languages[0].greeting

    def replies(event: SessionEvent) -> list[Command]:
        if isinstance(event, Connected):
            audio = phrases.audio(greeting, language="en")
            hello = Speak(
                reply_id=0, clause=0, turn_id=None, text=greeting, language="en", audio=audio
            )
            return [ListenIn(language=code), hello]
        if isinstance(event, TurnOpened) and event.turn_id == 0:
            return [HearOverlap(turn_id=0, window_ms=750)]
        return [HangUp(reason="server")] if isinstance(event, Ending) else []

    captured = Captured()

    async def run() -> FakeSession:
        pipeline = calls._pipeline(
            "call-1",
            (ToneVAD(), PauseAnalyzer()),
            caller=CALLER,
            consent=CONSENT,
            language=agent.languages[0],
            output=capturing_output(captured),
        )
        session = FakeSession(pipeline.setup, pipeline.commands, replies=replies)
        await pipeline.start(session)
        pipeline.connect()
        await until(lambda: bool(captured.audio))
        caller = [
            *audio_frames(0.3, loud=False),
            *audio_frames(1.2),
            *audio_frames(1.2, loud=False),
        ]
        caller += [*audio_frames(0.6), *audio_frames(1.5, loud=False)]
        for frame in caller:  # at about real-time pace, as a call's input
            await pipeline.worker.queue_frame(frame)
            await asyncio.sleep(0.02)
        await until(lambda: any(_turns_own(e, 1) for e in session.events))
        pipeline.leave("server")
        await asyncio.wait_for(pipeline.finished.wait(), timeout=20)
        return session

    session = asyncio.run(asyncio.wait_for(run(), timeout=60))
    parts = [e.part for e in session.events if isinstance(e, Transcribing)]
    assert len(parts) == len(port.calls)
    return [
        (part, (language, prompt))
        for part, (_, language, prompt) in zip(parts, port.calls, strict=True)
    ]


def _counted(monkeypatch: pytest.MonkeyPatch) -> Counter[str]:
    """How many times each language's prompt is built, the library's own function counting."""
    built: Counter[str] = Counter()

    def counting(terms: Iterable[str], language: LanguageCode) -> WhisperPrompt:
        built[language] += 1
        return whisper_prompt(terms, language)

    monkeypatch.setattr(requests_module, "whisper_prompt", counting)
    return built


@pytest.mark.parametrize(("kind", "code"), [("echo", "ar"), ("talker", "en")])
def test_every_request_of_a_call_carries_the_prompt_run_w_measured(
    settings: VoiceSettings, monkeypatch: pytest.MonkeyPatch, kind: str, code: LanguageCode
) -> None:
    """Byte for byte what W1 sent for the language the request names (run_arms.py's
    `prompts_of`: `whisper_prompt` of the declared vocabulary's terms), on every part's request,
    each language's prompt built once for the whole call, not once a request."""
    built = _counted(monkeypatch)
    sent = _call(settings, ECHO if kind == "echo" else TALKER, code)
    measured = whisper_prompt(TERMS, code).text
    assert measured.startswith("Outlook, VPN, LT-, ")  # the terms, then the command words
    assert sent == [(part, (code, measured)) for part in SENT[kind]]
    assert built == Counter(dict.fromkeys(COMMAND_SPELLINGS, 1))


@pytest.mark.parametrize("kind", ["echo", "talker"])
def test_with_send_prompt_off_no_request_of_a_call_carries_a_prompt(
    settings: VoiceSettings, kind: str
) -> None:
    off = settings.model_copy(update={"stt": SttSettings(send_prompt=False)})
    sent = _call(off, ECHO if kind == "echo" else TALKER, "ar")
    assert sent == [(part, ("ar", None)) for part in SENT[kind]]


def test_a_request_that_names_no_language_carries_no_prompt(settings: VoiceSettings) -> None:
    """`stt.live_language = "auto"` names none (`ListenIn(None)`): W1 sent a prompt only with
    the language a request named, so none goes."""
    assert _call(settings, ECHO, None) == [(part, (None, None)) for part in SENT["echo"]]


def test_the_calls_prompts_are_w1s_with_the_settings_terms_after_the_declarations(
    settings: VoiceSettings,
) -> None:
    """`call_prompts`: each language's `whisper_prompt` of the declaration's terms, then the
    `words.vocabulary` setting's; the command words alone for an agent with no vocabulary;
    nothing with the setting off; and a language whose prompt holds no word left out, so its
    requests send none."""
    prompts = requests_module.call_prompts
    assert prompts(ECHO, settings) == {c: whisper_prompt(TERMS, c).text for c in ("ar", "en")}
    added = settings.model_copy(update={"words": WordSettings(vocabulary=("Teams", "VPN"))})
    both = (*TERMS, "Teams", "VPN")
    assert prompts(ECHO, added) == {c: whisper_prompt(both, c).text for c in ("ar", "en")}
    plain = VoiceAgent(name="plain", languages=LANGUAGES)
    found = prompts(plain, settings)
    assert found == {c: ", ".join(COMMAND_SPELLINGS[c]) for c in ("ar", "en")}
    off = settings.model_copy(update={"stt": SttSettings(send_prompt=False)})
    assert prompts(ECHO, off) == {}
    term = "𠀀" * 64  # a CJK character of 4 bytes, 64 times: 256 bytes, so none fits
    wide = VoiceAgent(name="wide", languages=LANGUAGES, vocabulary=Vocabulary(terms=[term]))
    assert whisper_prompt(wide.vocabulary.terms, "en").text == ""
    assert prompts(wide, settings) == {}

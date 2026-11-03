"""The time of each step of an echo call (testing/echo_timing.py and timed_speech.py): each turn
timed from hand-made events and commands, as a file-fed call hands them (a turn echoed, one
dropped, one whose transcript failed, one whose echo clause failed); each model's usage counted
as the session counts it; the heard words' first sound read from their audio, which goes on
unchanged; and what `echo_timings` builds its calls with, against a fake `VoiceCalls` and a fake
`feed_file`: the caller's phrase audio, so no fixed phrase reaches the text-to-speech, and the
caller's speech ports, read on the way."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

import pytest
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.events import ModelUsage
from t2_agentic_voice.core.settings.tts import LanguageTag
from t2_agentic_voice.domain.declaration import Language, VoiceAgent
from t2_agentic_voice.domain.ports.speech_to_text import AudioClip, Transcript
from t2_agentic_voice.domain.ports.text_to_speech import AudioChunk
from t2_agentic_voice.testing import echo_timing
from t2_agentic_voice.testing.echo_timing import (
    EchoTiming,
    TurnTiming,
    echo_timings,
    timing_of,
    usage_of,
)
from t2_agentic_voice.testing.timed_speech import NOISE_FLOOR, Take, TimedSpeech, first_sound
from t2_agentic_voice.voice import file_transport
from t2_agentic_voice.voice.file_transport import FedCall
from t2_agentic_voice.voice.session.commands import Command, Speak
from t2_agentic_voice.voice.session.session_events import (
    AgentAudio,
    ClauseFailed,
    ClausePlayed,
    ClauseQueued,
    SessionEvent,
    Synthesizing,
    Transcribed,
    Transcribing,
    TurnClosed,
    TurnOpened,
)

from tests.t2_agentic_voice.fakes import FakeClock, FakePhrases, FakeSpeechToText, FakeTextToSpeech
from tests.t2_agentic_voice.testing.feed_support import FakeFeed

AGENT = VoiceAgent(name="echo", languages=[Language.english(greeting="Hello there.")])
SECOND = AudioClip(pcm16=b"\x00\x00" * 16_000)
ARABIC = "canopylabs/orpheus-arabic-saudi"
ENGLISH = "canopylabs/orpheus-v1-english"
MODELS: dict[LanguageTag, str] = {"ar-SA": ARABIC, "ar": ARABIC, "en": ENGLISH}
FRAME_AUDIO = AudioChunk(pcm16=b"\x01\x00" * 240, sample_rate=24_000)
QUIET, LOUD = (NOISE_FLOOR).to_bytes(2, "little"), (NOISE_FLOOR + 1).to_bytes(2, "little")


def _speak(reply: int, clause: int, turn: int | None, text: str, *, cached: bool) -> Speak:
    audio = FRAME_AUDIO if cached else None
    return Speak(reply_id=reply, clause=clause, turn_id=turn, text=text, language="en", audio=audio)


def _call() -> FedCall:
    """A call whose clip starts at 10.0: its greeting (reply 0, cached); turn 0, echoed (frame,
    then the heard words), its first output frame at 12.30; turn 1, dropped; turn 2, whose
    transcript failed; turn 3, whose echo's heard words failed."""
    events: list[SessionEvent] = [
        Synthesizing(reply_id=9, clause=0, at=9.0),  # a clause no command asked for: ignored
        TurnOpened(turn_id=0, at=10.5, speech_at=10.3),
        TurnClosed(turn_id=0, at=11.5, speech_ended_at=11.2),
        Transcribing(turn_id=0, at=11.5, audio_s=1.2),
        Transcribed(
            turn_id=0,
            at=11.8,
            audio_s=1.2,
            sent_at=11.5,
            transcript=Transcript(text="x", language="en", remaining_requests=19),
        ),
        ClauseQueued(reply_id=1, clause=0, at=12.2, requested_at=None),
        AgentAudio(pcm16=b"", sample_rate=24_000, at=12.25),  # no audio: not a frame
        AgentAudio(pcm16=b"\x01\x00", sample_rate=24_000, at=12.3),
        Synthesizing(reply_id=1, clause=1, at=12.0),
        ClauseQueued(reply_id=1, clause=1, at=12.4, requested_at=12.0),
        ClausePlayed(reply_id=1, clause=1, at=13.0, audio_s=0.5, chunks=2, remaining_requests=7),
        TurnOpened(turn_id=1, at=13.1, speech_at=12.9),
        TurnClosed(turn_id=1, at=14.0, speech_ended_at=13.7),
        Transcribing(turn_id=1, at=14.0, audio_s=12.5),
        Transcribed(turn_id=1, at=14.2, audio_s=12.5, sent_at=14.0, transcript=None),
        TurnOpened(turn_id=2, at=15.0, speech_at=14.8),
        TurnClosed(turn_id=2, at=16.0, speech_ended_at=15.6),
        Transcribing(turn_id=2, at=16.0, audio_s=1.0),
        Transcribed(
            turn_id=2,
            at=16.3,
            audio_s=1.0,
            sent_at=16.0,
            transcript=None,
            failure="rate_limited",
            retryable=True,
        ),
        TurnOpened(turn_id=3, at=17.0, speech_at=16.9),
        TurnClosed(turn_id=3, at=18.0, speech_ended_at=17.7),
        Synthesizing(reply_id=3, clause=1, at=18.4),
        ClauseFailed(reply_id=3, clause=1, at=18.6, failure="timeout", retryable=True),
    ]
    commands: list[tuple[float, Command]] = [
        (9.0, _speak(0, 0, None, "Hello there.", cached=True)),
        (11.9, _speak(1, 0, 0, "I heard:", cached=True)),
        (11.95, _speak(1, 1, 0, "open the inbox", cached=False)),
        (16.4, _speak(2, 0, None, "Sorry.", cached=True)),
        (18.3, _speak(3, 0, 3, "I heard:", cached=True)),
        (18.35, _speak(3, 1, 3, "two", cached=False)),
    ]
    return FedCall(started_at=10.0, events=tuple(events), commands=tuple(commands))


def _rounded(model: TurnTiming | ModelUsage) -> dict[str, object]:
    """A timing's or a usage's fields, each float to the microsecond's thousandth."""
    return {k: round(v, 6) if isinstance(v, float) else v for k, v in model.model_dump().items()}


def test_each_turn_is_timed_from_the_clips_start() -> None:
    takes = [
        Take(text="open the inbox", language="en", first_sound_at=12.9, leading_silence_s=0.45),
        Take(text="two", language="en"),
    ]
    echoed, dropped, unheard, failed = map(_rounded, timing_of(_call(), takes))
    assert echoed == {
        "turn_id": 0,
        "speech_stop_ms": 1200.0,
        "end_ms": 1500.0,
        "stt_sent_ms": 1500.0,
        "stt_answered_ms": 1800.0,
        "echo_text_ms": 1950.0,
        "frame_audio_ms": 2300.0,
        "tts_sent_ms": 2000.0,
        "tts_first_audio_ms": 2400.0,
        "heard_sound_ms": 2900.0,
        "leading_silence_ms": 450.0,
        "failure": None,
    }
    assert {k: v for k, v in dropped.items() if v is not None} == {
        "turn_id": 1,
        "speech_stop_ms": 3700.0,
        "end_ms": 4000.0,
        "stt_sent_ms": 4000.0,
        "stt_answered_ms": 4200.0,
    }
    assert (unheard["failure"], unheard["stt_answered_ms"]) == ("rate_limited", 6300.0)
    assert {k: v for k, v in failed.items() if v is not None} == {
        "turn_id": 3,
        "speech_stop_ms": 7700.0,
        "end_ms": 8000.0,
        "echo_text_ms": 8350.0,
        "tts_sent_ms": 8400.0,
        "failure": "timeout",
    }


def test_only_a_turn_part_is_the_turns_own_transcript() -> None:
    """An overlap's `window` and `overlap` parts (plan 005) come before its `turn` part: the
    turn is timed from its own part alone, while usage counts every request, each part's."""
    window = Transcribing(turn_id=0, at=10.9, audio_s=0.75, part="window")
    whole = Transcribing(turn_id=0, at=11.2, audio_s=1.1, part="overlap")
    heard = [
        Transcribed(turn_id=0, at=at, audio_s=s, sent_at=sent, transcript=None, part=part)
        for at, s, sent, part in ((11.1, 0.75, 10.9, "window"), (11.4, 1.1, 11.2, "overlap"))
    ]
    call = _call()
    fed = FedCall(
        started_at=call.started_at,
        events=(call.events[0], call.events[1], window, heard[0], whole, heard[1], *call.events[2:]),
        commands=call.commands,
    )
    (echoed, *_) = timing_of(fed, [])
    assert (echoed.stt_sent_ms, echoed.stt_answered_ms) == pytest.approx((1500.0, 1800.0))
    (whisper, _) = usage_of(fed, stt_model="whisper-large-v3", tts_models=MODELS)
    assert whisper.requests == 5


def test_a_take_is_claimed_once_and_only_by_its_own_words() -> None:
    other = Take(text="another text", language="en", first_sound_at=12.5, leading_silence_s=0.1)
    (echoed, *_) = timing_of(_call(), [other])
    assert (echoed.heard_sound_ms, echoed.leading_silence_ms) == (None, None)


def test_each_models_usage_is_counted_from_the_calls_reports() -> None:
    whisper, english = usage_of(_call(), stt_model="whisper-large-v3", tts_models=MODELS)
    assert _rounded(whisper) == {
        "model": "whisper-large-v3",
        "requests": 3,
        "audio_sent_s": 14.7,
        "billed_s": 32.5,  # 10 + 12.5 + 10
        "characters": 0,
        "cache_hits": 0,
        "remaining_requests": 19,
        "remaining_tokens": None,
    }
    assert _rounded(english) == {
        "model": ENGLISH,
        "requests": 2,
        "audio_sent_s": 0.0,
        "billed_s": 0.0,
        "characters": len("open the inbox") + len("two"),
        "cache_hits": 4,
        "remaining_requests": 7,
        "remaining_tokens": None,
    }
    quiet = FedCall(started_at=0.0, events=(), commands=())
    assert usage_of(quiet, stt_model="whisper-large-v3", tts_models=MODELS) == ()


def test_the_first_sound_is_the_first_sample_above_the_noise_floor() -> None:
    assert first_sound(QUIET * 3 + LOUD + QUIET) == 3
    assert first_sound((-(NOISE_FLOOR + 1)).to_bytes(2, "little", signed=True)) == 0
    assert first_sound(QUIET * 4) is None and first_sound(b"") is None


class _Chunks(FakeTextToSpeech):
    """A text-to-speech that streams fixed chunks, and says whether its stream was closed."""

    def __init__(self, chunks: list[bytes]) -> None:
        super().__init__()
        self.chunks, self.stream_closed = chunks, False

    async def synthesize(self, text: str, *, language: str) -> AsyncIterator[AudioChunk]:
        self.calls.append((text, language))
        try:
            for pcm16 in self.chunks:
                yield AudioChunk(pcm16=pcm16, sample_rate=1_000)
        finally:
            self.stream_closed = True


def test_timed_speech_hands_the_audio_on_and_keeps_when_its_first_sound_came() -> None:
    chunks = [QUIET * 2, b"", QUIET + LOUD, LOUD]
    inner = _Chunks(chunks)
    clock = FakeClock(start=5.0)
    timed = TimedSpeech(inner, clock)

    async def take() -> list[bytes]:
        found = []
        async for chunk in timed.synthesize("words", language="en"):
            found.append(chunk.pcm16)
            await clock.advance(1.0)
        await timed.check_language("en")
        await timed.aclose()
        return found

    assert asyncio.run(take()) == chunks
    assert timed.takes == [Take("words", "en", first_sound_at=7.0, leading_silence_s=0.003)]
    assert (timed.name, timed.data_flow, timed.max_chars("en")) == ("fake", inner.data_flow, 200)
    assert inner.checked == ["en"] and inner.closed and inner.stream_closed


def test_timed_speech_closes_the_providers_stream_when_its_reader_stops() -> None:
    inner = _Chunks([QUIET, LOUD, LOUD])
    timed = TimedSpeech(inner)

    async def first() -> None:
        stream = timed.synthesize("words", language="en")
        async for _ in stream:
            break
        await stream.aclose()  # type: ignore[attr-defined]

    asyncio.run(first())
    assert inner.stream_closed and timed.takes == [Take("words", "en")]


@pytest.fixture
def feed(monkeypatch: pytest.MonkeyPatch) -> FakeFeed:
    faked = FakeFeed([])
    monkeypatch.setattr(echo_timing, "VoiceCalls", faked.voice_calls)
    monkeypatch.setattr(file_transport, "feed_file", faked)
    return faked


async def _all(found: AsyncIterator[EchoTiming]) -> list[EchoTiming]:
    return [timing async for timing in found]


def test_each_clip_is_an_echo_call_of_the_agent_in_its_language(
    feed: FakeFeed, settings: VoiceSettings
) -> None:
    """The caller's phrase audio plays the fixed phrases, so `tts` gets no request for one; the
    caller's speech ports are the calls', the text-to-speech read on its way."""
    agent = VoiceAgent(
        name="echo",
        languages=[
            Language.english(greeting="Hello there."),
            Language.saudi_arabic(greeting="أهلا"),
        ],
    )
    phrases = FakePhrases.of(agent)
    stt, tts = FakeSpeechToText(), FakeTextToSpeech()
    feed.calls = [_call(), FedCall(started_at=1.0, events=(), commands=())]
    found = echo_timings(
        [(SECOND, "en"), (SECOND, "ar-SA")],
        agent=agent,
        settings=settings,
        stt=stt,
        tts=tts,
        phrases=phrases,
        lead_s=1.0,
        tail_s=4.5,
    )
    first, second = asyncio.run(_all(found))
    assert [turn.turn_id for turn in first.turns] == [0, 1, 2, 3]
    assert [usage.model for usage in first.usage] == [settings.stt.model, ENGLISH]
    assert second == EchoTiming(turns=(), usage=())
    (calls,) = feed.built
    built: dict[str, Any] = calls.built
    assert (built["agent"], built["phrases"], built["stt"]) == (agent, phrases, stt)
    assert isinstance(built["tts"], TimedSpeech) and built["tts"].inner is tts
    assert [asked["language"].tag for asked in feed.asked] == ["en", "ar-SA"]
    assert [asked["call_id"] for asked in feed.asked] == ["echo-timings-0", "echo-timings-1"]
    assert all((asked["lead_s"], asked["tail_s"]) == (1.0, 4.5) for asked in feed.asked)
    assert (calls.started, calls.closed) == (1, 1) and tts.calls == [] and not tts.closed


def test_a_clip_the_calls_cannot_take_is_refused_before_any_call(
    feed: FakeFeed, settings: VoiceSettings
) -> None:
    def run(clip: AudioClip, tag: Any) -> None:
        found = echo_timings(
            [(clip, tag)],
            agent=AGENT,
            settings=settings,
            stt=FakeSpeechToText(),
            tts=FakeTextToSpeech(),
            phrases=FakePhrases.of(AGENT),
            lead_s=1.0,
            tail_s=4.5,
        )
        asyncio.run(_all(found))

    with pytest.raises(ValueError, match="16000 Hz"):
        run(AudioClip(pcm16=b"\x00\x00", sample_rate=8_000), "en")
    with pytest.raises(ValueError, match="speaks no ar-SA"):
        run(SECOND, "ar-SA")
    assert feed.built == []

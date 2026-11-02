"""The fakes of the ports, the clock and voice's entry point (tests/t2_agentic_voice/fakes.py)
implement their protocols, so the tracks that build against them build against the real
interfaces: each is assigned to its protocol, which mypy checks, and does what its docstring
says. The session's I/O fakes are checked in test_session_fakes.py."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from datetime import timedelta

import pytest
from t2_agentic_voice import ConfigurationError, InvalidRequestError, NotFoundError, ProviderError
from t2_agentic_voice.core.identity import Caller, Consent
from t2_agentic_voice.ports import AudioChunk, AudioClip, SpeechToText, TextToSpeech, Transcript
from t2_agentic_voice.voice.calls import Calls, Candidate
from t2_agentic_voice.voice.session.io import SYSTEM_CLOCK, Clock

from tests.t2_agentic_voice.fakes import (
    WALL_START,
    Captured,
    FakeCalls,
    FakeClock,
    FakeSpeechToText,
    FakeTextToSpeech,
    capturing_output,
    quiet_pipecat,
    tone,
)

CLIP = AudioClip(pcm16=tone(1.0, 16_000))
CALLER = Caller(subject="caller-1")
CONSENT = Consent(version=None, record_audio=False)


def test_the_tone_is_whole_samples_of_sound() -> None:
    audio = tone(0.01, 16_000)
    assert len(audio) == 320
    assert {int.from_bytes(audio[i : i + 2], "little", signed=True) for i in (0, 2)} == {
        1024,
        -1024,
    }
    assert tone(0, 24_000) == b""


def test_the_fake_speech_to_text_answers_from_its_script() -> None:
    script: list[str | Transcript | ProviderError] = [
        "words for the test",
        Transcript(text="more words", language="en"),
        ProviderError("timeout", True),
    ]
    fake = FakeSpeechToText(script)
    stt: SpeechToText = fake

    async def four() -> list[Transcript]:
        heard = [await stt.transcribe(CLIP, language="en", prompt=None) for _ in range(2)]
        with pytest.raises(ProviderError):
            await stt.transcribe(CLIP, language="en", prompt=None)
        heard.append(await stt.transcribe(CLIP, language=None, prompt="p"))
        await stt.aclose()
        return heard

    heard = asyncio.run(four())
    assert [h.text for h in heard] == ["words for the test", "more words", ""]
    assert (heard[0].billed_seconds, heard[0].language) == (10.0, "en")
    assert [(language, prompt) for _, language, prompt in fake.calls][-1] == (None, "p")
    assert fake.closed


def test_the_fake_speech_to_text_can_be_cancelled_mid_call() -> None:
    stt = FakeSpeechToText(["late"], delay_s=10)

    async def cancelled() -> None:
        await asyncio.wait_for(stt.transcribe(CLIP, language="ar", prompt=None), timeout=0.01)

    with pytest.raises(TimeoutError):
        asyncio.run(cancelled())


async def _take(tts: TextToSpeech, text: str, language: str = "en") -> list[AudioChunk]:
    return [chunk async for chunk in tts.synthesize(text, language=language)]


def test_the_fake_text_to_speech_says_every_text_as_audio() -> None:
    fake = FakeTextToSpeech(remaining=(9, 900), cut_short={"cut here"})
    tts: TextToSpeech = fake
    chunks = asyncio.run(_take(tts, "ten chars!"))
    assert sum(c.seconds for c in chunks) == pytest.approx(0.6)
    assert [len(c.pcm16) for c in chunks] == [4800] * 6
    assert [(c.remaining_requests, c.remaining_tokens) for c in chunks[:2]] == [
        (9, 900),
        (None, None),
    ]
    assert not any(c.cut_short for c in chunks)
    assert asyncio.run(_take(tts, "cut here", "ar"))[-1].cut_short
    assert asyncio.run(_take(tts, "")) == []
    assert fake.calls == [("ten chars!", "en"), ("cut here", "ar"), ("", "en")]
    assert (tts.max_chars("en"), FakeTextToSpeech(limit=None).max_chars("ar")) == (200, None)


def test_the_fake_text_to_speech_fails_as_the_port_says() -> None:
    timeout = ProviderError("timeout", True)
    tts = FakeTextToSpeech(limit=5, failures={"fails": timeout})
    with pytest.raises(ProviderError) as raised:
        asyncio.run(_take(tts, "longer than five"))
    assert (raised.value.kind, raised.value.retryable) == ("rejected", False)
    with pytest.raises(ProviderError) as failed:
        asyncio.run(_take(tts, "fails"))
    assert failed.value is timeout

    async def checked() -> None:
        await tts.check_language("ar-SA")
        with pytest.raises(ConfigurationError, match="FIX: "):
            await tts.check_language("fr")
        await tts.aclose()

    asyncio.run(checked())
    assert (tts.checked, tts.closed) == (["ar-SA", "fr"], True)


def test_the_fake_text_to_speech_can_be_cancelled_mid_take() -> None:
    tts = FakeTextToSpeech(delay_s=10)

    async def cancelled() -> None:
        await asyncio.wait_for(_take(tts, "a clause"), timeout=0.01)

    with pytest.raises(TimeoutError):
        asyncio.run(cancelled())


def test_the_fake_clock_moves_only_when_advanced() -> None:
    fake = FakeClock(start=50.0)
    clock: Clock = fake
    real: Clock = SYSTEM_CLOCK
    assert real.wall().tzinfo is not None and real.now() > 0
    woke: list[tuple[str, float]] = []

    async def sleeper(name: str, seconds: float, then: float | None = None) -> None:
        await clock.sleep(seconds)
        woke.append((name, clock.now()))
        if then is not None:
            await clock.sleep(then)
            woke.append((f"{name} again", clock.now()))

    async def scene() -> None:
        tasks = [
            asyncio.create_task(sleeper("late", 3.0)),
            asyncio.create_task(sleeper("early", 1.0, then=0.5)),
            asyncio.create_task(sleeper("never", 60.0)),
        ]
        await asyncio.sleep(0)
        await clock.sleep(0)
        assert (woke, clock.now()) == ([], 50.0)
        await fake.advance(2.0)
        assert clock.now() == 52.0
        await fake.advance(1.0)
        tasks[2].cancel()
        await fake.advance(100.0)
        await asyncio.gather(*tasks, return_exceptions=True)

    asyncio.run(scene())
    assert woke == [("early", 51.0), ("early again", 51.5), ("late", 53.0)]
    assert fake.sleeps == [3.0, 1.0, 60.0, 0, 0.5]
    assert clock.wall() == WALL_START + timedelta(seconds=103)


def _candidate(line: str) -> Candidate:
    return Candidate(candidate=line, sdp_mid="0", sdp_mline_index=0)


def test_the_fake_calls_answer_offers_as_voices_entry_point_does() -> None:
    fake = FakeCalls(refused={"an offer it refuses"})
    calls: Calls = fake
    good = [_candidate("candidate:1 1 udp 1 192.0.2.1 5000 typ host"), _candidate("")]

    async def scene() -> list[str | None]:
        with pytest.raises(RuntimeError, match="FIX: "):
            await calls.answer("c1", "an offer", caller=CALLER, consent=CONSENT)
        await calls.start()
        answer = await calls.answer("c1", "an offer", caller=CALLER, consent=CONSENT)
        for call_id, offer in (("c1", "again"), ("c2", "an offer it refuses")):
            with pytest.raises(InvalidRequestError):
                await calls.answer(call_id, offer, caller=CALLER, consent=CONSENT)
        with pytest.raises(NotFoundError):
            await calls.add_candidates("c9", good)
        with pytest.raises(InvalidRequestError):
            await calls.add_candidates("c1", [good[0], _candidate("not a candidate")])
        await calls.add_candidates("c1", good)
        phases = [calls.phase("c1")]
        fake.connect("c1")
        phases.append(calls.phase("c1"))
        await calls.end("c1")
        await calls.end("c1")
        await calls.end("c9")
        phases += [calls.phase("c1"), calls.phase("c9")]
        await calls.answer("c3", "an offer", caller=CALLER, consent=CONSENT)
        await calls.aclose()
        return [answer, *phases]

    assert asyncio.run(scene()) == ["answer to c1", "connecting", "connected", "ended", None]
    assert fake.offers["c1"] == ("an offer", CALLER, CONSENT) and "c2" not in fake.offers
    assert fake.candidates["c1"] == good
    assert (fake.ended, fake.started, fake.closed) == (["c1", "c3"], 1, 1)


def _run(captured: Captured, items: Sequence[object | float], *, realtime: bool) -> None:
    """A pipeline of a `capturing_output` alone, without the 2 s of silence after the end:
    each item queued in turn once it started (a float waits that many seconds first), then an
    end."""
    from pipecat.frames.frames import EndFrame, Frame
    from pipecat.pipeline.pipeline import Pipeline
    from pipecat.pipeline.worker import PipelineWorker
    from pipecat.transports.base_transport import TransportParams
    from pipecat.workers.runner import WorkerRunner

    params = TransportParams(audio_out_enabled=True, audio_out_end_silence_secs=0)
    output = capturing_output(captured, params=params, realtime=realtime)

    async def run() -> None:
        worker = PipelineWorker(Pipeline([output]), enable_rtvi=False, idle_timeout_secs=None)
        runner = WorkerRunner(handle_sigint=False)
        await runner.add_workers(worker)

        async def feed() -> None:
            while not captured.frames:  # the StartFrame comes first
                await asyncio.sleep(0.01)
            for item in items:
                if isinstance(item, float):
                    await asyncio.sleep(item)
                else:
                    assert isinstance(item, Frame)
                    await worker.queue_frame(item)
            await worker.queue_frame(EndFrame())

        await asyncio.wait_for(asyncio.gather(runner.run(), feed()), timeout=30)

    asyncio.run(run())


def test_the_capturing_output_writes_audio_and_messages_where_a_test_reads_them() -> None:
    quiet_pipecat()
    from pipecat.frames.frames import (
        OutputAudioRawFrame,
        OutputTransportMessageUrgentFrame,
        StartFrame,
    )

    captured = Captured()
    audio = OutputAudioRawFrame(audio=tone(0.2, 24_000), sample_rate=24_000, num_channels=1)
    message = OutputTransportMessageUrgentFrame(message={"v": 1, "type": "state"})
    _run(captured, [audio, message], realtime=False)
    assert isinstance(captured.frames[0], StartFrame) and audio in captured.frames
    assert [len(f.audio) for _, f in captured.audio] == [1920] * 5  # 40 ms chunks
    assert captured.audio_s() == pytest.approx(0.2)
    assert [m for _, m in captured.messages] == [{"v": 1, "type": "state"}]


def test_the_capturing_output_plays_in_real_time_and_drops_audio_on_an_interruption() -> None:
    """A second of audio queued, then an interruption 0.3 s in: what was written stops there,
    give or take a chunk and Windows' timer, and each write waited for the one before to play."""
    quiet_pipecat()
    from pipecat.frames.frames import InterruptionFrame, OutputAudioRawFrame

    captured = Captured()
    audio = OutputAudioRawFrame(audio=tone(1.0, 24_000), sample_rate=24_000, num_channels=1)
    _run(captured, [audio, 0.3, InterruptionFrame()], realtime=True)
    assert 0.2 <= captured.audio_s() <= 0.5
    times = [at for at, _ in captured.audio]
    assert times[-1] - times[0] >= captured.audio_s() - 0.04 - 0.05

"""Plan 003's step 16, the integration check with no spend: one call as a browser makes it, from its
join to its end, through the runtime's router (api/router.py), the real pipeline
(voice/pipeline.py) and the echo session (voice/session/), the providers fakes and the audio
generated (no audio file: tests/ole5_voice/evals/test_no_audio.py).

A local aiortc peer, built with `RTCConfiguration(iceServers=[])` (tests/conftest.py makes
aiortc's default list raise), plays the browser's part as `t2v-client.js` does: it joins the
minimal example's echo agent (`DevIdentity`, `env` dev, from loopback), offers, sends its
candidates once the offer is answered and then their end, says hello on the data channel, waits
out the greeting, and sends a sine that the fake speech detector hears as speech. The fake
speech-to-text hears made-up words, the session says them back, and the client hears the echo
from the fake text-to-speech, which says the heard words at a pitch of their own; then it hangs
up. It also checks what the tracks left to this test: the phrase cache, real and declared at
the runtime's start under the test's folder, gets no new file and is never asked for the heard
words (invariant 8); and no public event, and no session message that names a thing, is sent
twice. The call runs on a selector loop, as `serve()` runs it (api/server.py), every wait
bounded, every peer closed and no task left.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections import Counter
from collections.abc import AsyncIterator, Awaitable
from fractions import Fraction
from functools import partial
from pathlib import Path
from typing import Any

import av
import httpx
import numpy as np
import pytest
from aiortc import RTCBundlePolicy, RTCConfiguration, RTCPeerConnection, RTCSessionDescription
from aiortc.mediastreams import MediaStreamError, MediaStreamTrack
from fastapi import FastAPI
from minimal_example.app import agent
from t2_agentic_voice.adapters.phrase_cache import PhraseCache
from t2_agentic_voice.api.runtime import Providers, VoiceRuntime
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.events import CallEnded, Event
from t2_agentic_voice.core.settings.storage import StorageSettings
from t2_agentic_voice.core.settings.tts import LanguageTag
from t2_agentic_voice.domain.ports.text_to_speech import AudioChunk
from t2_agentic_voice.identity import DevIdentity
from t2_agentic_voice.voice.calls import CallsFactory, VoiceCalls
from t2_agentic_voice.voice.protocol import RESERVED_TYPES, SESSION_MESSAGES
from t2_agentic_voice.voice.session.report import REPORTS

from tests.t2_agentic_voice.api.runtime_support import PREFIX, patch, post, serving
from tests.t2_agentic_voice.fakes import FakeSpeechToText, FakeTextToSpeech
from tests.t2_agentic_voice.voice.kit import PauseAnalyzer, ToneVAD, until

ENGLISH = agent.languages[0]
# The made-up words the fake speech-to-text hears, said back at a pitch of their own; the
# phrases, the caller's signal and the echo's words each at its own.
HEARD = "a loopback call said back"
SECONDS_PER_CHAR = 0.03
PHRASE_HZ, HEARD_HZ, SIGNAL_HZ = 400.0, 1000.0, 300.0
AMPLITUDE = 8000
# The browser's audio: 20 ms frames at 48 kHz, as Opus carries them; a frame of the agent's is
# heard when a sample passes LOUD, at its strongest frequency, within a bin of its spectrum.
RATE, PTIME, LOUD, BIN_HZ = 48_000, 0.02, 1000, 50.0
# How long the caller speaks, and waits after the greeting (past the session's 300 ms).
SPEECH_S, AFTER_GREETING_S = 0.6, 0.5
# How far each pitch's audio, as heard, may be from what was said: Opus's frame edges and the
# output's 40 ms chunks (the agent's bound).
TOLERANCE_S = 0.15
# The bound on each wait and on each peer's close, and on the whole call, start to stop.
WAIT_S, CLOSE_S, TEST_S = 10.0, 5.0, 30.0
QUIET = ("not_offered", "ice_completed", "call_ended")


def sine(hz: float, seconds: float, rate: int, start: int = 0) -> bytes:
    """`seconds` of a sine at `hz` as mono PCM16 at `rate`, from sample `start`."""
    n = np.arange(start, start + round(seconds * rate))
    return (AMPLITUDE * np.sin(2 * np.pi * hz * n / rate)).astype("<i2").tobytes()


class PitchedSpeech(FakeTextToSpeech):
    """The fakes' text-to-speech, saying each text as a sine: the heard words at HEARD_HZ and
    every other text, the phrases the cache declares, at PHRASE_HZ."""

    def __init__(self) -> None:
        super().__init__(seconds_per_char=SECONDS_PER_CHAR)

    async def synthesize(self, text: str, *, language: str) -> AsyncIterator[AudioChunk]:
        self.calls.append((text, language))
        hz = HEARD_HZ if text == HEARD else PHRASE_HZ
        pcm = sine(hz, len(text) * self.seconds_per_char, self.sample_rate)
        step = round(self.chunk_s * self.sample_rate) * 2
        for i in range(0, len(pcm), step):
            yield AudioChunk(pcm16=pcm[i : i + step], sample_rate=self.sample_rate)


class Signal(MediaStreamTrack):
    """The caller's microphone: 20 ms frames of mono PCM16 at 48 kHz, paced in real time,
    silent but while `say` asks for the sine."""

    kind = "audio"

    def __init__(self) -> None:
        super().__init__()
        self._sent = 0
        self._start: float | None = None
        self._loud = 0

    def say(self, seconds: float) -> None:
        self._loud = round(seconds * RATE)

    async def recv(self) -> av.AudioFrame:
        if self.readyState != "live":
            raise MediaStreamError
        if self._start is None:
            self._start = time.perf_counter()
        else:
            await asyncio.sleep(self._start + self._sent / RATE - time.perf_counter())
        samples = round(PTIME * RATE)
        loud = min(self._loud, samples)
        self._loud -= loud
        pcm = sine(SIGNAL_HZ, loud / RATE, RATE, self._sent) + bytes(2 * (samples - loud))
        frame = av.AudioFrame.from_ndarray(
            np.frombuffer(pcm, dtype="<i2").reshape(1, -1), format="s16", layout="mono"
        )
        frame.sample_rate, frame.pts, frame.time_base = RATE, self._sent, Fraction(1, RATE)
        self._sent += samples
        return frame


def pitch(frame: av.AudioFrame) -> float | None:
    """The frame's strongest frequency in its first channel, in Hz; None for a quiet frame."""
    data = frame.to_ndarray()
    channels = len(frame.layout.channels)
    first = data[0] if frame.format.is_planar else data.reshape(-1, channels)[:, 0]
    samples = first.astype(np.float64)
    if not len(samples) or np.max(np.abs(samples)) < LOUD:
        return None
    return float(np.argmax(np.abs(np.fft.rfft(samples)))) * frame.sample_rate / len(samples)


async def bounded[T](step: Awaitable[T], seconds: float = WAIT_S) -> T:
    """`step`, awaited for at most `seconds`."""
    return await asyncio.wait_for(step, seconds)


class Browser:
    """The browser's part (`t2v-client.js`): its peer, with the signal as its microphone and a
    data channel; the messages it was sent; the agent's audio, each frame's pitch and length;
    and each PATCH's answer. Built inside the loop, which aiortc's sender keeps."""

    def __init__(self) -> None:
        config = RTCConfiguration(iceServers=[], bundlePolicy=RTCBundlePolicy.MAX_BUNDLE)
        self.peer = RTCPeerConnection(config)
        self.signal = Signal()
        self.peer.addTrack(self.signal)  # the audio first, so its m-line is mid 0
        self.channel = self.peer.createDataChannel("t2v", ordered=True)
        self.messages: list[dict[str, Any]] = []
        self.heard: list[tuple[float | None, float]] = []
        self.patches: list[int | str] = []
        self._reading: list[asyncio.Task[None]] = []
        self.channel.on("message", lambda data: self.messages.append(json.loads(data)))
        self.peer.on("track", self._track)

    def _track(self, track: MediaStreamTrack) -> None:
        self._reading.append(asyncio.ensure_future(self._read(track)))

    async def _read(self, track: MediaStreamTrack) -> None:
        while True:
            try:
                frame = await track.recv()
            except MediaStreamError:
                return
            assert isinstance(frame, av.AudioFrame)
            self.heard.append((pitch(frame), frame.samples / frame.sample_rate))

    def of(self, kind: str) -> list[dict[str, Any]]:
        """The t2v/1 messages of `kind` the session sent, in order."""
        return [m for m in self.messages if m.get("v") == 1 and m["type"] == kind]

    def states(self) -> list[str]:
        return [m["state"] for m in self.of("state")]

    def heard_s(self, hz: float) -> float:
        """How long the agent's audio was heard at `hz`."""
        return sum(s for found, s in self.heard if found is not None and abs(found - hz) <= BIN_HZ)

    def send(self, kind: str, **fields: object) -> None:
        self.channel.send(json.dumps({"v": 1, "type": kind, **fields}))

    async def connect(self, http: httpx.AsyncClient) -> None:
        """Join, offer, then trickle the candidates and their end once the offer is answered,
        each PATCH's quiet 409 ignored as the client ignores it."""
        joined = await bounded(
            post(http, "/join", {"token": "dev", "protocol": 1, "language": "en"})
        )
        assert joined.status_code == 200, joined.text
        call_id, secret = joined.json()["call_id"], joined.json()["offer_secret"]
        assert joined.json()["ice_servers"] == []
        offer = await bounded(self.peer.createOffer())
        assert "a=candidate:" not in offer.sdp  # as a browser's: its candidates trickle
        await bounded(self.peer.setLocalDescription(offer))
        body = {"call_id": call_id, "sdp": offer.sdp, "type": "offer", "offer_secret": secret}
        answered = await bounded(post(http, "/offer", body))
        assert answered.status_code == 200, answered.text
        answer = RTCSessionDescription(sdp=answered.json()["sdp"], type="answer")
        await bounded(self.peer.setRemoteDescription(answer))
        lines = _candidates(self.peer.localDescription.sdp)
        assert lines, "the peer gathered no candidate"
        end = {"candidate": "", "sdp_mid": "0", "sdp_mline_index": 0}
        for candidate in [*lines, end]:
            body = {"call_id": call_id, "candidates": [candidate], "offer_secret": secret}
            sent = await bounded(patch(http, body))
            code = sent.status_code if sent.status_code == 204 else sent.json()["code"]
            assert code == 204 or (sent.status_code == 409 and code in QUIET), sent.text
            self.patches.append(code)

    async def talk(self) -> None:
        """Say hello once the channel opens, wait out the greeting, speak, hear the echo's
        words, and hang up once they have played."""
        await until(lambda: self.channel.readyState == "open", timeout=WAIT_S)
        self.send("hello", client="aiortc-loopback/1")
        self.send("client_stats", candidate_type="host")
        await until(lambda: self.states()[-2:] == ["speaking", "listening"], timeout=WAIT_S)
        await asyncio.sleep(AFTER_GREETING_S)
        spoke = len(self.states())
        self.signal.say(SPEECH_S)
        await until(lambda: "speaking" in self.states()[spoke:], timeout=WAIT_S)
        await until(lambda: self.states()[-1] == "listening", timeout=WAIT_S)
        echo_s = len(HEARD) * SECONDS_PER_CHAR
        await until(lambda: self.heard_s(HEARD_HZ) >= echo_s - TOLERANCE_S, timeout=WAIT_S)
        self.send("hangup")
        await until(lambda: bool(self.of("ended")), timeout=WAIT_S)
        await until(lambda: self.channel.readyState == "closed", timeout=WAIT_S)

    async def close(self) -> None:
        """Close the peer, then let each reader of its tracks end: each bounded."""
        self.signal.stop()
        await bounded(self.peer.close(), CLOSE_S)
        await bounded(asyncio.gather(*self._reading), CLOSE_S)


def _candidates(sdp: str) -> list[dict[str, object]]:
    """The candidates of the offer's media section mid 0 (the audio's, which carries the
    bundle), as a browser's `icecandidate` events give them."""
    for section in sdp.split("\r\nm=")[1:]:
        lines = section.split("\r\n")
        if "a=mid:0" in lines:
            return [
                {"candidate": line.removeprefix("a="), "sdp_mid": "0", "sdp_mline_index": 0}
                for line in lines
                if line.startswith("a=candidate:")
            ]
    return []


# voice's entry point as the runtime builds it, each call's speech detector the fakes' tone
# detector and its turn analyzer one that ends each turn at its first pause.
FAKE_DETECTORS: CallsFactory = partial(
    VoiceCalls, speech_detector=ToneVAD, turn_analyzer=PauseAnalyzer
)


def _files(folder: Path) -> list[str]:
    return sorted(path.name for path in folder.iterdir())


def test_a_browser_like_peer_joins_speaks_and_hears_its_words_said_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = VoiceSettings(env="dev", storage=StorageSettings(var_dir=tmp_path / "var"))
    stt, tts = FakeSpeechToText([HEARD]), PitchedSpeech()
    runtime = VoiceRuntime(
        agent,
        settings=settings,
        identity=DevIdentity(),
        providers=Providers(stt=stt, tts=tts),
        _calls=FAKE_DETECTORS,
    )
    emitted: list[Event] = []

    @runtime.on(Event)
    async def observe(event: Event) -> None:
        emitted.append(event)

    asked: list[str] = []
    audio = PhraseCache.audio

    def asking(cache: PhraseCache, text: str, *, language: LanguageTag) -> AudioChunk:
        asked.append(text)
        return audio(cache, text, language=language)

    monkeypatch.setattr(PhraseCache, "audio", asking)
    app = FastAPI()
    app.include_router(runtime.router(), prefix=PREFIX)
    folder = settings.storage.var_dir / agent.name / "phrases"
    browsers: list[Browser] = []
    declared: list[str] = []
    left: list[asyncio.Task[Any]] = []

    def others() -> list[asyncio.Task[Any]]:
        return [task for task in asyncio.all_tasks() if task is not asyncio.current_task()]

    async def scene() -> None:
        async with asyncio.timeout(TEST_S):
            browsers.append(browser := Browser())
            try:
                async with serving(app) as http:
                    declared.extend(_files(folder))
                    await browser.connect(http)
                    await browser.talk()
            finally:
                await browser.close()
            try:
                await until(lambda: not others(), timeout=CLOSE_S)
            except TimeoutError:
                left.extend(others())

    asyncio.run(scene(), loop_factory=asyncio.SelectorEventLoop)
    (browser,) = browsers
    assert not left, left
    assert browser.peer.connectionState == "closed"

    # Its candidates went once the offer was answered, then their end, each answered.
    assert len(browser.patches) >= 2
    # The echo's words came back from the fake text-to-speech, once; the phrases from the cache.
    echo_s, phrases_s = len(HEARD), len(ENGLISH.greeting) + len(ENGLISH.echo_frame)
    assert abs(browser.heard_s(HEARD_HZ) - echo_s * SECONDS_PER_CHAR) <= TOLERANCE_S
    assert abs(browser.heard_s(PHRASE_HZ) - phrases_s * SECONDS_PER_CHAR) <= 2 * TOLERANCE_S
    assert [text for text, _ in tts.calls].count(HEARD) == 1 and len(stt.calls) == 1

    # The phrase cache, declared at the start, got no new file and was never asked for the
    # heard words, but for the greeting and the frame (invariant 8).
    assert declared and _files(folder) == declared
    assert HEARD not in asked and {ENGLISH.greeting, ENGLISH.echo_frame} <= set(asked)

    # Every message is t2v/1's, or SmallWebRTC's own `peerLeft` as the call ends, which the
    # client ignores; none that names a thing came twice.
    kinds = {kind.model_fields["type"].default for kind in SESSION_MESSAGES}
    for message in browser.messages:
        ours = message.get("v") == 1 and message["type"] in kinds
        assert ours or (message["type"] in RESERVED_TYPES and "v" not in message), message
    assert [m["reason"] for m in browser.of("ended")] == ["hangup"]
    captions = [
        (m["speaker"], m["turn_id"], m["reply_id"], m["clause"], m["text"])
        for m in browser.of("caption")
    ]
    assert captions == [
        ("agent", None, 0, 0, ENGLISH.greeting),
        ("caller", 0, None, None, HEARD),
        ("agent", 0, 1, 0, ENGLISH.echo_frame),
        ("agent", 0, 1, 1, HEARD),
    ]

    # No public event came twice: each the call sent, once.
    sent = Counter((type(event).__name__, event.turn_id) for event in emitted)
    assert sent == Counter(
        [
            ("CallStarted", None),
            ("AgentSpeechEnded", None),
            ("UserTurnEnded", 0),
            ("AgentSpeechEnded", 0),
            ("TurnMetrics", 0),
            ("CallEnded", None),
        ]
    )
    (ended,) = [event for event in emitted if isinstance(event, CallEnded)]
    report = ended.report
    assert [m["call_id"] for m in browser.of("hello")] == [report.call_id]
    assert report.ended_by == "hangup" and report.client is not None
    assert report.client.candidate_type == "host"
    (turn,) = report.turns
    assert (turn.heard, turn.said, turn.dropped) == (HEARD, f"{ENGLISH.echo_frame} {HEARD}", False)
    usage = {each.model: each for each in report.usage}
    tts_usage = usage[settings.tts.languages["en"].model]
    assert (tts_usage.requests, tts_usage.cache_hits) == (1, 2)
    written = (settings.storage.var_dir / REPORTS / f"{report.call_id}.json").read_text("utf-8")
    assert HEARD not in written

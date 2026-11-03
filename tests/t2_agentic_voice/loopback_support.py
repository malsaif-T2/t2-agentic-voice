"""What the loopback checks share (TD-087): plan 003's step 16 (test_loopback_call.py) and plan
005's step 9 (test_loopback_interruptions.py). Each runs one call as a browser makes it, through
the runtime's router (api/router.py), the real pipeline (voice/pipeline.py) and the echo session
(voice/session/), the providers fakes and the audio generated (no audio file:
tests/ole5_voice/evals/test_no_audio.py).

- `Browser` plays `t2v-client.js`'s part: a local aiortc peer built with
  `RTCConfiguration(iceServers=[])` (tests/conftest.py makes aiortc's default list raise), its
  microphone a `Signal` (a sine the fake speech detector hears as speech), a data channel, every
  message it was sent with when it came, and the agent's audio, each frame's pitch, length, when
  the client's track gave it and when its packet reached the client's peer (`arrived`: aiortc's
  receiver holds four packets before it decodes one, as a browser's jitter buffer holds some, so
  what reaches the client is timed at its packet);
- the audio, all generated: loopback_audio.py's;
- `echo_runtime`, the minimal example's echo agent (`DevIdentity`, `env` dev, from loopback) on
  the fakes, each call's speech detector the fakes' tone detector and its turn analyzer one that
  ends each turn at its first pause, its router served under PREFIX;
- `run_call`, which runs one call on a selector loop, as `serve()` runs it (api/server.py), every
  wait bounded, every peer closed, and says which tasks were left.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Awaitable, Callable, Iterator
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Any, cast

import httpx
from aiortc import RTCBundlePolicy, RTCConfiguration, RTCPeerConnection, RTCSessionDescription
from aiortc.mediastreams import MediaStreamError, MediaStreamTrack
from aiortc.rtp import RtpPacket
from fastapi import FastAPI
from minimal_example.app import agent
from t2_agentic_voice.api.runtime import Providers, VoiceRuntime
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.events import Event
from t2_agentic_voice.domain.ports.speech_to_text import SpeechToText
from t2_agentic_voice.identity import DevIdentity
from t2_agentic_voice.voice.calls import CallsFactory, VoiceCalls

from tests.t2_agentic_voice.api.runtime_support import PREFIX, patch, post, serving
from tests.t2_agentic_voice.loopback_audio import BIN_HZ, Frame, PitchedSpeech, Signal, pitch
from tests.t2_agentic_voice.voice.kit import PauseAnalyzer, ToneVAD, until

ENGLISH = agent.languages[0]
# How long the client waits after the greeting before it speaks (past the session's 300 ms).
AFTER_GREETING_S = 0.5
# The bound on each wait and on each peer's close, and on the whole call, start to stop.
WAIT_S, CLOSE_S, TEST_S = 10.0, 5.0, 30.0
QUIET = ("not_offered", "ice_completed", "call_ended")
# The RTP timestamps of a call, which aiortc's receiver counts from its first (its
# `TimestampMapper`), modulo this.
_RTP_WRAP = 1 << 32


async def bounded[T](step: Awaitable[T], seconds: float = WAIT_S) -> T:
    """`step`, awaited for at most `seconds`."""
    return await asyncio.wait_for(step, seconds)


@dataclass(frozen=True)
class Heard:
    """One frame of the agent's audio as the client heard it: its pitch (None when quiet), its
    length, when the client's track gave it (`at`, on `time.perf_counter`, the session's clock:
    io.py), and its timestamp in samples (`pts`, as aiortc's receiver counts it)."""

    hz: float | None
    seconds: float
    at: float
    pts: int | None


class Browser:
    """The browser's part (`t2v-client.js`): its peer, with the signal as its microphone and a
    data channel; the messages it was sent and when each came; the agent's audio as it heard it
    (`heard`) and when each packet of it reached the peer; and each PATCH's answer. Built inside
    the loop, which aiortc's sender keeps."""

    def __init__(self) -> None:
        config = RTCConfiguration(iceServers=[], bundlePolicy=RTCBundlePolicy.MAX_BUNDLE)
        self.peer = RTCPeerConnection(config)
        self.signal = Signal()
        self.peer.addTrack(self.signal)  # the audio first, so its m-line is mid 0
        self.channel = self.peer.createDataChannel("t2v", ordered=True)
        self.messages: list[dict[str, Any]] = []
        self.message_at: list[float] = []
        self.heard: list[Heard] = []
        self.patches: list[int | str] = []
        self._arrivals: dict[int, float] = {}
        self._origin: int | None = None
        self._reading: list[asyncio.Task[None]] = []
        self.channel.on("message", self._message)
        self.peer.on("track", self._track)
        (receiver,) = self.peer.getReceivers()
        handle = receiver._handle_rtp_packet

        async def arrived(packet: RtpPacket, arrival_time_ms: int) -> None:
            self._arrived(packet)
            await handle(packet, arrival_time_ms)

        receiver._handle_rtp_packet = arrived  # type: ignore[method-assign]

    def _message(self, data: str) -> None:
        self.messages.append(json.loads(data))
        self.message_at.append(time.perf_counter())

    def _arrived(self, packet: RtpPacket) -> None:
        """A packet of the agent's audio reached the peer: its time, by its timestamp counted
        from the first, as aiortc's receiver counts it."""
        if self._origin is None:
            self._origin = packet.timestamp
        counted = (packet.timestamp - self._origin) % _RTP_WRAP
        self._arrivals.setdefault(counted, time.perf_counter())

    def arrived(self, frame: Heard) -> float:
        """When the packet of `frame` reached the client's peer; KeyError for none."""
        if frame.pts is None:
            raise KeyError("a frame with no timestamp")
        return self._arrivals[frame.pts]

    def _track(self, track: MediaStreamTrack) -> None:
        self._reading.append(asyncio.ensure_future(self._read(track)))

    async def _read(self, track: MediaStreamTrack) -> None:
        while True:
            try:
                frame = cast(Frame, await track.recv())
            except MediaStreamError:
                return
            seconds = frame.samples / frame.sample_rate
            self.heard.append(Heard(pitch(frame), seconds, time.perf_counter(), frame.pts))

    def received(self) -> Iterator[tuple[float, dict[str, Any]]]:
        """Each message the session sent, with when it came, in order."""
        return zip(self.message_at, self.messages, strict=True)

    def came(self, kind: str) -> list[float]:
        """When each t2v/1 message of `kind` came, in order."""
        return [at for at, m in self.received() if m.get("v") == 1 and m["type"] == kind]

    def of(self, kind: str) -> list[dict[str, Any]]:
        """The t2v/1 messages of `kind` the session sent, in order."""
        return [m for m in self.messages if m.get("v") == 1 and m["type"] == kind]

    def states(self) -> list[str]:
        return [m["state"] for m in self.of("state")]

    def heard_s(self, hz: float) -> float:
        """How long the agent's audio was heard at `hz`."""
        return sum(f.seconds for f in self.heard if f.hz is not None and abs(f.hz - hz) <= BIN_HZ)

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

    async def greeted(self) -> None:
        """Say hello once the channel opens, then wait out the greeting."""
        await until(lambda: self.channel.readyState == "open", timeout=WAIT_S)
        self.send("hello", client="aiortc-loopback/1")
        self.send("client_stats", candidate_type="host")
        await until(lambda: self.states()[-2:] == ["speaking", "listening"], timeout=WAIT_S)
        await asyncio.sleep(AFTER_GREETING_S)

    async def hang_up(self) -> None:
        """Hang up, and wait for the call's end and the channel's close."""
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


def echo_runtime(
    settings: VoiceSettings, stt: SpeechToText, tts: PitchedSpeech
) -> tuple[FastAPI, list[Event]]:
    """The minimal example's echo agent on the fakes with `settings`, its router served under
    PREFIX, and every public event it emits, in order."""
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

    app = FastAPI()
    app.include_router(runtime.router(), prefix=PREFIX)
    return app, emitted


def files(folder: Path) -> list[str]:
    return sorted(path.name for path in folder.iterdir())


def run_call(
    app: FastAPI, steps: Callable[[Browser, httpx.AsyncClient], Awaitable[None]]
) -> tuple[Browser, list[asyncio.Task[Any]]]:
    """One call: a browser takes `steps` against `app` while its lifespan runs, then closes its
    peer; on a selector loop, bounded by TEST_S. The browser, and the tasks still running
    CLOSE_S after (none, for a call that leaks none)."""
    browsers: list[Browser] = []
    left: list[asyncio.Task[Any]] = []

    def others() -> list[asyncio.Task[Any]]:
        return [task for task in asyncio.all_tasks() if task is not asyncio.current_task()]

    async def scene() -> None:
        async with asyncio.timeout(TEST_S):
            browsers.append(browser := Browser())
            try:
                async with serving(app) as http:
                    await steps(browser, http)
            finally:
                await browser.close()
            try:
                await until(lambda: not others(), timeout=CLOSE_S)
            except TimeoutError:
                left.extend(others())

    asyncio.run(scene(), loop_factory=asyncio.SelectorEventLoop)
    (browser,) = browsers
    return browser, left

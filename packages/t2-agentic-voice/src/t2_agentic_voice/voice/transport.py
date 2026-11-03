"""One call's transport: its WebRTC peer over Pipecat's Small WebRTC, and the taps around the
pipeline's input and output (plan 003's appendix, "Changes to the plan's interfaces", items 7,
10, 14, 15, 20 and 21).

- `WebRTCPeer` answers one call's SDP offer through a request handler of its own, always with
  `pc_id=None`, `restart_pc=None` and `type="offer"`, and keeps Pipecat's `pc_id`, which holds
  `#` and lets whoever names it renegotiate a live call, to itself, never taking one from the
  client (item 10). Its peer gets exactly the settings' ICE servers, an empty list included,
  never aiortc's default, which asks Google's STUN server (the design's 11). An offer that marks
  the end of its candidates and holds no UDP candidate is refused, since aioice 0.11.0 would
  leave its peer `new`, with no event and no timeout (F7, item 21). Each trickled candidate is
  read before Pipecat sees it, since aiortc answers a malformed line with an AssertionError
  (item 10); an empty one is the end of candidates, which reaches aioice (item 11). Its close
  is bounded (`CLOSE_TIMEOUT_S`), since on Windows' proactor loop 2 or 3 of 16 closes hung
  (item 20).
- `transport_params`: audio in and out on, the caller's audio resampled to the speech
  detector's 16 kHz mono, the agent's sent at the pipeline's 24 kHz (item 15).
- `CallerTap`, after the input, hands the session the caller's audio as the pipeline hears it
  (`CallerAudio`); `ClauseGate`, before the output, drops any frame of a clause a stop dropped
  that slipped past Pipecat's interruption (a frame waiting in a processor's input queue when
  the interruption reaches it is taken after it); and `OutputTap`, after the output, hands the
  agent's audio as the output transport sent it (`AgentAudio`) and reports each clause's end
  as it leaves the output (session_bridge.py's markers, text-to-speech contexts' stop frames).
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Sequence

from pipecat.frames.frames import (
    Frame,
    InputAudioRawFrame,
    OutputAudioRawFrame,
    TTSStoppedFrame,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.transports.base_transport import TransportParams
from pipecat.transports.smallwebrtc.connection import IceServer, SmallWebRTCConnection
from pipecat.transports.smallwebrtc.request_handler import (
    IceCandidate,
    SmallWebRTCPatchRequest,
    SmallWebRTCRequest,
    SmallWebRTCRequestHandler,
)
from pipecat.transports.smallwebrtc.transport import SmallWebRTCTransport

from t2_agentic_voice.core.errors import InvalidRequestError
from t2_agentic_voice.core.logging import get_logger
from t2_agentic_voice.voice.session.session_events import AgentAudio, CallerAudio
from t2_agentic_voice.voice.session_bridge import CallEvents, ClauseEndFrame, ClauseKey, clause_of

log = get_logger(__name__)

# The speech detector's rate (Silero takes 16 or 8 kHz) and the pipeline's output rate.
IN_RATE = 16_000
OUT_RATE = 24_000
# How long a peer's close may take before the call is forgotten without it (item 20; the
# agent's bound, far over a close that does not hang).
CLOSE_TIMEOUT_S = 5.0
# voice's own deadline from offer to connected (items 11 and 21): a local call connects in
# under half a second (the spike's 111 to 285 ms), and a relayed one in a few, so a third of
# Pipecat's 60 s shows a failed call sooner and ends the F7 hang (the agent's value).
CONNECT_DEADLINE_S = 20.0
_CANDIDATE_TYPES = frozenset({"host", "srflx", "prflx", "relay"})
_PROTOCOLS = frozenset({"udp", "tcp"})


def transport_params() -> TransportParams:
    """A call's transport: audio in, mono at the speech detector's rate, and audio out at the
    pipeline's rate, with no silence after the end (the call is cancelled, never drained)."""
    return TransportParams(
        audio_in_enabled=True,
        audio_in_sample_rate=IN_RATE,
        audio_in_channels=1,
        audio_out_enabled=True,
        audio_out_sample_rate=OUT_RATE,
        audio_out_channels=1,
        audio_out_end_silence_secs=0,
    )


def check_offer(offer: str) -> None:
    """InvalidRequestError for the offer aioice 0.11.0 hangs on: one that marks the end of its
    candidates and holds no UDP candidate (F7)."""
    lines = [line.strip() for line in offer.splitlines()]
    ended = "a=end-of-candidates" in lines
    udp = any(
        line.startswith("a=candidate:")
        and len(parts := line.split()) > 2
        and parts[2].lower() == "udp"
        for line in lines
    )
    if ended and not udp:
        raise InvalidRequestError("The offer ends its candidates without one this server can use.")


def check_candidate(line: str) -> None:
    """InvalidRequestError, naming no part of it, for a candidate line aiortc cannot read: a
    foundation, a component, a protocol, a priority, an address, a port, `typ` and a type,
    then pairs of a name and a value, the related port a number."""
    bits = line.removeprefix("candidate:").split()
    try:
        readable = (
            len(bits) >= 8
            and 0 < int(bits[1]) <= 256
            and bits[2].lower() in _PROTOCOLS
            and int(bits[3]) >= 0
            and 0 <= int(bits[5]) <= 65_535
            and bits[6] == "typ"
            and bits[7] in _CANDIDATE_TYPES
            and len(bits) % 2 == 0
            and all(
                int(v) >= 0 for k, v in zip(bits[8::2], bits[9::2], strict=True) if k == "rport"
            )
        )
    except ValueError:
        readable = False
    if not readable:
        raise InvalidRequestError("A candidate could not be read.")


class WebRTCPeer:
    """One call's WebRTC peer, its offer answered (`answer_sdp`) and its `pc_id` kept here."""

    def __init__(
        self,
        handler: SmallWebRTCRequestHandler,
        connection: SmallWebRTCConnection,
        answer_sdp: str,
        pc_id: str,
    ) -> None:
        self._handler = handler
        self.connection = connection
        self.answer_sdp = answer_sdp
        self._pc_id = pc_id

    @classmethod
    async def answer(cls, offer: str, ice_servers: Sequence[str]) -> WebRTCPeer:
        """A peer that answers `offer`, given exactly `ice_servers`. InvalidRequestError, with
        no part of the offer, for one it refuses (F7) or cannot read."""
        check_offer(offer)
        handler = SmallWebRTCRequestHandler(
            ice_servers=[IceServer(urls=url) for url in ice_servers]
        )
        made: list[SmallWebRTCConnection] = []

        async def keep(connection: SmallWebRTCConnection) -> None:
            made.append(connection)

        request = SmallWebRTCRequest(
            sdp=offer, type="offer", pc_id=None, restart_pc=None, request_data=None
        )
        try:  # a new peer comes through `keep`; one with no answer raises
            answer = await handler.handle_web_request(request, keep) or {}
        except Exception as error:
            log.info("offer_unreadable", error=type(error).__name__)
            for connection in made:
                await _close(connection)
            raise InvalidRequestError("The offer could not be read.") from None
        return cls(handler, made[0], answer["sdp"], answer["pc_id"])

    def transport(self) -> SmallWebRTCTransport:
        """The call's Pipecat transport over this peer."""
        return SmallWebRTCTransport(self.connection, transport_params())

    async def add_candidates(self, candidates: Sequence[tuple[str, str, int]]) -> None:
        """Hand the peer its trickled candidates (each a line, its media's ID and its m-line's
        index), in order, each read first; an empty line is the end of candidates.
        InvalidRequestError for a line it cannot read, none of them then given."""
        for line, _, _ in candidates:
            if line:
                check_candidate(line)
        patch = SmallWebRTCPatchRequest(
            pc_id=self._pc_id,
            candidates=[
                IceCandidate(candidate=line, sdp_mid=mid, sdp_mline_index=index)
                for line, mid, index in candidates
            ],
        )
        await self._handler.handle_patch_request(patch)

    def on_connection(
        self, failed: Callable[[], Awaitable[None]], closed: Callable[[], Awaitable[None]]
    ) -> None:
        """Call `failed` when the peer's ICE fails and `closed` when the peer closes."""

        async def on_failed(connection: SmallWebRTCConnection) -> None:
            await failed()

        async def on_closed(connection: SmallWebRTCConnection) -> None:
            await closed()

        self.connection.add_event_handler("failed", on_failed)
        self.connection.add_event_handler("closed", on_closed)

    async def close(self) -> None:
        """Close the peer, bounded by `CLOSE_TIMEOUT_S`."""
        await _close(self.connection)


async def _close(connection: SmallWebRTCConnection) -> None:
    try:
        disconnect: Callable[[], Awaitable[None]] = connection.disconnect
        await asyncio.wait_for(disconnect(), CLOSE_TIMEOUT_S)
    except TimeoutError:
        log.warning("peer_close_timeout", waited_s=CLOSE_TIMEOUT_S)
    except Exception as error:  # a peer that cannot close is forgotten all the same
        log.warning("peer_close_failed", error=type(error).__name__)


class CallerTap(FrameProcessor):
    """After the input: each piece of the caller's audio, as the pipeline hears it, to the
    session (`CallerAudio`)."""

    def __init__(self, events: CallEvents) -> None:
        super().__init__(name="t2v-caller-tap")
        self._events = events

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        if isinstance(frame, InputAudioRawFrame) and direction == FrameDirection.DOWNSTREAM:
            now = self._events.clock.now()
            heard = CallerAudio(pcm16=frame.audio, sample_rate=frame.sample_rate, at=now)
            self._events.hand(heard)
        await self.push_frame(frame, direction)


def _clause(frame: Frame) -> ClauseKey | None:
    if isinstance(frame, ClauseEndFrame):
        return frame.key
    context = getattr(frame, "context_id", None)
    return clause_of(context) if isinstance(context, str) else None


class ClauseGate(FrameProcessor):
    """Before the output: drops every frame of a clause a stop dropped."""

    def __init__(self, events: CallEvents) -> None:
        super().__init__(name="t2v-clause-gate")
        self._events = events

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        if direction == FrameDirection.DOWNSTREAM and _clause(frame) in self._events.dropped:
            return
        await self.push_frame(frame, direction)


class OutputTap(FrameProcessor):
    """After the output: the agent's audio as the output transport sent it, to the session
    (`AgentAudio`), and each clause's end as it leaves the output, to `played`."""

    def __init__(self, events: CallEvents, played: Callable[[ClauseKey], None]) -> None:
        super().__init__(name="t2v-output-tap")
        self._events = events
        self._played = played

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        if direction == FrameDirection.DOWNSTREAM:
            if isinstance(frame, OutputAudioRawFrame) and frame.audio:
                now = self._events.clock.now()
                sent = AgentAudio(pcm16=frame.audio, sample_rate=frame.sample_rate, at=now)
                self._events.hand(sent)
            elif isinstance(frame, TTSStoppedFrame | ClauseEndFrame):
                key = _clause(frame)
                if key is not None:
                    self._played(key)
        await self.push_frame(frame, direction)

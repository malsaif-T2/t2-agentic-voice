"""voice's entry point, which api calls: every call of one runtime, from its SDP offer to its end
(plan 003, step 10). Built by plan 003's Track E; until then a stub. The items cited are plan
003's appendix, "Changes to the plan's interfaces"; what Track E builds:

- **Start.** The runtime's lifespan builds one `VoiceCalls` and starts it (`start`), which builds
  Silero VAD and Smart Turn v3.2, each loading its ONNX model on the CPU there, never at import:
  importing onnxruntime takes 8 to 12 s a process (item 24). This module imports no Pipecat at
  its top, since api imports it when the library is imported, and `import t2_agentic_voice` and
  `t2v --help` import no Pipecat (GP-17). Pipecat's loguru namespace is switched off before voice
  first imports Pipecat (Q2, item 16); the transport loggers are held at WARNING unless
  `logging.content` is on (`core.logging.hold_transport_loggers`); `PIPECAT_SETUP_FILES` and
  `PIPECAT_SMART_TURN_LOG_DATA` set to a value are refused (item 17).
- **The offer** (`answer`). One Pipecat pipeline per call, its session a `CallSession`
  (`voice/session/`). Pipecat's request handler keys its connections on a `pc_id` it chooses,
  which holds `#`; it renegotiates a live call for whoever names that ID, and leaves a stale key
  behind on a restart. So voice keeps the `pc_id` behind the call's ID, never takes one from the
  client, and passes `pc_id=None`, `restart_pc=None` and `type="offer"`, or builds
  `SmallWebRTCConnection` itself (item 10). The handler swallows its callback's exceptions, so
  voice checks that the call's pipeline started. An offer that marks the end of its candidates
  (`a=end-of-candidates`) and holds no usable candidate is refused with an InvalidRequestError:
  aioice 0.11.0 would leave its peer `new`, with no event and no timeout (F7, item 21). A call
  not connected within voice's own deadline from offer to connected, shorter than Pipecat's
  60 s (a value Track E sets and records), ends as a `TransportFailure` at `connect`, so a failed
  call shows sooner than Pipecat's timeout, and the F7 hang ends too (items 11 and 21). Each
  aiortc peer gets an explicit ICE server list, never aiortc's default, which asks Google's STUN
  server (the design's 11: the library contacts nothing beyond its outbound hosts).
- **Candidates** (`add_candidates`). Each one is checked before Pipecat sees it, since aiortc
  answers a malformed line with an AssertionError (item 10); an empty one marks their end, the
  client's end-of-candidates PATCH, which reaches aioice (item 11).
- **The end** (`end`, `aclose`). Each peer's close is bounded by a timeout, since on Windows'
  proactor loop 2 or 3 of 16 closes hung (item 20); a call's session always hangs up, with its
  report written, before voice forgets the call.

api does the HTTP side: the offer secret, a second offer's 409, the quiet 409 for a PATCH after
ICE completed (from `phase`), and mapping each error to its one shape.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal, Protocol

from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.events import CallId
from t2_agentic_voice.core.identity import Caller, Consent
from t2_agentic_voice.core.tracing import Tracing
from t2_agentic_voice.domain.declaration import VoiceAgent
from t2_agentic_voice.domain.ports.speech_to_text import SpeechToText
from t2_agentic_voice.domain.ports.text_to_speech import TextToSpeech
from t2_agentic_voice.voice.session.io import SYSTEM_CLOCK, Clock, EventSink, Phrases

_STUB = "voice's entry point is built by plan 003's Track E"

# Where a call stands, as api asks before it takes a PATCH: its offer answered and its
# connection being set up; connected (ICE completed, so the offer secret stops working); or
# ended.
CallPhase = Literal["connecting", "connected", "ended"]


@dataclass(frozen=True, kw_only=True)
class Candidate:
    """One trickled ICE candidate, as api parsed it from `PATCH /offer` (api/protocol.py's
    `IceCandidate`): its line, empty for the end of candidates; its media's ID; and its m-line's
    index."""

    candidate: str
    sdp_mid: str
    sdp_mline_index: int


class Calls(Protocol):
    """voice's entry point as api uses it: `VoiceCalls`, or a test's fake."""

    async def start(self) -> None:
        """Build what every call shares, the speech detector's and the turn analyzer's models
        among it; called once, at the runtime's start, before any offer."""

    async def answer(self, call_id: CallId, offer: str, *, caller: Caller, consent: Consent) -> str:
        """Answer the call's SDP offer with its SDP answer, the call's pipeline and session
        started. InvalidRequestError for an offer it refuses (one it cannot read, or the F7
        offer), or for a call ID it already holds; the call is then not started."""

    async def add_candidates(self, call_id: CallId, candidates: Sequence[Candidate]) -> None:
        """Hand the call's peer its trickled candidates, in order. NotFoundError for a call it
        does not hold; InvalidRequestError for a candidate line it cannot read, none of the
        candidates then given."""

    def phase(self, call_id: CallId) -> CallPhase | None:
        """Where the call stands; None for a call it does not hold."""

    async def end(self, call_id: CallId) -> None:
        """End the call now (`server`), if it holds it; return once its peer is closed."""

    async def aclose(self) -> None:
        """End every call and release what `start` built; called once, at the runtime's
        stop."""


class VoiceCalls:
    """Every call of one runtime over SmallWebRTC, each its own Pipecat pipeline and session, for
    `agent` with `settings`: speech-to-text through `stt`, text-to-speech through `tts`, the
    fixed phrases from `phrases`, its turns traced on `tracing`, its public events sent to
    `emit`, its times on `clock`. Built cheaply, with no IO; `start` loads the models."""

    def __init__(
        self,
        *,
        agent: VoiceAgent,
        settings: VoiceSettings,
        stt: SpeechToText,
        tts: TextToSpeech,
        phrases: Phrases,
        tracing: Tracing,
        emit: EventSink,
        clock: Clock = SYSTEM_CLOCK,
    ) -> None:
        raise NotImplementedError(_STUB)

    async def start(self) -> None:
        """Build Silero VAD and Smart Turn v3.2 (the `Calls` protocol's `start`)."""
        raise NotImplementedError(_STUB)

    async def answer(self, call_id: CallId, offer: str, *, caller: Caller, consent: Consent) -> str:
        """Answer the call's SDP offer (the `Calls` protocol's `answer`)."""
        raise NotImplementedError(_STUB)

    async def add_candidates(self, call_id: CallId, candidates: Sequence[Candidate]) -> None:
        """Hand the call's peer its candidates (the `Calls` protocol's `add_candidates`)."""
        raise NotImplementedError(_STUB)

    def phase(self, call_id: CallId) -> CallPhase | None:
        """Where the call stands (the `Calls` protocol's `phase`)."""
        raise NotImplementedError(_STUB)

    async def end(self, call_id: CallId) -> None:
        """End the call now (the `Calls` protocol's `end`)."""
        raise NotImplementedError(_STUB)

    async def aclose(self) -> None:
        """End every call, each close bounded (the `Calls` protocol's `aclose`)."""
        raise NotImplementedError(_STUB)

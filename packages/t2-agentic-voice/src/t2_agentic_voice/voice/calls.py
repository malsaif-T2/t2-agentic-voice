"""voice's entry point, which api calls: every call of one runtime, from its SDP offer to its end
(plan 003, step 10). Built by plan 003's Track E. The items cited are plan
003's appendix, "Changes to the plan's interfaces"; what Track E builds:

- **Start.** The runtime's lifespan builds one `VoiceCalls` and starts it (`start`), which
  imports onnxruntime and warms one pair of models, a Silero VAD and a Smart Turn v3.2, each
  loading its ONNX model on the CPU there, never at import: importing onnxruntime takes 8 to
  12 s a process (item 24). This module imports no Pipecat at its top, since api imports it
  when the library is imported, and `import t2_agentic_voice` and `t2v --help` import no
  Pipecat (GP-17). Pipecat's loguru namespace is switched off before voice
  first imports Pipecat (Q2, item 16); the transport loggers are held at WARNING unless
  `logging.content` is on (`core.logging.hold_transport_loggers`); `PIPECAT_SETUP_FILES` and
  `PIPECAT_SMART_TURN_LOG_DATA` set to a value are refused (item 17), each named in a
  ConfigurationError, never its value. voice reads no variable itself (ARCH-ENV): it asks
  `core.config.foreign_set`, which answers by name however the settings were built. Track E's
  test: each one set (monkeypatch) makes `start` refuse, naming it.
- **The detectors.** Each call gets its own speech detector and turn analyzer, since each of
  Pipecat's keeps one stream's state (a `VADAnalyzer`'s buffer, Silero's model state, Smart
  Turn's audio) and its public constructor loads its own ONNX session, sharing none:
  `VoiceCalls` makes them with the factories it is given, and with none builds Silero and Smart
  Turn v3.2 from the settings' `turns` group, each loading its model again for the call (after
  the warm-up, the review's probe on the owner's machine took 85.2 to 102.3 ms for Silero and
  106.6 to 134.2 ms for Smart Turn). So `VoiceCalls` calls each factory off the event loop
  (`await asyncio.to_thread(factory)`) before it answers the offer, and no live call's audio
  waits on a join. Track E's test: while `answer` builds a call with a factory that blocks for
  0.2 s (`time.sleep`), a 20 ms ticker on the same loop misses no deadline by more than a few ms
  (`TICKER_BOUND_S`, Track E's bound, half the factory's block). A test gives fakes (step 16's
  sends a generated signal through a fake speech detector), through the runtime's private
  `_calls` (api/runtime.py); `start` warms the factories it is given, so a test's fakes load no
  ONNX model. With `turns.smart_turn` off, no turn analyzer is built: every pause ends a turn.
- **The offer** (`answer`). One Pipecat pipeline per call, its session a `CallSession`
  (`voice/session/`). Pipecat's request handler keys its connections on a `pc_id` it chooses,
  which holds `#`; it renegotiates a live call for whoever names that ID, and leaves a stale key
  behind on a restart. So voice keeps the `pc_id` behind the call's ID, never takes one from the
  client, and passes `pc_id=None`, `restart_pc=None` and `type="offer"`, or builds
  `SmallWebRTCConnection` itself (item 10). The handler swallows its callback's exceptions, so
  voice checks that the call's pipeline started. An offer that marks the end of its candidates
  (`a=end-of-candidates`) and holds no UDP candidate is refused with an InvalidRequestError:
  aioice 0.11.0 would leave its peer `new`, with no event and no timeout (F7, item 21). A call
  not connected within voice's own deadline from offer to connected, shorter than Pipecat's
  60 s (transport.py's `CONNECT_DEADLINE_S`, 20 s), ends as a `TransportFailure` at
  `connect`, so a failed call shows sooner than Pipecat's timeout, and the F7 hang ends too
  (items 11 and 21). Each
  aiortc peer gets an explicit ICE server list, never aiortc's default, which asks Google's STUN
  server (the design's 11: the library contacts nothing beyond its outbound hosts).
- **Candidates** (`add_candidates`). Each one is checked before Pipecat sees it, since aiortc
  answers a malformed line with an AssertionError (item 10); an empty one marks their end, the
  client's end-of-candidates PATCH, which reaches aioice (item 11).
- **Messages.** The session bridge hands the session each client message as `on_app_message`
  gives it, the object Pipecat parsed (voice/protocol.py's object path), parsed with
  `parse_client_message`. Pipecat parsed the channel's text first, with no bound of ours (up to
  the transport's message size), and holds the messages that come before the call connects, so
  the bound is on the object written back as compact JSON. Track E's test: a message sent on a
  test peer's data channel reaches `parse_client_message` as that object, and one whose compact
  JSON is over MAX_CLIENT_MESSAGE_BYTES is dropped.
- **The end** (`end`, `aclose`). Each peer's close is bounded by a timeout, since on Windows'
  proactor loop 2 or 3 of 16 closes hung (item 20). A call's session always hangs up, and voice
  ends the call's stream with the session's `aclose`, which returns once its report is written
  (voice/session/io.py's end), before it forgets the call. Voice forgets a call once it has
  ended and its peer has closed: `phase` says `ended` only until then, and None after, as for a
  call it never held.

api does the HTTP side: the offer secret, a second offer's 409, the quiet 409 for a PATCH before
voice answered the call's offer or after ICE completed or the call ended, and mapping each error
to its one shape; it never hands voice the candidates of a call whose offer voice has not
answered. It keeps its own record of the calls it joined (each one's offer secret, and the
call's language and identity until its offer), so a PATCH for a call whose offer was answered
and whose `phase` is `ended` or None gets the quiet 409 `call_ended`. It drops a record a
bounded time later (api/runtime.py): a join never offered once its join token's window has
passed, and an answered call `FORGOTTEN_KEPT_S` (60 s) after voice forgets it; a request for
the call then gets 403 `forbidden`, as for a call never joined.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, Protocol

from t2_agentic_voice.core.config import VoiceSettings, foreign_set
from t2_agentic_voice.core.errors import ConfigurationError, InvalidRequestError, NotFoundError
from t2_agentic_voice.core.events import CallId
from t2_agentic_voice.core.identity import Caller, Consent
from t2_agentic_voice.core.logging import get_logger, hold_transport_loggers
from t2_agentic_voice.core.tracing import Tracing
from t2_agentic_voice.domain.declaration import Language, VoiceAgent
from t2_agentic_voice.domain.ports.action_jobs import ActionJobs
from t2_agentic_voice.domain.ports.chat_model import ChatModel
from t2_agentic_voice.domain.ports.language_classifier import LanguageClassifier
from t2_agentic_voice.domain.ports.speech_to_text import SpeechToText
from t2_agentic_voice.domain.ports.text_to_speech import TextToSpeech
from t2_agentic_voice.voice.loguru_policy import switch_pipecat_off
from t2_agentic_voice.voice.session.call import CallSession
from t2_agentic_voice.voice.session.io import (
    SYSTEM_CLOCK,
    CallSetup,
    Clock,
    EventSink,
    PhraseAudio,
    Session,
)
from t2_agentic_voice.voice.talkers import TalkerFactory, talker_for, talks

if TYPE_CHECKING:  # named in annotations only: this module imports no Pipecat (above)
    from pipecat.audio.turn.base_turn_analyzer import BaseTurnAnalyzer
    from pipecat.audio.vad.vad_analyzer import VADAnalyzer
    from pipecat.processors.frame_processor import FrameProcessor
    from pipecat.transports.base_output import BaseOutputTransport

    from t2_agentic_voice.voice.pipeline import CallPipeline, WebRTCCall

log = get_logger(__name__)

# Pipecat's variables that change what a call does whatever is passed in code: one executes the
# files it names in every pipeline, the other writes every turn's audio to disk (plan 003's
# appendix, item 17). `start` refuses either when set.
REFUSED_VARIABLES = ("PIPECAT_SETUP_FILES", "PIPECAT_SMART_TURN_LOG_DATA")
# The bound Track E's test holds a 20 ms ticker to while `answer` builds a call whose factory
# blocks for 0.2 s: half the block, so a factory run on the loop fails it, with room for a
# machine under load and Windows' 15.6 ms timer (the agent's value).
TICKER_BOUND_S = 0.1


# Where a call stands, as api asks before it takes a PATCH: its offer answered and its
# connection being set up; connected (ICE completed, so the offer secret stops working); or
# ended, until voice forgets it (its peer closed).
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
        """Prepare what every call needs (`VoiceCalls` imports onnxruntime and warms one pair of
        models: above); called once, at the runtime's start, before any offer."""

    async def answer(
        self, call_id: CallId, offer: str, *, caller: Caller, consent: Consent, language: Language
    ) -> str:
        """Answer the call's SDP offer with its SDP answer, the call's pipeline and session
        started, for `caller` with `consent`, held in `language` (the agent's, which api
        resolved at join with `VoiceAgent.call_language`). InvalidRequestError for an offer it
        refuses (one it cannot read, or the F7 offer), or for a call ID it already holds; the
        call is then not started."""

    async def add_candidates(self, call_id: CallId, candidates: Sequence[Candidate]) -> None:
        """Hand the call's peer its trickled candidates, in order. NotFoundError for a call it
        does not hold or that has ended; InvalidRequestError for a candidate line it cannot
        read, none of the candidates then given."""

    def phase(self, call_id: CallId) -> CallPhase | None:
        """Where the call stands; None for a call it does not hold, an ended call it has
        forgotten included (once its peer closed)."""

    async def end(self, call_id: CallId) -> None:
        """End the call now (`server`), if it holds it; return once its peer is closed."""

    async def aclose(self) -> None:
        """End every call and release what `start` built; called once, at the runtime's
        stop."""


class CallsFactory(Protocol):
    """How the runtime builds voice's entry point in its lifespan: `VoiceCalls` itself, or a
    test's function that returns a fake (the runtime's private `_calls`)."""

    def __call__(
        self,
        *,
        agent: VoiceAgent,
        settings: VoiceSettings,
        stt: SpeechToText,
        tts: TextToSpeech,
        phrases: PhraseAudio,
        tracing: Tracing,
        emit: EventSink,
        clock: Clock = SYSTEM_CLOCK,
        talker: TalkerFactory | None = None,
        chat: ChatModel | None = None,
        action_jobs: ActionJobs | None = None,
        classifier: LanguageClassifier | None = None,
    ) -> Calls:
        """voice's entry point for the runtime's calls, built with no IO."""


class VoiceCalls:
    """Every call of one runtime over SmallWebRTC, each its own Pipecat pipeline and session, for
    `agent` with `settings`: speech-to-text through `stt`, text-to-speech through `tts`, the
    fixed phrases from `phrases`, its turns traced on `tracing`, its public events sent to
    `emit`, its times on `clock`. Each call's speech detector comes from `speech_detector` and
    its turn analyzer from `turn_analyzer`, each called once per call, off the event loop; None
    builds Silero VAD and Smart Turn v3.2, each loading its model for the call. A call of an
    agent that runs the talker gets its own, built by `talker` (voice/talkers.py), and `chat`,
    the chat model that decides an overlap the rule left uncertain, for an agent that asks
    for it (D-069). `action_jobs` carries out each call's confirmed actions (plan 007), one
    for every call, which it tells apart by the call's ID; with none, a call's confirmed yes is
    told as the `error` notice and nothing is sent. `classifier`, loaded by the runtime, hears
    each turn's language under `stt.live_language = "classified"` (plan 007's Block H). Built
    cheaply, with no IO; `start` imports onnxruntime and warms one pair of models."""

    def __init__(
        self,
        *,
        agent: VoiceAgent,
        settings: VoiceSettings,
        stt: SpeechToText,
        tts: TextToSpeech,
        phrases: PhraseAudio,
        tracing: Tracing,
        emit: EventSink,
        clock: Clock = SYSTEM_CLOCK,
        talker: TalkerFactory | None = None,
        chat: ChatModel | None = None,
        action_jobs: ActionJobs | None = None,
        classifier: LanguageClassifier | None = None,
        speech_detector: Callable[[], VADAnalyzer] | None = None,
        turn_analyzer: Callable[[], BaseTurnAnalyzer] | None = None,
    ) -> None:
        self._talker = talker if talks(agent, settings, talker) else None
        self._chat, self._action_jobs, self._classifier = chat, action_jobs, classifier
        self._agent, self._settings, self._stt, self._tts = agent, settings, stt, tts
        self._phrases, self._tracing, self._emit, self._clock = phrases, tracing, emit, clock
        self._speech_detector, self._turn_analyzer = speech_detector, turn_analyzer
        self._calls: dict[CallId, WebRTCCall] = {}
        self._answering: set[CallId] = set()
        self._started = False

    async def start(self) -> None:
        """Import onnxruntime and warm one Silero VAD and one Smart Turn v3.2 (the `Calls`
        protocol's `start`)."""
        switch_pipecat_off()
        refused = sorted(foreign_set(REFUSED_VARIABLES))
        if refused:
            raise ConfigurationError(
                f"Pipecat reads {' and '.join(refused)}, which change what every call does "
                "(one runs the files it names in each pipeline, the other writes every turn's "
                "audio to disk). FIX: unset it in the server's environment.",
                details={"variables": list(refused)},
            )
        if not self._settings.logging.content:
            hold_transport_loggers()
        await asyncio.to_thread(self._detectors)
        self._started = True

    async def answer(
        self, call_id: CallId, offer: str, *, caller: Caller, consent: Consent, language: Language
    ) -> str:
        """Answer the call's SDP offer (the `Calls` protocol's `answer`)."""
        from t2_agentic_voice.voice.pipeline import WebRTCCall
        from t2_agentic_voice.voice.transport import WebRTCPeer, check_offer

        if not self._started:
            raise RuntimeError("An offer came before start(). FIX: start the calls first.")
        if call_id in self._calls or call_id in self._answering:
            raise InvalidRequestError("The call already has an answered offer.")
        check_offer(offer)
        self._answering.add(call_id)
        try:
            detectors = await asyncio.to_thread(self._detectors)
            peer = await WebRTCPeer.answer(offer, self._settings.server.ice_servers)
            try:
                transport = peer.transport()
                pipeline = self._pipeline(
                    call_id,
                    detectors,
                    caller=caller,
                    consent=consent,
                    language=language,
                    output=transport.output(),
                    input=transport.input(),
                    closing=peer.close,
                    on_finished=lambda: self._forget(call_id),
                )
                call = WebRTCCall(pipeline, peer)
                await call.start(transport, self._session(pipeline))
            except BaseException:
                await peer.close()
                raise
        finally:
            self._answering.discard(call_id)
        self._calls[call_id] = call
        return peer.answer_sdp

    async def add_candidates(self, call_id: CallId, candidates: Sequence[Candidate]) -> None:
        """Hand the call's peer its candidates (the `Calls` protocol's `add_candidates`)."""
        call = self._calls.get(call_id)
        if call is None or call.pipeline.ending:
            raise NotFoundError("No such call.")
        lines = [(c.candidate, c.sdp_mid, c.sdp_mline_index) for c in candidates]
        try:
            await call.peer.add_candidates(lines)
        except InvalidRequestError:
            raise
        except Exception as error:  # the peer closed meanwhile (Pipecat's 404) or failed
            log.info("candidates_not_taken", call_id=call_id, error=type(error).__name__)
            raise NotFoundError("No such call.") from None

    def phase(self, call_id: CallId) -> CallPhase | None:
        """Where the call stands (the `Calls` protocol's `phase`)."""
        call = self._calls.get(call_id)
        if call is None:
            return None
        if call.pipeline.ending:
            return "ended"
        return "connected" if call.pipeline.connected else "connecting"

    async def end(self, call_id: CallId) -> None:
        """End the call now (the `Calls` protocol's `end`)."""
        call = self._calls.get(call_id)
        if call is not None:
            call.pipeline.leave("server")
            await call.pipeline.finished.wait()

    async def aclose(self) -> None:
        """End every call, each close bounded (the `Calls` protocol's `aclose`)."""
        await asyncio.gather(*(self.end(call_id) for call_id in list(self._calls)))
        self._started = False

    def _detectors(self) -> tuple[VADAnalyzer, BaseTurnAnalyzer | None]:
        """A call's speech detector and turn analyzer (voice/turns.py's): off the event loop."""
        from t2_agentic_voice.voice.turns import detectors

        return detectors(self._settings.turns, self._speech_detector, self._turn_analyzer)

    def _pipeline(
        self,
        call_id: CallId,
        detectors: tuple[VADAnalyzer, BaseTurnAnalyzer | None],
        *,
        caller: Caller,
        consent: Consent,
        language: Language,
        output: BaseOutputTransport,
        input: FrameProcessor | None = None,
        closing: Callable[[], Awaitable[None]] | None = None,
        on_finished: Callable[[], None] = lambda: None,
        record: bool = False,
    ) -> CallPipeline:
        """One call's pipeline, with this runtime's agent, settings, providers and phrases (the
        file-fed transport builds its calls here too)."""
        from t2_agentic_voice.voice.pipeline import CallPipeline

        setup = CallSetup(
            call_id=call_id,
            caller=caller,
            consent=consent,
            agent=self._agent,
            language=language,
            settings=self._settings,
            phrases=self._phrases,
            max_chars=self._tts.max_chars,
            tracing=self._tracing,
            emit=self._emit,
            clock=self._clock,
            talker=talker_for(
                self._talker, call_id=call_id, caller=caller, language=language, clock=self._clock
            ),
            overlap_model=self._chat if self._talker is not None else None,
            action_jobs=self._action_jobs,
        )
        detector, analyzer = detectors
        return CallPipeline(
            setup=setup,
            stt=self._stt,
            tts=self._tts,
            detector=detector,
            analyzer=analyzer,
            output=output,
            input=input,
            closing=closing,
            on_finished=on_finished,
            record=record,
            classifier=self._classifier,
        )

    def _session(self, pipeline: CallPipeline) -> Session:
        """The call's session, given where its commands go."""
        return CallSession(pipeline.setup, pipeline.commands)

    def _forget(self, call_id: CallId) -> None:
        call = self._calls.pop(call_id, None)
        if call is not None:
            call.stop_deadline()

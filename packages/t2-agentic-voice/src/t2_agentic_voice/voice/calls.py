"""voice's entry point, which api calls: every call of one runtime, from its SDP offer to its end
(`VoiceCalls`, which meets entry.py's `Calls` protocol). The items cited are plan 003's appendix,
"Changes to the plan's interfaces".

- **Start and the detectors** (`start`): voice/calls_start.py says what is set, imported and
  warmed there, and how each call's speech detector and turn analyzer are made. This module
  imports no Pipecat at its top, since api imports it when the library is imported, and
  `import t2_agentic_voice` and `t2v --help` import no Pipecat (GP-17).
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
  server (the design's 11: the library contacts nothing beyond its outbound hosts). Each
  answered offer sends its warm requests under `warmup.at_join` (voice/join_warmth.py) and logs
  its server steps as times alone, never an address or a candidate (`call_answered`;
  `call_connected` in voice/pipeline.py).
- **Candidates** (`add_candidates`). Each one is checked before Pipecat sees it, since aiortc
  answers a malformed line with an AssertionError (item 10); an empty one marks their end, the
  client's end-of-candidates PATCH, which reaches aioice (item 11).
- **Messages.** The session bridge hands the session each client message as `on_app_message`
  gives it, the object Pipecat parsed (voice/protocol.py's object path), parsed with
  `parse_client_message`. Pipecat parsed the channel's text first, with no bound of ours (up to
  the transport's message size), and holds the messages that come before the call connects, so
  the bound is on the object written back as compact JSON: one whose compact JSON is over
  MAX_CLIENT_MESSAGE_BYTES is dropped.
- **The end** (`end`, `aclose`). Each peer's close is bounded by a timeout, since on Windows'
  proactor loop 2 or 3 of 16 closes hung (item 20). A call's session always hangs up, and voice
  ends the call's stream with the session's `aclose`, which returns once its report is written
  (voice/session/io.py's end), before it forgets the call. Voice forgets a call once it has
  ended and its peer has closed: `phase` says `ended` only until then, and None after, as for a
  call it never held.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from time import perf_counter
from typing import TYPE_CHECKING

from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.errors import InvalidRequestError, NotFoundError
from t2_agentic_voice.core.events import CallId
from t2_agentic_voice.core.identity import Caller, Consent
from t2_agentic_voice.core.logging import get_logger
from t2_agentic_voice.core.tracing import Tracing
from t2_agentic_voice.domain.declaration import Language, VoiceAgent
from t2_agentic_voice.domain.ports.action_jobs import ActionJobs
from t2_agentic_voice.domain.ports.chat_model import ChatModel
from t2_agentic_voice.domain.ports.language_classifier import LanguageClassifier
from t2_agentic_voice.domain.ports.speech_to_text import SpeechToText
from t2_agentic_voice.domain.ports.text_to_speech import TextToSpeech
from t2_agentic_voice.voice.calls_start import elapsed_ms, warm

# The contract api meets is entry.py's; these names are given here too, where api imports them.
from t2_agentic_voice.voice.entry import CallPhase as CallPhase
from t2_agentic_voice.voice.entry import Calls as Calls
from t2_agentic_voice.voice.entry import CallsFactory as CallsFactory
from t2_agentic_voice.voice.entry import Candidate as Candidate
from t2_agentic_voice.voice.entry import ChosenCall as ChosenCall
from t2_agentic_voice.voice.join_warmth import JoinWarmth
from t2_agentic_voice.voice.session.call import CallSession
from t2_agentic_voice.voice.session.io import (
    SYSTEM_CLOCK,
    CallSetup,
    Clock,
    EventSink,
    PhraseAudio,
    Session,
)
from t2_agentic_voice.voice.spare import Spare
from t2_agentic_voice.voice.talkers import TalkerFactory, talker_for, talks

if TYPE_CHECKING:  # named in annotations only: this module imports no Pipecat (above)
    from pipecat.audio.turn.base_turn_analyzer import BaseTurnAnalyzer
    from pipecat.audio.vad.vad_analyzer import VADAnalyzer
    from pipecat.processors.frame_processor import FrameProcessor
    from pipecat.transports.base_output import BaseOutputTransport

    from t2_agentic_voice.voice.pipeline import CallPipeline, WebRTCCall

log = get_logger(__name__)


class VoiceCalls:
    """Every call of one runtime over SmallWebRTC, each its own Pipecat pipeline and session, for
    `agent` with `settings`: speech-to-text through `stt`, text-to-speech through `tts`, the
    fixed phrases from `phrases`, its turns traced on `tracing`, its public events sent to
    `emit`, its times on `clock`. Each call's speech detector comes from `speech_detector` and
    its turn analyzer from `turn_analyzer`, each called once per call, off the event loop; None
    builds Silero VAD and Smart Turn v3.2, each loading its model for the call. A call of an
    agent that runs the talker gets its own, built by `talker` (voice/talkers.py), and `chat`,
    the chat model of the session's own requests, for an agent that asks: it decides an overlap
    the rule left uncertain (D-069), and judges an answer to a read-back that the yes rule's
    lists leave unplaced (D-082). `action_jobs` carries out each call's confirmed actions, one
    for every call, which it tells apart by the call's ID; with none, a call's confirmed yes is
    told as the `error` notice and nothing is sent. `classifier`, loaded by the runtime, hears
    each turn's language under `stt.live_language = "classified"`. `stt_model` names the model
    `stt` hears with in each call's usage (None: `stt.model`). `chosen` gives a call whose
    providers were chosen for it (the dev console's speech-to-text, an app's page's choice) its
    `ChosenCall` (entry.py), taken once, at its offer: each provider it names in place of the
    runtime's. Built cheaply, with no IO; `start` imports onnxruntime and warms one pair of
    models."""

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
        chosen: Callable[[CallId], ChosenCall | None] = lambda call_id: None,
        stt_model: str | None = None,
        speech_detector: Callable[[], VADAnalyzer] | None = None,
        turn_analyzer: Callable[[], BaseTurnAnalyzer] | None = None,
    ) -> None:
        self._talker = talker if talks(agent, settings, talker) else None
        self._chat, self._action_jobs, self._classifier = chat, action_jobs, classifier
        self._agent, self._settings, self._stt, self._tts = agent, settings, stt, tts
        self._phrases, self._tracing, self._emit, self._clock = phrases, tracing, emit, clock
        self._speech_detector, self._turn_analyzer = speech_detector, turn_analyzer
        self._chosen, self._stt_model = chosen, stt_model
        self._calls: dict[CallId, WebRTCCall] = {}
        self._answering: set[CallId] = set()
        # The next call's detectors, made ahead under `warmup.at_start` (voice/calls_start.py).
        self._spare = Spare(self._detectors, ahead=settings.warmup.at_start)
        self._warmth = JoinWarmth(on=settings.warmup.at_join, tts=tts, chat=self._chat)
        self._started = False

    async def start(self) -> None:
        """Import an offer's modules, and onnxruntime, and warm one Silero VAD and one Smart
        Turn v3.2, kept for the first call (the `Calls` protocol's `start`)."""
        await warm(self._settings, self._spare)
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
        began = perf_counter()
        try:
            detectors = await self._spare.take()
            took = perf_counter()
            stun = [u for u in self._settings.server.ice_servers if u.startswith("stun:")]
            peer = await WebRTCPeer.answer(offer, stun)  # the relay's are the browser's
            answered = perf_counter()
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
                call = WebRTCCall(pipeline, peer, began=began)
                await call.start(transport, self._session(pipeline))
                tts, chat = pipeline.tts, pipeline.setup.overlap_model
                self._warmth.joined(call_id, pipeline.stt, language.tag, tts=tts, chat=chat)
            except BaseException:
                await peer.close()
                raise
        finally:
            self._answering.discard(call_id)
        self._calls[call_id] = call
        steps = {"detectors_ms": elapsed_ms(began, took), "peer_ms": elapsed_ms(took, answered)}
        log.info("call_answered", call_id=call_id, **steps, pipeline_ms=elapsed_ms(answered))
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
        await self._spare.aclose()
        await self._warmth.aclose()
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
        """One call's pipeline, with this runtime's agent, settings, providers and phrases, or
        each one the call's `ChosenCall` names in their place (the file-fed transport's too)."""
        from t2_agentic_voice.voice.pipeline import CallPipeline

        chosen = self._chosen(call_id)
        settings = self._settings if chosen is None else chosen.settings
        tts = chosen.tts if chosen and chosen.tts else self._tts
        phrases = chosen.phrases if chosen and chosen.phrases else self._phrases
        factory = self._talker
        if factory is not None and chosen and chosen.talker:
            factory = chosen.talker
        chat = chosen.chat if chosen and chosen.chat else self._chat
        setup = CallSetup(
            call_id=call_id,
            caller=caller,
            consent=consent,
            agent=self._agent,
            language=language,
            settings=settings,
            phrases=phrases,
            max_chars=tts.max_chars,
            tracing=self._tracing,
            emit=self._emit,
            clock=self._clock,
            talker=talker_for(
                factory, call_id=call_id, caller=caller, language=language, clock=self._clock
            ),
            overlap_model=chat if self._talker is not None else None,
            action_jobs=self._action_jobs,
            stt_model=chosen.stt_model if chosen and chosen.stt_model else self._stt_model,
        )
        detector, analyzer = detectors
        return CallPipeline(
            setup=setup,
            stt=self._stt if chosen is None else chosen.stt,
            tts=tts,
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

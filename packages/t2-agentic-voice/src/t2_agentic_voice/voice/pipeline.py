"""One call's Pipecat pipeline, from its start to its end (the design's 13; plan 003's appendix,
"Changes to the plan's interfaces", items 1 to 3 and 7):

    input -> CallerTap -> VADProcessor -> UserTurnProcessor -> TurnSTTBridge -> SessionBridge
          -> ClauseTTSBridge -> ClauseGate -> output -> OutputTap

over SmallWebRTC for a call (transport.py), or fed from a clip with its output kept for a
file-fed one (file_transport.py), the input then being frames queued at the pipeline's head.
None of Pipecat's LLM services, context aggregators or function calls is used, and RTVI is off
(it lets the browser inject text and audio, and interrupt). Each call has a `PipelineWorker` and
a `WorkerRunner` of its own, built inside the running loop with no signal handling, and
Pipecat's idle cancel off (`limits.idle_s` is the library's, the session's to keep).

The call ends at the first of: the session's `HangUp`, an `Ending` (`leave`: the caller's side
closed, or voice was asked to end it) or a `TransportFailure` (`fail`). After an `Ending` or a
`TransportFailure` the session is given `HANGUP_WAIT_S` to hang up, so its `ended` message goes
out first; then the speech-to-text bridge drops what it holds, the pipeline is cancelled (its
queued audio dropped, a request in flight cancelled, never flushed), the peer is closed, each
step bounded, and the session's stream ends with its `aclose` (voice/session/io.py's end).
`finished` is set once all of it is done.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from pipecat.audio.turn.base_turn_analyzer import BaseTurnAnalyzer
from pipecat.audio.vad.vad_analyzer import VADAnalyzer
from pipecat.frames.frames import ErrorFrame, Frame, OutputTransportMessageUrgentFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.processors.frame_processor import FrameProcessor
from pipecat.transports.base_output import BaseOutputTransport
from pipecat.transports.smallwebrtc.transport import SmallWebRTCTransport
from pipecat.workers.runner import WorkerRunner

from t2_agentic_voice.core.errors import T2VoiceError
from t2_agentic_voice.core.events import EndReason, TransportStage
from t2_agentic_voice.core.logging import get_logger
from t2_agentic_voice.domain.ports.language_classifier import LanguageClassifier
from t2_agentic_voice.domain.ports.speech_to_text import SpeechToText
from t2_agentic_voice.domain.ports.text_to_speech import TextToSpeech
from t2_agentic_voice.voice.pipecat_events import FailureReport
from t2_agentic_voice.voice.session.io import CallSetup, Session
from t2_agentic_voice.voice.session.session_events import Connected, Ending, TransportFailure
from t2_agentic_voice.voice.session_bridge import EventStream, SessionBridge, SessionCommands
from t2_agentic_voice.voice.stt_bridge import TurnSTTBridge, call_prompts
from t2_agentic_voice.voice.stt_language import turn_languages
from t2_agentic_voice.voice.transport import (
    CLOSE_TIMEOUT_S,
    CONNECT_DEADLINE_S,
    IN_RATE,
    OUT_RATE,
    CallerTap,
    ClauseGate,
    OutputTap,
    WebRTCPeer,
)
from t2_agentic_voice.voice.tts_bridge import ClauseTTSBridge
from t2_agentic_voice.voice.turns import turn_processors

log = get_logger(__name__)

# How long a pipeline may take to start before the call is refused (the agent's bound; the
# spike's started in well under a second).
START_TIMEOUT_S = 10.0
# How long, after an `Ending` or a `TransportFailure`, the session is given to hang up before
# the call is torn down whatever it does (the agent's bound: it hangs up at once, io.py's end).
HANGUP_WAIT_S = 1.0


class CallPipeline:
    """One call's pipeline and its session's I/O, built from `setup`: speech-to-text through
    `stt`, text-to-speech through `tts`, `detector` hearing speech and `analyzer` ending turns
    (every pause, with none), between `input` (None: frames queued at the head) and `output`.
    `closing` closes the call's peer; `on_finished` is called once the call is done. With
    `record`, what the session was handed and gave is kept (`events.handed`,
    `commands.given`). `classifier` hears each turn's language under `stt.live_language =
    "classified"` (voice/stt_language.py)."""

    def __init__(
        self,
        *,
        setup: CallSetup,
        stt: SpeechToText,
        tts: TextToSpeech,
        detector: VADAnalyzer,
        analyzer: BaseTurnAnalyzer | None,
        output: BaseOutputTransport,
        input: FrameProcessor | None = None,
        closing: Callable[[], Awaitable[None]] | None = None,
        on_finished: Callable[[], None] = lambda: None,
        record: bool = False,
        classifier: LanguageClassifier | None = None,
    ) -> None:
        self.setup = setup
        self.report = FailureReport(call_id=setup.call_id, emit=setup.emit, clock=setup.clock)
        self.events = events = EventStream(setup.clock, record=record)
        self.stt_bridge = TurnSTTBridge(
            stt=stt,
            events=events,
            report=self.report,
            start_s=detector.params.start_secs,
            early=setup.talker is not None,  # the early start is the talker's (plan 006, Q2)
            prompts=call_prompts(setup.agent, setup.settings),  # once a call (plan 006, Q23)
            languages=turn_languages(setup.agent, setup.settings, classifier, setup.clock),
        )
        bridge = SessionBridge(events)
        timeout_s = setup.settings.tts.timeout_s
        self.tts_bridge = ClauseTTSBridge(
            tts=tts, events=events, report=self.report, timeout_s=timeout_s
        )
        self.commands = SessionCommands(
            bridge,
            events,
            listen=self.stt_bridge.listen_in,
            hear=self.stt_bridge.hear_overlap,
            send=self._send,
            hang_up=self._hung_up,
            record=record,
        )
        vad, user_turns = turn_processors(detector, analyzer, setup.settings.turns)
        processors: list[FrameProcessor] = [] if input is None else [input]
        processors += [CallerTap(events), vad, user_turns, self.stt_bridge, bridge]
        processors += [self.tts_bridge, ClauseGate(events), output]
        processors += [OutputTap(events, self.tts_bridge.played)]
        self.worker = PipelineWorker(
            Pipeline(processors),
            params=PipelineParams(audio_in_sample_rate=IN_RATE, audio_out_sample_rate=OUT_RATE),
            enable_rtvi=False,
            enable_turn_tracking=False,
            idle_timeout_secs=None,
            cancel_on_idle_timeout=False,
        )
        self.worker.add_event_handler("on_pipeline_started", self._on_started)
        self.worker.add_event_handler("on_pipeline_error", self._on_error)
        self._output = output
        self._closing = closing
        self._on_finished = on_finished
        self.connected = False
        self.ending = False
        self.finished = asyncio.Event()
        self._started = asyncio.Event()
        self._hung_up_now = asyncio.Event()
        self._run: asyncio.Task[None] | None = None
        self._teardown: asyncio.Task[None] | None = None

    async def start(self, session: Session) -> None:
        """Start the pipeline, then hand `session` the call's events. T2VoiceError when it does
        not start within `START_TIMEOUT_S`, the pipeline then cancelled."""
        runner = WorkerRunner(handle_sigint=False)
        await runner.add_workers(self.worker)
        self._run = asyncio.create_task(runner.run(), name="t2v-call-pipeline")
        started = asyncio.create_task(self._started.wait())
        await asyncio.wait(
            {started, self._run}, timeout=START_TIMEOUT_S, return_when=asyncio.FIRST_COMPLETED
        )
        if not started.done():
            started.cancel()
            await asyncio.gather(started, return_exceptions=True)
            await self._cancel_pipeline()
            raise T2VoiceError("The call could not start.")
        self.events.start(session)

    def connect(self) -> None:
        """The caller's peer connected: the session's `Connected`."""
        if not self.connected and not self.events.ended:
            self.connected = True
            self.events.hand(Connected(at=self.setup.clock.now()))

    def leave(self, reason: EndReason) -> None:
        """The call ends from outside the session, for `reason`: its `Ending`, then the end."""
        if not self.events.ended:
            self.events.hand(Ending(reason=reason, at=self.setup.clock.now()))
            self._end(wait=True)

    def fail(self, stage: TransportStage) -> None:
        """The call's connection failed at `stage`: its `TransportFailure`, then the end."""
        if not self.events.ended:
            self.report.transport_failed(stage)
            self.events.hand(TransportFailure(stage=stage, at=self.setup.clock.now()))
            self._end(wait=True)

    async def _send(self, message: object) -> None:
        await self._output.send_message(OutputTransportMessageUrgentFrame(message=message))

    def _hung_up(self, reason: EndReason) -> None:
        self._hung_up_now.set()
        self._end(wait=False)

    def _end(self, *, wait: bool) -> None:
        if self._teardown is None:
            self.ending = True
            self._teardown = asyncio.create_task(self._tear_down(wait), name="t2v-call-end")

    async def _tear_down(self, wait: bool) -> None:
        if wait:
            try:
                await asyncio.wait_for(self._hung_up_now.wait(), HANGUP_WAIT_S)
            except TimeoutError:
                log.warning("session_did_not_hang_up", call_id=self.setup.call_id)
        self.events.end()
        await self.stt_bridge.drop()
        await self._cancel_pipeline()
        if self._closing is not None:
            await self._closing()
        await self.events.close()
        self.finished.set()
        self._on_finished()

    async def _cancel_pipeline(self) -> None:
        await self.worker.cancel()
        if self._run is None:
            return
        try:
            await asyncio.wait_for(asyncio.shield(self._run), CLOSE_TIMEOUT_S)
        except TimeoutError:
            log.warning("pipeline_cancel_timeout", call_id=self.setup.call_id)
            self._run.cancel()
        except Exception as error:  # the runner's own failure: the call ends all the same
            log.error("pipeline_failed", call_id=self.setup.call_id, error=type(error).__name__)

    async def _on_started(self, worker: PipelineWorker, frame: Frame) -> None:
        self._started.set()

    async def _on_error(self, worker: PipelineWorker, frame: ErrorFrame) -> None:
        speech = [(self.stt_bridge, "speech_to_text"), (self.tts_bridge, "text_to_speech")]
        stage = self.report.error_frame(frame, speech=speech)
        if stage is not None:
            self.fail(stage)


class WebRTCCall:
    """One call over WebRTC: its pipeline over `peer`, and voice's own deadline from offer to
    connected (`CONNECT_DEADLINE_S`), after which a call not connected ends as a
    `TransportFailure` at `connect`."""

    def __init__(self, pipeline: CallPipeline, peer: WebRTCPeer) -> None:
        self.pipeline = pipeline
        self.peer = peer
        self._deadline: asyncio.Task[None] | None = None

    async def start(self, transport: SmallWebRTCTransport, session: Session) -> None:
        """Start the call's pipeline over `transport`, its peer's events wired to it: the
        transport's client connected is the session's `Connected`, ICE failing or the peer
        closing before that a `TransportFailure` at `connect`, and after it a failure at `media`
        or the caller leaving."""
        pipeline = self.pipeline

        async def connected(transport: object, connection: object) -> None:
            pipeline.connect()
            self.stop_deadline()

        async def failed() -> None:
            pipeline.fail("media" if pipeline.connected else "connect")

        async def closed() -> None:
            if pipeline.connected:
                pipeline.leave("caller_left")
            else:
                pipeline.fail("connect")

        transport.add_event_handler("on_client_connected", connected)
        self.peer.on_connection(failed, closed)
        await pipeline.start(session)
        self._deadline = asyncio.create_task(self._expire(), name="t2v-connect-deadline")

    def stop_deadline(self) -> None:
        """The call connected or ended: no deadline is left."""
        if self._deadline is not None:
            self._deadline.cancel()

    async def _expire(self) -> None:
        await asyncio.sleep(CONNECT_DEADLINE_S)
        if not self.pipeline.connected:
            log.info("call_connect_deadline", call_id=self.pipeline.setup.call_id)
            self.pipeline.fail("connect")

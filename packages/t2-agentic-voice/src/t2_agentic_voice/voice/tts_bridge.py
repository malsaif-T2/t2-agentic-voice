"""The text-to-speech bridge: Pipecat's TTS base class (`TTSService`) in
`TextAggregationMode.TOKEN`, speaking each clause the session asks for (`Speak`, carried as
session_bridge.py's `SpeakFrame`) through the `TextToSpeech` port, one request a clause (plan
003's appendix, "Changes to the plan's interfaces", item 9; voice/session/io.py's replies).

- A clause with text goes through the base class's own path, as a `TTSSpeakFrame`: TOKEN
  aggregation hands its text on at once, so `run_tts` runs once for it. Its text-to-speech
  context is named from the clause's key (session_bridge.py's `context_id`), and opened only
  when its first audio comes, so a request that fails or gives no audio opens none: Pipecat
  1.15.0 reports a context that ends with no audio as an error. `run_tts` sends the clause's
  text as the session gave it, handing `Synthesizing` as the request goes and `ClauseQueued`
  when its first audio is queued; a `ProviderError` is its `ClauseFailed`, from which the
  session emits the `ProviderFailed`, and the line `provider_failed`.
- A fixed phrase plays its cached audio in a context of its own, with no request; a clause
  whose audio is empty, or whose request gave none, sends no frame and opens no context: a
  `ClauseEndFrame` marks its place behind the audio queued before it.
- Every clause's last audio is followed by its context's `TTSStoppedFrame`, which the output
  transport passes on once that audio has left it: the output tap then asks `played` for the
  clause's `ClausePlayed` (transport.py), with the seconds and chunks that came, the headroom on
  the response's first chunk and whether the take came back cut short.
- The output transport is handed only whole chunks of its own (transport.py's
  `OUT_CHUNK_10MS`, 40 ms) at the pipeline's rate: a take's audio, a cached phrase's too, is
  resampled when its rate differs, cut into whole chunks, each remainder carried into the next
  and the last padded with silence (tts_output.py). Pipecat 1.15.0's output holds what falls
  short of a chunk, and its resampler's tail, until more comes, and discards both when a
  context's `TTSStoppedFrame` is played (`_bot_stopped_speaking`): the next clause's audio,
  still streaming when the clause before it ends, would lose up to a chunk from its middle.

Clauses play in the order they were asked for: each is spoken on the processor's own task, one
after another, and Pipecat plays the contexts in order. A clause a stop dropped, or one asked
for after the call's end, is never spoken; Pipecat's interruption, which the session bridge
broadcasts, cancels a request in flight and drops every context and queued frame.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

from pipecat.frames.frames import (
    Frame,
    InterruptionFrame,
    TTSAudioRawFrame,
    TTSSpeakFrame,
    TTSStartedFrame,
    TTSStoppedFrame,
)
from pipecat.processors.frame_processor import FrameDirection
from pipecat.services.settings import TTSSettings
from pipecat.services.tts_service import TextAggregationMode, TTSService

from t2_agentic_voice.core.errors import ProviderError, ProviderErrorKind
from t2_agentic_voice.core.logging import get_logger
from t2_agentic_voice.domain.ports.text_to_speech import AudioChunk, TextToSpeech
from t2_agentic_voice.voice.pipecat_events import FailureReport
from t2_agentic_voice.voice.session.commands import Speak
from t2_agentic_voice.voice.session.session_events import (
    ClauseFailed,
    ClausePlayed,
    ClauseQueued,
    Synthesizing,
)
from t2_agentic_voice.voice.session_bridge import (
    CallEvents,
    ClauseEndFrame,
    ClauseKey,
    SpeakFrame,
)
from t2_agentic_voice.voice.session_bridge import context_id as clause_context
from t2_agentic_voice.voice.tts_output import ClauseTake, OutputChunks

log = get_logger(__name__)


class ClauseTTSBridge(TTSService):
    """One call's text-to-speech bridge: each clause through `tts`, its events to `events`, its
    failures to `report`; a context with no audio for `timeout_s` (the settings' longest
    request) is ended, as Pipecat ends one gone quiet."""

    def __init__(
        self, *, tts: TextToSpeech, events: CallEvents, report: FailureReport, timeout_s: float
    ) -> None:
        super().__init__(
            text_aggregation_mode=TextAggregationMode.TOKEN,
            push_start_frame=False,
            push_stop_frames=True,
            stop_frame_timeout_s=timeout_s,
            max_consecutive_zero_audio_contexts=0,
            settings=TTSSettings(model=None, voice=None, language=None),
            name="t2v-tts-bridge",
        )
        self._tts = tts
        self._events = events
        self._report = report
        self._clauses: dict[ClauseKey, ClauseTake] = {}
        self._speaking: tuple[ClauseKey, Speak] | None = None

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        if isinstance(frame, SpeakFrame) and direction == FrameDirection.DOWNSTREAM:
            await self._speak(frame.speak)
            return
        await super().process_frame(frame, direction)
        if isinstance(frame, InterruptionFrame):  # a stop: forget what it dropped
            for key in [k for k in self._clauses if k in self._events.dropped]:
                del self._clauses[key]

    def create_context_id(self) -> str:
        """The context of the clause being spoken, named from its key."""
        if self._speaking is not None:
            return clause_context(self._speaking[0])
        return super().create_context_id()

    async def run_tts(self, text: str, context_id: str) -> AsyncGenerator[Frame | None, None]:
        """The clause being spoken, through the port: its text as the session gave it (the
        base passes it with leading spaces trimmed), its audio as frames of its context, in
        whole output chunks, the context opened when its first chunk is whole."""
        if self._speaking is None:  # only a clause is ever spoken here
            return
        key, speak = self._speaking
        clause = self._clauses[key]
        clock = self._events.clock
        clause.requested_at = clock.now()
        self._events.hand(Synthesizing(reply_id=key[0], clause=key[1], at=clause.requested_at))
        chunks = OutputChunks(self.sample_rate)
        try:
            async for chunk in self._tts.synthesize(speak.text, language=speak.language):
                clause.took(chunk)
                for frame in await self._audio(key, clause, context_id, await chunks.whole(chunk)):
                    yield frame
            for frame in await self._audio(key, clause, context_id, await chunks.rest()):
                yield frame
        except ProviderError as error:
            self._failed(key, clause, error.kind, error.retryable)
        except Exception as error:  # an adapter's bug: the clause still fails, as it must
            log.error("tts_request_failed", reply_id=key[0], error=type(error).__name__)
            self._failed(key, clause, "server_error", False)

    async def _audio(
        self, key: ClauseKey, clause: ClauseTake, context_id: str, audio: bytes
    ) -> list[Frame]:
        """The frames of a take's whole chunks `audio`: none for none, its context's
        `TTSStartedFrame` before its first, the context opened and `ClauseQueued` handed."""
        if not audio:
            return []
        frames: list[Frame] = []
        if not clause.queued:
            await self.create_audio_context(context_id)
            frames.append(TTSStartedFrame(context_id=context_id))
            self._queued(key, clause)
        frames.append(TTSAudioRawFrame(audio, self.sample_rate, 1, context_id=context_id))
        return frames

    def played(self, key: ClauseKey) -> None:
        """The clause's last audio has left the output transport, or its place in the output
        has come when it had none: its `ClausePlayed` (its `ClauseQueued` first when no audio
        came), unless it failed, a stop dropped it or it was already reported."""
        clause = self._clauses.pop(key, None)
        if clause is None or clause.failed:
            return
        if not clause.queued:
            self._queued(key, clause)
        played = ClausePlayed(
            reply_id=key[0],
            clause=key[1],
            at=self._events.clock.now(),
            audio_s=clause.audio_s,
            chunks=clause.chunks,
            remaining_requests=clause.remaining_requests,
            remaining_tokens=clause.remaining_tokens,
            cut_short=clause.cut_short,
        )
        self._events.hand(played)

    async def _speak(self, speak: Speak) -> None:
        key = (speak.reply_id, speak.clause)
        if self._events.ended or key in self._events.dropped:
            return
        clause = self._clauses[key] = ClauseTake(turn_id=speak.turn_id)
        if speak.audio is not None:
            await self._play(key, clause, speak.audio)
        elif not speak.text.strip():
            await self._mark(key)
        elif not self.is_usable:
            self._failed(key, clause, "server_error", False)
        else:
            self._speaking = key, speak
            try:
                await super().process_frame(
                    TTSSpeakFrame(text=speak.text, append_to_context=False),
                    FrameDirection.DOWNSTREAM,
                )
            finally:
                self._speaking = None
            if not clause.queued and not clause.failed:  # the request gave no audio
                await self._mark(key)

    async def _play(self, key: ClauseKey, clause: ClauseTake, audio: AudioChunk) -> None:
        """A fixed phrase's cached audio, in a context of its own, with no request, in whole
        output chunks."""
        if not audio.pcm16:
            await self._mark(key)
            return
        chunks = OutputChunks(self.sample_rate)
        pcm16 = await chunks.whole(audio) + await chunks.rest()
        context = clause_context(key)
        await self.create_audio_context(context)
        await self.append_to_audio_context(context, TTSStartedFrame(context_id=context))
        clause.took(audio)
        self._queued(key, clause)
        frame = TTSAudioRawFrame(pcm16, self.sample_rate, 1, context_id=context)
        await self.append_to_audio_context(context, frame)
        await self.append_to_audio_context(context, TTSStoppedFrame(context_id=context))
        await self.remove_audio_context(context)

    async def _mark(self, key: ClauseKey) -> None:
        """A clause with no audio: its place in the output, behind the audio queued before it."""
        await super().process_frame(ClauseEndFrame(key=key), FrameDirection.DOWNSTREAM)

    def _queued(self, key: ClauseKey, clause: ClauseTake) -> None:
        clause.queued = True
        now = self._events.clock.now()
        queued = ClauseQueued(
            reply_id=key[0], clause=key[1], at=now, requested_at=clause.requested_at
        )
        self._events.hand(queued)

    def _failed(
        self, key: ClauseKey, clause: ClauseTake, kind: ProviderErrorKind, retryable: bool
    ) -> None:
        """The clause's request failed: no more of it plays, and no `ClausePlayed` follows."""
        clause.failed = True
        if not clause.queued:  # no context opened, so no stop frame will come for it
            self._clauses.pop(key, None)
        self._report.provider_failed("text_to_speech", kind, retryable, turn_id=clause.turn_id)
        failed = ClauseFailed(
            reply_id=key[0],
            clause=key[1],
            at=self._events.clock.now(),
            failure=kind,
            retryable=retryable,
        )
        self._events.hand(failed)

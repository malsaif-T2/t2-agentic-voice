"""The requests of a call heard over its stream (plan 010's 5.1): `StreamedRequests`, the bridge's
`SttRequests` (voice/stt_requests.py) whose streamed turns' `held` and `turn` requests are
answered by the call's stream (voice/stt_stream.py's `CallStream`) instead of a request.

Each such request hands its `Transcribing` as it commits the stream, naming the language its
words are in, and its one `Transcribed`: the words of every commit the turn made, joined, so
its time runs from the commit to the stream's answer. When the stream fails it, or leaves it
unanswered, the turn's audio goes as a request after all, as it would have gone, its time
counted from the commit. Every other request (an overlap's parts, a turn heard by request) is
`SttRequests`' own, and `call_requests` gives `SttRequests` itself to a call with no stream.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping

from pipecat.services.stt_service import STTService

from t2_agentic_voice.domain.ports.speech_to_text import AudioClip, SpeechToText
from t2_agentic_voice.voice.pipecat_events import FailureReport
from t2_agentic_voice.voice.session.session_events import Transcribed, TranscriptPart
from t2_agentic_voice.voice.session_bridge import EventStream
from t2_agentic_voice.voice.stt_language import TurnLanguages
from t2_agentic_voice.voice.stt_requests import SttRequests, SwitchRule
from t2_agentic_voice.voice.stt_stream import CallStream, Commits, StreamHooks, call_stream


def call_requests(
    processor: STTService,
    *,
    stt: SpeechToText,
    events: EventStream,
    report: FailureReport,
    prompts: Mapping[str, str],
    languages: TurnLanguages,
    detect: SwitchRule | None,
    streaming: bool,
    preroll_s: float,
) -> tuple[StreamHooks, SttRequests]:
    """The bridge `processor`'s stream and requests, each with the arguments `SttRequests`
    takes: with `streaming`, no switch rule (`detect`) and no classifier, a provider that streams
    gives a `CallStream`, fed each turn from the bridge's pre-roll (`preroll_s`), and
    `StreamedRequests` on it; any other call has hooks that do nothing and `SttRequests`."""
    on = streaming and detect is None and not languages.classifies
    stream = call_stream(processor, stt, prompts, events.clock, on=on, preroll_s=preroll_s)
    if isinstance(stream, CallStream):
        streamed = StreamedRequests(
            processor,
            stream=stream,
            stt=stt,
            events=events,
            report=report,
            prompts=prompts,
            languages=languages,
        )
        return stream, streamed
    requests = SttRequests(
        processor,
        stt=stt,
        events=events,
        report=report,
        prompts=prompts,
        languages=languages,
        detect=detect,
    )
    return stream, requests


class StreamedRequests(SttRequests):
    """`SttRequests` of a call with no switch rule, whose streamed turns' `held` and `turn`
    requests `stream` answers (the module's docstring)."""

    def __init__(
        self,
        processor: STTService,
        *,
        stream: CallStream,
        stt: SpeechToText,
        events: EventStream,
        report: FailureReport,
        prompts: Mapping[str, str],
        languages: TurnLanguages,
    ) -> None:
        super().__init__(
            processor,
            stt=stt,
            events=events,
            report=report,
            prompts=prompts,
            languages=languages,
        )
        self._stream = stream

    def send(
        self,
        turn_id: int,
        audio: bytes,
        part: TranscriptPart,
        *,
        voiced_s: float | None = None,
        hand: bool = True,
    ) -> asyncio.Task[Transcribed]:
        """A streamed turn's `held` or `turn` request as a commit of the stream; any other as
        `SttRequests.send` sends it."""
        own = part in ("held", "turn") and bool(audio) and self._processor.is_usable
        commits = self._stream.commit(turn_id) if own else None
        if commits is None:
            return super().send(turn_id, audio, part, voiced_s=voiced_s, hand=hand)
        return self._track(self._streamed(turn_id, audio, part, commits, hand=hand))

    async def _streamed(
        self, turn_id: int, audio: bytes, part: TranscriptPart, commits: Commits, *, hand: bool
    ) -> Transcribed:
        """The streamed request's `Transcribing` as it commits, then its one `Transcribed`,
        handed (unless `hand` is off) and returned; by request when the stream fails it."""
        clock = self._events.clock
        sent_at, named = clock.now(), self._languages.named(turn_id, part)
        clip = AudioClip(pcm16=audio, sample_rate=self._processor.sample_rate)
        self._events.hand(named.transcribing(turn_id, at=sent_at, audio_s=clip.seconds, part=part))
        transcript = await self._stream.joined(commits, named.language)
        failure, retryable = None, False
        if transcript is None:  # the stream failed it: the turn's audio as a request after all
            prompt = None if named.language is None else self._prompts.get(named.language)
            transcript, failure, retryable = await self._ask(turn_id, clip, named.language, prompt)
        if failure is not None:
            self._report.provider_failed("speech_to_text", failure, retryable, turn_id=turn_id)
        heard = Transcribed(
            turn_id=turn_id,
            at=clock.now(),
            audio_s=clip.seconds,
            sent_at=sent_at,
            transcript=transcript,
            failure=failure,
            retryable=retryable,
            part=part,
        )
        if hand:
            self._events.hand(heard)
        return heard

    async def drop(self) -> None:
        """The call has ended: every request in flight cancelled, then the stream closed."""
        await super().drop()
        await self._stream.drop()

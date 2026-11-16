"""The requests of one call's speech-to-text bridge (voice/stt_bridge.py): `SttRequests`, which
sends the `SpeechToText` port each request the bridge asks for, on a task of its own, and hands
its `Transcribing` as it goes and its one `Transcribed`, an empty, failed or unusable result
included.

Every request, each part's, names the language `languages` gives it as it goes (voice/
stt_language.py's `TurnLanguages`: the one last named, `listen_in`, unless a classifier chose
another for the turn), its `Transcribing` carrying it, and carries that language's Whisper
prompt: the call's `prompts`, built once a call by `call_prompts`, the prompt run W's arm W1
measured and kept (plan 006, Q23). A request that names no language, or one whose prompt holds no
word, carries none, as W1 sent none; with `stt.send_prompt` off, none carries one.

`drop` cancels every request in flight at the call's end, its `Transcribing` already handed.
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine, Mapping
from dataclasses import replace
from typing import Any

from pipecat.services.stt_service import STTService

from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.errors import ProviderError, ProviderErrorKind
from t2_agentic_voice.core.logging import get_logger
from t2_agentic_voice.domain.declaration import VoiceAgent
from t2_agentic_voice.domain.ports.speech_to_text import AudioClip, SpeechToText, Transcript
from t2_agentic_voice.domain.whisper_prompt import COMMAND_SPELLINGS, whisper_prompt
from t2_agentic_voice.voice.pipecat_events import FailureReport
from t2_agentic_voice.voice.session.session_events import Transcribed, TranscriptPart
from t2_agentic_voice.voice.session_bridge import EventStream
from t2_agentic_voice.voice.stt_language import TurnLanguages

log = get_logger(__name__)


def call_prompts(agent: VoiceAgent, settings: VoiceSettings) -> dict[str, str]:
    """The Whisper prompt of each language a call of `agent` may name, by its primary code:
    `whisper_prompt` of the declaration's vocabulary, the `words.vocabulary` setting's terms
    after it, as run W's arm W1 built it (its `--prompt-agent`); none with `stt.send_prompt`
    off, and none for a language whose prompt holds no word."""
    if not settings.stt.send_prompt:
        return {}
    terms = (*agent.vocabulary.terms, *settings.words.vocabulary)
    prompts = {code: whisper_prompt(terms, code).text for code in COMMAND_SPELLINGS}
    return {code: text for code, text in prompts.items() if text}


class SttRequests:
    """The requests of the bridge `processor` (its tasks, its sample rate, whether it is
    usable): each to `stt`, its events to `events`, its failures to `report`, each naming the
    language `languages` gives it with that language's prompt of `prompts` (the module's)."""

    def __init__(
        self,
        processor: STTService,
        *,
        stt: SpeechToText,
        events: EventStream,
        report: FailureReport,
        prompts: Mapping[str, str],
        languages: TurnLanguages,
    ) -> None:
        self._processor = processor
        self._stt = stt
        self._events = events
        self._report = report
        self._prompts = dict(prompts)
        self._languages = languages
        self._requests: set[asyncio.Task[Transcribed]] = set()

    def send(self, turn_id: int, audio: bytes, part: TranscriptPart) -> asyncio.Task[Transcribed]:
        """One request of the turn's `part`, on a task of its own (`transcribe`)."""
        return self._track(self.transcribe(turn_id, audio, part))

    def reuse(
        self, source: asyncio.Task[Transcribed], part: TranscriptPart
    ) -> asyncio.Task[Transcribed]:
        """`source`'s result again, once it came, as the turn's `part`, with no request, on a
        task of its own."""
        return self._track(self._reused(source, part))

    def _track(self, work: Coroutine[Any, Any, Transcribed]) -> asyncio.Task[Transcribed]:
        """Run `work` on a task of its own, cancelled at the call's end."""
        request: asyncio.Task[Transcribed] = self._processor.create_task(
            work, name="t2v-stt-request"
        )
        self._requests.add(request)
        request.add_done_callback(self._requests.discard)
        return request

    async def transcribe(self, turn_id: int, audio: bytes, part: TranscriptPart) -> Transcribed:
        """One request of the turn's `part`, its `Transcribing` handed as it goes, and its one
        `Transcribed`, handed and returned; none goes for no audio or an unusable bridge."""
        events, clock = self._events, self._events.clock
        heard = Transcribed(
            turn_id=turn_id, at=0.0, audio_s=0.0, sent_at=None, transcript=None, part=part
        )
        if not audio or not self._processor.is_usable:
            heard = replace(heard, at=clock.now())
            events.hand(heard)
            return heard
        clip = AudioClip(pcm16=audio, sample_rate=self._processor.sample_rate)
        sent_at, named = clock.now(), self._languages.named(turn_id, part)
        events.hand(named.transcribing(turn_id, at=sent_at, audio_s=clip.seconds, part=part))
        transcript: Transcript | None = None
        failure: ProviderErrorKind | None = None
        retryable, language = False, named.language
        prompt = None if language is None else self._prompts.get(language)
        try:
            transcript = await self._stt.transcribe(clip, language=language, prompt=prompt)
        except ProviderError as error:
            failure, retryable = error.kind, error.retryable
        except Exception as error:  # an adapter's bug: still exactly one result for the part
            log.error("stt_request_failed", turn_id=turn_id, error=type(error).__name__)
            failure = "server_error"
        if failure is not None:
            self._report.provider_failed("speech_to_text", failure, retryable, turn_id=turn_id)
        heard = replace(
            heard,
            at=clock.now(),
            audio_s=clip.seconds,
            sent_at=sent_at,
            transcript=transcript,
            failure=failure,
            retryable=retryable,
        )
        events.hand(heard)
        return heard

    async def _reused(self, source: asyncio.Task[Transcribed], part: TranscriptPart) -> Transcribed:
        heard = replace(await asyncio.shield(source), part=part, at=self._events.clock.now())
        self._events.hand(heard)
        return heard

    async def drop(self) -> None:
        """The call has ended: every request in flight cancelled."""
        for request in list(self._requests):
            await self._processor.cancel_task(request)

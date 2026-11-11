"""One call's usage of each provider model (the design's 10.4), counted from each request's report
as it goes (voice/session/io.py's usage): a `Transcribing` is one speech-to-text request, its
audio sent and billed as Groq bills Whisper, at least `WHISPER_MIN_BILLED_S` a request; a
`Synthesizing` is one text-to-speech request, its clause's text the characters sent; a phrase
or a held clause played from a cache is a cache hit, which sends nothing; a chat model's request
is counted as the talker reports it going (`ModelRequested`), and its tokens as its provider
reported them when it ended (`ModelReplied`). A request the call's end cancelled is counted,
since it went; the last headroom the provider reported for its key is kept per model.
"""

from __future__ import annotations

from dataclasses import dataclass

from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.events import ModelUsage
from t2_agentic_voice.core.settings.tts import LanguageTag
from t2_agentic_voice.domain.ports.chat_model import Usage as ChatUsage
from t2_agentic_voice.voice.session.session_events import ClausePlayed, Transcribed, Transcribing

# The least Groq bills a transcription request, in seconds (the design's 10.4, checked).
WHISPER_MIN_BILLED_S = 10.0


@dataclass(kw_only=True)
class _Counts:
    """One model's counts so far."""

    requests: int = 0
    audio_sent_s: float = 0.0
    billed_s: float = 0.0
    characters: int = 0
    cache_hits: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0
    remaining_requests: int | None = None
    remaining_tokens: int | None = None

    def headroom(self, requests: int | None, tokens: int | None) -> None:
        """Keep the headroom a response reported, each value only when it carried one."""
        if requests is not None:
            self.remaining_requests = requests
        if tokens is not None:
            self.remaining_tokens = tokens


class Usage:
    """Each model's usage in one call: the speech-to-text model, each language's
    text-to-speech model as `tts.languages` gives it, and each chat model the talker asked; the
    call's own language's is reported even when it sent nothing."""

    def __init__(self, settings: VoiceSettings, language: LanguageTag) -> None:
        self._stt_model = settings.stt.model
        self._tts_models = {tag: voice.model for tag, voice in settings.tts.languages.items()}
        self._models: dict[str, _Counts] = {self._stt_model: _Counts()}
        self._tts(language)

    def _tts(self, language: LanguageTag) -> _Counts:
        return self._models.setdefault(self._tts_models[language], _Counts())

    def model(self, language: LanguageTag) -> str:
        """The text-to-speech model `language` is spoken in."""
        return self._tts_models[language]

    def transcribing(self, event: Transcribing) -> None:
        """One speech-to-text request went, with `event.audio_s` of audio."""
        counts = self._models[self._stt_model]
        counts.requests += 1
        counts.audio_sent_s += event.audio_s
        counts.billed_s += max(WHISPER_MIN_BILLED_S, event.audio_s)

    def transcribed(self, event: Transcribed) -> None:
        """The headroom the transcript's response reported."""
        if event.transcript is not None:
            transcript = event.transcript
            counts = self._models[self._stt_model]
            counts.headroom(transcript.remaining_requests, transcript.remaining_tokens)

    def synthesizing(self, language: LanguageTag, characters: int) -> None:
        """One text-to-speech request of `language` went, sending `characters`."""
        counts = self._tts(language)
        counts.requests += 1
        counts.characters += characters

    def cached(self, language: LanguageTag) -> None:
        """A phrase, or a clause the clause cache held, of `language` was played from a cache."""
        self._tts(language).cache_hits += 1

    def played(self, language: LanguageTag, event: ClausePlayed) -> None:
        """The headroom a clause's response reported."""
        self._tts(language).headroom(event.remaining_requests, event.remaining_tokens)

    def chat_requested(self, model: str) -> None:
        """One request to the chat model `model` went."""
        self._models.setdefault(model, _Counts()).requests += 1

    def chat_replied(self, model: str, usage: ChatUsage | None) -> None:
        """A request to the chat model `model` ended, using `usage` (None: not reported)."""
        counts = self._models.setdefault(model, _Counts())
        if usage is not None:
            counts.input_tokens += usage.input_tokens
            counts.output_tokens += usage.output_tokens
            counts.cached_tokens += usage.cached_tokens

    def report(self) -> tuple[ModelUsage, ...]:
        """Each model's usage, the speech-to-text model's first."""
        return tuple(
            ModelUsage(
                model=model,
                requests=counts.requests,
                audio_sent_s=counts.audio_sent_s,
                billed_s=counts.billed_s,
                characters=counts.characters,
                cache_hits=counts.cache_hits,
                input_tokens=counts.input_tokens,
                output_tokens=counts.output_tokens,
                cached_tokens=counts.cached_tokens,
                remaining_requests=counts.remaining_requests,
                remaining_tokens=counts.remaining_tokens,
            )
            for model, counts in self._models.items()
        )

"""What a call's traces carry beside the turn and its speech-to-text span (core/tracing.py): the
text-to-speech span of one reply, the attributes the design's 10.1 gives a trace's resource with
the digest of the settings that leaves out every secret, and `CallTrace`, which holds one call's
spans for the session, so `voice` never names an OpenTelemetry type (ARCH-OWNER; plan 003, Track
D).

The resource attributes go on each trace's root span (a turn's, and the call's own), not on a
provider's `Resource`: a team's provider keeps its own, and the agent and the consent version are
the call's, not the process's. The digest is a SHA-256 of the settings written as JSON with every
secret left out, and the `_file` setting that names the file holding it, so the digest is the same
whichever key or file is given and says nothing of either. Under `tracing.include_transcripts`
a turn's root span holds what was heard and what its reply said, a reply's span its text, and a
tool call's span the arguments the model wrote and what the tool gave back (D-079), each through
the redaction hook.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator, Mapping
from contextlib import AbstractContextManager, ExitStack, contextmanager
from dataclasses import dataclass
from functools import cache
from importlib.metadata import version
from typing import Any, get_args

from openinference.semconv.trace import (
    OpenInferenceMimeTypeValues,
    OpenInferenceSpanKindValues,
    SpanAttributes,
)
from opentelemetry.trace import Span, StatusCode, set_span_in_context
from opentelemetry.util.types import AnyValue
from pydantic import BaseModel, SecretStr

from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.tracing import SpeechToTextSpan, Tracing
from t2_agentic_voice.core.tracing_export import VERSION

# A span's attributes as a caller outside core gives them: names to texts and numbers.
Attributes = Mapping[str, str | bool | int | float]
# The resource attributes' names (the design's 10.1): the library's version and Pipecat's, the
# settings' digest, the agent (its fingerprint and version come with the talker), the models a
# call speaks with, and the consent version its caller agreed to.
LIBRARY_VERSION = "t2v.version"
PIPECAT_VERSION = "t2v.pipecat.version"
SETTINGS_DIGEST = "t2v.settings.digest"
AGENT_NAME = "t2v.agent.name"
MODELS = "t2v.models"
CONSENT_VERSION = "t2v.consent.version"
# A text-to-speech span's own attributes (the design's 10.1).
TTS_CHARACTERS = "tts.characters"
TTS_CHUNKS = "tts.chunks"
TTS_REQUESTS = "tts.requests"
TTS_FIRST_AUDIO_MS = "tts.first_audio_ms"
TTS_CACHE_HITS = "tts.cache_hits"
TTS_CUT_SHORT = "tts.cut_short"
TTS_VOICE = "tts.voice"
TTS_LANGUAGE = "tts.language"
# Pipecat's distribution, read from its metadata: core never imports Pipecat (ARCH-OWNER).
_PIPECAT = "pipecat-ai"


def settings_digest(settings: VoiceSettings) -> str:
    """The SHA-256, in hex, of `settings` written as JSON with sorted keys, every secret of each
    group left out, and its `_file` setting with it: changing a key, a secret or the file that
    holds one leaves it the same, while any other setting changes it."""
    dumped = settings.model_dump(mode="json", exclude=_secrets(settings))
    text = json.dumps(dumped, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(text.encode()).hexdigest()


def _secrets(settings: VoiceSettings) -> dict[str, set[str]]:
    """Each group's secret settings, by group: every field whose type holds a `SecretStr`, and
    the `_file` field beside it."""
    found: dict[str, set[str]] = {}
    for name in type(settings).model_fields:
        group = getattr(settings, name)
        if not isinstance(group, BaseModel):
            continue
        fields = type(group).model_fields
        secret = {field for field, info in fields.items() if _holds_secret(info.annotation)}
        secret |= {f"{field}_file" for field in secret if f"{field}_file" in fields}
        if secret:
            found[name] = secret
    return found


def _holds_secret(annotation: Any) -> bool:
    """Whether the type `annotation` is a `SecretStr` or holds one (an optional one, a map)."""
    return annotation is SecretStr or any(_holds_secret(arg) for arg in get_args(annotation))


@cache
def _pipecat_version() -> str:
    """Pipecat's version, read once a process from its installed metadata."""
    return version(_PIPECAT)


def resource_attributes(
    settings: VoiceSettings, *, agent: str, models: tuple[str, ...], consent_version: str | None
) -> dict[str, AnyValue]:
    """The design's 10.1 resource attributes for one call's traces: the library's and Pipecat's
    versions, the settings' digest (no secret), the agent's name, the `models` the call speaks
    with, and the consent version its caller agreed to (left out when none)."""
    attributes: dict[str, AnyValue] = {
        LIBRARY_VERSION: VERSION,
        PIPECAT_VERSION: _pipecat_version(),
        SETTINGS_DIGEST: settings_digest(settings),
        AGENT_NAME: agent,
        MODELS: list(models),
    }
    if consent_version is not None:
        attributes[CONSENT_VERSION] = consent_version
    return attributes


@dataclass(frozen=True, kw_only=True)
class ReplyNumbers:
    """What one reply took, as its text-to-speech span records it: the characters sent in its
    requests, the audio chunks played, the requests sent, the phrases and held clauses played
    from the caches, how long its first request took to its first audio (none when no request's
    audio came), and whether a take came back cut short. No text: what it says is the call's."""

    characters: int
    chunks: int
    requests: int
    cache_hits: int
    first_audio_ms: float | None
    cut_short: bool


class TextToSpeechSpan:
    """One reply's text-to-speech span, open while the reply plays."""

    def __init__(self, span: Span) -> None:
        self._span = span

    def record(self, numbers: ReplyNumbers, *, text: str = "") -> None:
        """What the reply took (`ReplyNumbers`) and, when given, what it was to say."""
        _words(self._span, SpanAttributes.INPUT_VALUE, SpanAttributes.INPUT_MIME_TYPE, text)
        attributes: dict[str, AnyValue] = {
            TTS_CHARACTERS: numbers.characters,
            TTS_CHUNKS: numbers.chunks,
            TTS_REQUESTS: numbers.requests,
            TTS_CACHE_HITS: numbers.cache_hits,
            TTS_CUT_SHORT: numbers.cut_short,
        }
        if numbers.first_audio_ms is not None:
            attributes[TTS_FIRST_AUDIO_MS] = numbers.first_audio_ms
        self._span.set_attributes(attributes)


def text_to_speech(
    tracing: Tracing, parent: Span, *, model: str, voice: str, language: str
) -> AbstractContextManager[TextToSpeechSpan]:
    """A text-to-speech span under `parent` (a turn's span, or the call's for a reply that
    answers no turn), with the model, the voice and the language; its `record` adds what the
    reply took. Built on core/tracing.py's own span helper, so the redaction hook runs on every
    text and nothing but text and numbers is exported."""
    attributes: dict[str, AnyValue] = {
        SpanAttributes.OPENINFERENCE_SPAN_KIND: OpenInferenceSpanKindValues.LLM.value,
        SpanAttributes.LLM_MODEL_NAME: model,
        TTS_VOICE: voice,
        TTS_LANGUAGE: language,
    }
    return _tts(tracing, parent, attributes)


@contextmanager
def _tts(
    tracing: Tracing, parent: Span, attributes: dict[str, AnyValue]
) -> Iterator[TextToSpeechSpan]:
    # The span helper of core/tracing.py, which this module extends (its text-to-speech half,
    # kept apart under the module size cap): the same package's, so its redaction applies.
    with tracing._span("text_to_speech", set_span_in_context(parent), attributes) as span:
        yield TextToSpeechSpan(span)


def _words(span: Span, value: str, mime_type: str, text: str) -> None:
    """`text`, when there is any, as the span's `value`, plain text."""
    if text:
        span.set_attribute(value, text)
        span.set_attribute(mime_type, OpenInferenceMimeTypeValues.TEXT.value)


class CallTrace:
    """One call's spans, each opened and ended as the call goes (the design's 10.1): the call's
    own root span, a root span per turn (one trace per turn), each with `session.id` set to the
    call's ID and the resource attributes; a turn's speech-to-text span; and each reply's
    text-to-speech span, under its turn's, or under the call's for a reply that answers no turn.
    `close` ends every span still open, the call's last."""

    def __init__(self, tracing: Tracing, *, call_id: str, resource: Mapping[str, AnyValue]) -> None:
        self._tracing = tracing
        self._call_id = call_id
        self._resource = dict(resource)
        self._call: tuple[ExitStack, Span] | None = None
        self._turns: dict[int, tuple[ExitStack, Span]] = {}
        self._stt: dict[int, tuple[ExitStack, SpeechToTextSpan]] = {}
        self._tts: dict[int, tuple[ExitStack, TextToSpeechSpan]] = {}
        self._tools: dict[str, tuple[int, ExitStack, Span]] = {}

    def _root(self, name: str) -> tuple[ExitStack, Span]:
        stack = ExitStack()
        span = stack.enter_context(self._tracing.turn(session_id=self._call_id, name=name))
        span.set_attributes(self._resource)
        return stack, span

    def _call_span(self) -> tuple[ExitStack, Span]:
        if self._call is None:
            self._call = self._root("call")
        return self._call

    def _turn_span(self, turn_id: int) -> Span:
        if turn_id not in self._turns:
            self._turns[turn_id] = self._root("turn")
            self._turns[turn_id][1].set_attribute("turn.id", turn_id)
        return self._turns[turn_id][1]

    def started(self) -> None:
        """The call began: its root span opens."""
        self._call_span()

    def turn_opened(self, turn_id: int) -> None:
        """The caller's turn `turn_id` began: its trace's root span opens."""
        self._turn_span(turn_id)

    def stt_sent(
        self, turn_id: int, *, model: str, language: str | None, audio_seconds: float
    ) -> None:
        """The turn's speech-to-text request went: its span opens under the turn's."""
        stack = ExitStack()
        parent = self._turn_span(turn_id)
        stt = self._tracing.speech_to_text(
            parent, model=model, language=language, audio_seconds=audio_seconds
        )
        self._stt[turn_id] = (stack, stack.enter_context(stt))

    def stt_heard(
        self, turn_id: int, *, text: str, language: str | None, billed_seconds: float | None
    ) -> None:
        """The turn's transcript came, or its request failed (no text): its span ends."""
        opened = self._stt.pop(turn_id, None)
        if opened is not None:
            stack, stt = opened
            stt.record(text=text, language=language, billed_seconds=billed_seconds)
            stack.close()

    def tts_started(
        self, reply_id: int, turn_id: int | None, *, model: str, voice: str, language: str
    ) -> None:
        """The reply `reply_id` was asked for: its span opens under its turn's (while that is
        open) or the call's."""
        if turn_id is not None and turn_id in self._turns:
            parent = self._turns[turn_id][1]
        else:
            parent = self._call_span()[1]
        stack = ExitStack()
        tts = text_to_speech(self._tracing, parent, model=model, voice=voice, language=language)
        self._tts[reply_id] = (stack, stack.enter_context(tts))

    def tts_ended(self, reply_id: int, numbers: ReplyNumbers, *, text: str = "") -> None:
        """The reply ended, however: its span ends with what it took and, under
        `tracing.include_transcripts`, what it was to say."""
        opened = self._tts.pop(reply_id, None)
        if opened is not None:
            stack, tts = opened
            tts.record(numbers, text=text if self._tracing.include_transcripts else "")
            stack.close()

    def tool_began(
        self, turn_id: int, tool_call_id: str, *, tool: str, arguments: str = ""
    ) -> None:
        """A tool call of the turn `turn_id` began: its span opens under the turn's, while that
        is open, with the arguments the model wrote (`tracing.include_transcripts`)."""
        if turn_id in self._turns:
            stack = ExitStack()
            span = stack.enter_context(self._tracing.tool(self._turns[turn_id][1], tool=tool))
            if arguments and self._tracing.include_transcripts:
                span.set_attribute(SpanAttributes.INPUT_VALUE, arguments)
                span.set_attribute(
                    SpanAttributes.INPUT_MIME_TYPE, OpenInferenceMimeTypeValues.JSON.value
                )
            self._tools[tool_call_id] = (turn_id, stack, span)

    def tool_ended(
        self, tool_call_id: str, *, ok: bool, failure: str | None, result: str = ""
    ) -> None:
        """The tool call ended: its span ends with whether it succeeded, what failed and, under
        `tracing.include_transcripts`, what it gave back."""
        opened = self._tools.pop(tool_call_id, None)
        if opened is not None:
            _, stack, span = opened
            if result and self._tracing.include_transcripts:
                span.set_attribute(SpanAttributes.OUTPUT_VALUE, result)
                span.set_attribute(
                    SpanAttributes.OUTPUT_MIME_TYPE, OpenInferenceMimeTypeValues.JSON.value
                )
            span.set_attribute("tool.ok", ok)
            if failure is not None:
                span.set_attribute("tool.failure", failure)
            if not ok:
                span.set_status(StatusCode.ERROR, failure or "failed")
            stack.close()

    def turn_ended(
        self, turn_id: int, attributes: Attributes, *, heard: str = "", said: str = ""
    ) -> None:
        """The turn is done: its tool calls' and speech-to-text spans, if still open, then its
        root span end, with `attributes` (its outcome and times) and, under
        `tracing.include_transcripts`, what was `heard` and what its reply `said`."""
        for tool_call_id, opened in list(self._tools.items()):
            if opened[0] == turn_id:
                del self._tools[tool_call_id]
                opened[1].close()
        stt = self._stt.pop(turn_id, None)
        if stt is not None:
            stt[0].close()
        turn = self._turns.pop(turn_id, None)
        if turn is not None:
            stack, span = turn
            span.set_attributes(attributes)
            if self._tracing.include_transcripts:
                _words(span, SpanAttributes.INPUT_VALUE, SpanAttributes.INPUT_MIME_TYPE, heard)
                _words(span, SpanAttributes.OUTPUT_VALUE, SpanAttributes.OUTPUT_MIME_TYPE, said)
            stack.close()

    def close(self, attributes: Attributes) -> None:
        """End every span still open: the replies', the turns' (each with what it had), then the
        call's, with `attributes` (the call's report as numbers)."""
        for _, stack, _ in self._tools.values():
            stack.close()
        self._tools.clear()
        for stack, _ in [*self._tts.values(), *self._stt.values(), *self._turns.values()]:
            stack.close()
        self._tts.clear()
        self._stt.clear()
        self._turns.clear()
        stack, span = self._call_span()
        span.set_attributes(attributes)
        stack.close()
        self._call = None

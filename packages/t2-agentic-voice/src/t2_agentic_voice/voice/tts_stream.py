"""One call's streaming text-to-speech (D-121; the design's 6.1), for the text-to-speech bridge
(tts_bridge.py): with `tts.stream_replies` on and a text-to-speech that streams the call's
language (`StreamingTextToSpeech`: ElevenLabs' adapter, or the clause cache over it), the
talker's replies are spoken on one socket for the call. With the setting off the bridge has none,
and every clause goes as before.

- **Opened** as the call's pipeline starts (the bridge's `start`): the provider's session, its
  socket opened in the background for the call's language. **Closed** at the call's end (the
  bridge's `cancel` and `cleanup`).
- **What goes on it**: a clause the talker wrote (`Speak.talker`, open_reply.py's `add_clause`)
  in a language the provider streams, sent as the session asks for it, one at a time, flushed;
  a reply's first clause starts a new turn, so one reply is one turn of the voice. Fixed
  phrases, an action's lines, the echo's words and a repeat keep to one request a clause
  (`synthesize`); a talker's clause the clause cache holds plays from it first, as before.
  Captions and the output guard read the clause's text as before; nothing here reads audio.
- **A stop** (the bridge's interruption) cuts the clause in flight: what the provider still held
  of it is dropped (on ElevenLabs, a new socket opened at once in the background).
- **A failure** of the socket, at its opening, a keep-alive or a clause, turns it off for the
  rest of the call, with one `tts_stream_fell_back` line (the call, the provider, the failure's
  kind, the reply and clause, and whether any of the clause's audio had come; never its text):
  a clause with no audio yet is then requested as before, in its place; one with some fails as
  a request that fails mid-take does (the bridge's `ClauseFailed`). An adapter's own exception
  counts as a failure there, logged by its type.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, AsyncIterator

from pydantic import JsonValue

from t2_agentic_voice.core.errors import ProviderError
from t2_agentic_voice.core.events import CallId
from t2_agentic_voice.core.logging import get_logger
from t2_agentic_voice.domain.ports.speech_stream import SpeechStream, StreamingTextToSpeech
from t2_agentic_voice.domain.ports.text_to_speech import AudioChunk, TextToSpeech
from t2_agentic_voice.voice.protocol import ReplyId
from t2_agentic_voice.voice.session.commands import Speak

log = get_logger(__name__)


class CallStream:
    """One call's streaming text-to-speech over `tts`, for the call `call_id` held in
    `language` (the module's docstring)."""

    def __init__(self, tts: TextToSpeech, *, language: str, call_id: CallId) -> None:
        self._tts = tts
        self._source = tts if isinstance(tts, StreamingTextToSpeech) else None
        self._language, self._call_id = language, call_id
        self._stream: SpeechStream | None = None
        self._reply: ReplyId | None = None  # the reply the socket spoke last
        self._closing: asyncio.Task[None] | None = None
        self._closed = False

    def start(self) -> None:
        """Open the call's session, when the provider streams the call's language."""
        source = self._source
        if self._closed or self._stream is not None or source is None:
            return
        if source.streams(self._language):
            self._stream = source.open_stream(language=self._language)
            log.info(
                "tts_stream_opened",
                call_id=self._call_id,
                provider=self._tts.name,
                language=self._language,
            )

    def cut(self) -> None:
        """A stop: the clause in flight on the socket, if any, is dropped."""
        if self._stream is not None:
            self._stream.cut()

    async def speech(self, speak: Speak) -> AsyncGenerator[AudioChunk, None]:
        """The audio of `speak`: on the socket when it takes it, else today's request, which a
        clause also gets in its place when the socket failed before its first audio."""
        stream, source = self._stream, self._source
        if stream is None or source is None or not speak.talker:
            on_socket = False
        else:
            on_socket = source.streams(speak.language)
        if stream is None or not on_socket:
            async for chunk in self._requested(speak):
                yield chunk
            return
        new_turn = speak.reply_id != self._reply
        self._reply = speak.reply_id
        heard = False
        failure: ProviderError
        try:
            said = stream.say(speak.text, language=speak.language, new_turn=new_turn)
            try:
                async for chunk in said:
                    heard = True
                    yield chunk
            finally:  # a cancel or a close here is a cut, which reaches the socket at once
                await self.close(said)
            return
        except ProviderError as error:
            failure = error
        except Exception as error:  # an adapter's bug: the socket is let go as on a failure
            details: dict[str, JsonValue] = {"provider": self._tts.name}
            details["error"] = type(error).__name__
            failure = ProviderError("server_error", False, details=details)
        self._fall_back(stream, speak, failure, heard=heard)
        if heard:  # some of it played: it fails, as a request that fails mid-take
            raise failure from None
        async for chunk in self._requested(speak):
            yield chunk

    @staticmethod
    async def close(takes: AsyncIterator[AudioChunk]) -> None:
        """Close `takes`, a clause's audio from `speech`, so a cancel or an early end reaches
        the socket at once, not when the iterator is collected."""
        close = getattr(takes, "aclose", None)
        if close is not None:
            await close()

    async def aclose(self) -> None:
        """Close the session, at the call's end; a second close does nothing."""
        self._closed = True
        stream, self._stream = self._stream, None
        if stream is not None:
            await stream.aclose()
        if self._closing is not None:
            await asyncio.gather(self._closing, return_exceptions=True)

    async def _requested(self, speak: Speak) -> AsyncGenerator[AudioChunk, None]:
        """Today's request for `speak`, closed with it."""
        chunks = self._tts.synthesize(speak.text, language=speak.language)
        try:
            async for chunk in chunks:
                yield chunk
        finally:
            await self.close(chunks)

    def _fall_back(
        self, stream: SpeechStream, speak: Speak, failure: ProviderError, *, heard: bool
    ) -> None:
        """The socket failed: off for the rest of the call, closed in the background, and one
        line (the module's docstring)."""
        if self._stream is not stream:
            return
        self._stream = None
        self._closing = asyncio.get_running_loop().create_task(
            stream.aclose(), name="t2v-tts-stream-close"
        )
        log.warning(
            "tts_stream_fell_back",
            call_id=self._call_id,
            provider=self._tts.name,
            kind=failure.kind,
            retryable=failure.retryable,
            error=failure.details.get("error"),
            reply_id=speak.reply_id,
            clause=speak.clause,
            audio=heard,
        )


def call_stream(
    tts: TextToSpeech, *, on: bool, language: str, call_id: CallId
) -> CallStream | None:
    """The call's streaming text-to-speech under `tts.stream_replies` (`on`), when `tts` can
    stream at all; None otherwise, so the bridge speaks as before."""
    if not on or not isinstance(tts, StreamingTextToSpeech):
        return None
    return CallStream(tts, language=language, call_id=call_id)

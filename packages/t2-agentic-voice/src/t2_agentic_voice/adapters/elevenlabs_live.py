"""ElevenLabs' Scribe v3 Live behind the streaming speech-to-text port (plan 010's 5.1;
domain/ports/transcript_stream.py): `open_live` opens one call's realtime session, a `LiveStream`.

The protocol is the one the probe of 2026-11-18 measured on the golden set's dev split (292
variants at 5e973f6; on those with speech, commit to final transcript p50 249.9 ms and p95 301.6
ms, against batch Scribe v3's 567.5 and 812.2 ms), from ElevenLabs' realtime pages (read
2026-11-18); its messages are adapters/elevenlabs_live_wire.py's:

- The socket is adapters/provider_socket.py's `open_socket` (no proxy, no compression, a logger
  that logs nothing), the key in the `xi-api-key` header, the query naming the model, the
  sample rate, a manual commit, the call's language and its prompt's keyterms.
- The server sends `session_started` first: the stream is handed over only then, within
  `OPEN_S` of the handshake's start.
- The audio goes in `CHUNK_S` messages, the probe's frames, in the order fed; a commit is a
  message of empty audio marked `commit`. With nothing fed for `KEEPALIVE_S`, one message of
  silence goes, since the server closes after 15 s with no client message.
- Each commit is answered by one `committed_transcript`, matched to the commits in the order
  they went. One with no commit waiting (Scribe's own, after about 36 s of audio not committed)
  is dropped and counted (`dropped`). Partials and `committed_transcript_with_timestamps`, whose
  language only echoes the one named, are not read.
- An error message (`auth_error`, `commit_throttled`, ...), a lost socket, or more than
  `MOST_QUEUED_S` of audio not yet sent fails the stream: its `failure` is set and every commit
  waiting raises it.

Its output is data, never an instruction (docs/SECURITY.md, trust boundaries). Its one log line,
`stt_live_closed`, holds counts alone.
"""

from __future__ import annotations

import asyncio
import copy
from collections import deque
from typing import Final

from pydantic import SecretStr

from t2_agentic_voice.adapters.elevenlabs_live_wire import (
    LONGEST_KEYTERM,
    MOST_KEYTERMS,
    RATES,
    audio_message,
    check_message,
    live_failure,
    live_url,
    read_message,
    stream_error,
)
from t2_agentic_voice.adapters.provider_http import keyterms
from t2_agentic_voice.adapters.provider_socket import Opener, Socket, close_quietly
from t2_agentic_voice.core.errors import ProviderError
from t2_agentic_voice.core.logging import get_logger
from t2_agentic_voice.domain.ports.speech_to_text import Transcript

log = get_logger(__name__)

CHUNK_S: Final = 0.02  # the audio of one message, the probe's frame
KEEPALIVE_S: Final = 5.0  # with nothing fed this long, a message of silence goes
OPEN_S: Final = 10.0  # the longest the handshake and `session_started` take
MOST_QUEUED_S: Final = 10.0  # audio waiting to go past which the stream has failed


async def open_live(
    *,
    key: SecretStr,
    base_url: str,
    model: str,
    language: str | None,
    prompt: str | None,
    sample_rate: int,
    opener: Opener,
) -> LiveStream:
    """One call's realtime session, once `session_started` came (the module's docstring);
    ProviderError when it does not open, a cancel closing what was opened."""
    if sample_rate not in RATES:
        raise stream_error("sample_rate", kind="rejected", retryable=False)
    terms = keyterms(prompt, most=MOST_KEYTERMS, longest=LONGEST_KEYTERM)
    url = live_url(base_url, model=model, language=language, terms=terms, sample_rate=sample_rate)
    socket: Socket | None = None
    try:
        async with asyncio.timeout(OPEN_S):
            socket = await opener(url, {"xi-api-key": key.get_secret_value()}, OPEN_S)
            await _started(socket)
    except asyncio.CancelledError:
        await close_quietly(socket)
        raise
    except Exception as error:  # every failure, the handshake's and the server's; never a cancel
        await close_quietly(socket)
        failure = live_failure(error)
    else:
        return LiveStream(socket, sample_rate=sample_rate, language=language)
    raise failure from None


async def _started(socket: Socket) -> None:
    """Read the server's messages until `session_started`; an error message raises."""
    while True:
        message = read_message(await socket.recv())
        if message.message_type == "session_started":
            return
        check_message(message)


def _retrieve(future: asyncio.Future[Transcript]) -> None:
    """Mark a commit's failure read, so one nobody waited for warns of nothing."""
    if not future.cancelled():
        future.exception()


class LiveStream:
    """One call's realtime session on `socket` (the `TranscriptStream` port; the module's
    docstring), its audio at `sample_rate`, its transcripts in `language`."""

    def __init__(self, socket: Socket, *, sample_rate: int, language: str | None) -> None:
        self._socket, self._rate, self._language = socket, sample_rate, language
        self._chunk = round(sample_rate * CHUNK_S) * 2
        self._buffer = bytearray()
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._waiting: deque[asyncio.Future[Transcript]] = deque()
        self._answers: dict[int, asyncio.Future[Transcript]] = {}
        self._failure: ProviderError | None = None
        self._closed = False
        self._closing: asyncio.Task[None] | None = None
        self.dropped = 0  # transcripts that came with no commit waiting
        self._sender = asyncio.create_task(self._send_all(), name="t2v-stt-live-send")
        self._reader = asyncio.create_task(self._read_all(), name="t2v-stt-live-read")

    @property
    def failure(self) -> ProviderError | None:
        """Why the stream stopped hearing; None while it hears."""
        return self._failure

    def feed(self, pcm16: bytes) -> None:
        """Queue the call's next audio, in `CHUNK_S` messages; dropped once failed or closed."""
        if self._failure is not None or self._closed:
            return
        self._buffer += pcm16
        while len(self._buffer) >= self._chunk:
            self._queue.put_nowait(audio_message(bytes(self._buffer[: self._chunk]), self._rate))
            del self._buffer[: self._chunk]
        if self._queue.qsize() * CHUNK_S > MOST_QUEUED_S:
            self._fail(stream_error("send_backlog", kind="timeout"))

    def commit(self) -> int:
        """End the audio fed so far (its last part sent first); the commit's number."""
        number = len(self._answers)
        future: asyncio.Future[Transcript] = asyncio.get_running_loop().create_future()
        future.add_done_callback(_retrieve)
        self._answers[number] = future
        if self._failure is not None or self._closed:
            future.set_exception(copy.copy(self._failure or stream_error("closed")))
            return number
        if self._buffer:
            self._queue.put_nowait(audio_message(bytes(self._buffer), self._rate))
            self._buffer.clear()
        self._queue.put_nowait(audio_message(b"", self._rate, commit=True))
        self._waiting.append(future)
        return number

    async def committed(self, number: int) -> Transcript:
        """Commit `number`'s transcript, once it came; ProviderError when the stream failed or
        closed first. A cancel stops this wait alone."""
        future = self._answers.get(number)
        if future is None:
            raise stream_error("unknown_commit", kind="server_error", retryable=False)
        return await asyncio.shield(future)

    async def aclose(self) -> None:
        """Close the session: its tasks stopped, its socket closed, a commit still waiting
        failed."""
        if self._closed:
            return
        self._closed = True
        self._settle(stream_error("closed"))
        for task in (self._sender, self._reader):
            task.cancel()
        await asyncio.gather(self._sender, self._reader, return_exceptions=True)
        await (self._closing or close_quietly(self._socket))
        log.info("stt_live_closed", commits=len(self._answers), dropped=self.dropped)

    async def _send_all(self) -> None:
        """Send what is queued, in order, and a message of silence after `KEEPALIVE_S` with
        nothing."""
        silence = audio_message(bytes(self._chunk), self._rate)
        try:
            while True:
                try:
                    message = await asyncio.wait_for(self._queue.get(), KEEPALIVE_S)
                except TimeoutError:
                    message = silence
                await self._socket.send(message)
        except Exception as error:  # the socket's failure; never a cancel
            self._fail(live_failure(error))

    async def _read_all(self) -> None:
        """Read the server's messages: each `committed_transcript` answers the oldest commit
        waiting; an error message or a lost socket fails the stream."""
        try:
            while True:
                message = read_message(await self._socket.recv())
                if message.message_type == "committed_transcript":
                    self._answered((message.text or "").strip())
                else:
                    check_message(message)
        except Exception as error:  # the socket's or the server's failure; never a cancel
            self._fail(live_failure(error))

    def _answered(self, text: str) -> None:
        if not self._waiting:
            self.dropped += 1
            return
        future = self._waiting.popleft()
        if not future.done():
            future.set_result(Transcript(text=text, language=self._language))

    def _fail(self, error: ProviderError) -> None:
        """The stream failed with `error`: every commit waiting fails, its tasks stop, its
        socket closes in the background."""
        if self._failure is not None or self._closed:
            return
        self._failure = error
        self._settle(error)
        current = asyncio.current_task()
        for task in (self._sender, self._reader):
            if task is not current:
                task.cancel()
        self._closing = asyncio.create_task(close_quietly(self._socket))

    def _settle(self, error: ProviderError) -> None:
        while self._waiting:
            future = self._waiting.popleft()
            if not future.done():
                future.set_exception(copy.copy(error))

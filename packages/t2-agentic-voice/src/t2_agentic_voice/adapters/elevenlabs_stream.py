"""ElevenLabs' Text-to-Dialogue socket behind the streaming text-to-speech port (D-121; the
design's 6.1): one call's session, `DialogueStream`, which `ElevenLabsTTS.open_stream` opens
(adapters/elevenlabs_tts.py) for a language whose model is one of ElevenLabs' dialogue models
(`eleven_v3*`, `eleven_v4*`: v4 Turbo, the default, D-114). Its messages are
adapters/elevenlabs_frames.py's, from ElevenLabs' reference and guides (read 2026-11-18):

- **The socket**: `wss://api.elevenlabs.io/v1/text-to-dialogue/stream-input`, with the model,
  `output_format=pcm_24000` and the clause's `language_code` (`ar`, `en`) in its query and the
  key in the handshake's `xi-api-key` header, opened by adapters/provider_socket.py's
  `open_socket` (no proxy, no compression, no pings, a logger that logs nothing), frames of up
  to `MAX_FRAME` bytes; its first message registers the language's voice (v4 takes one).
- **A clause** (`say`): sent flushed, so its audio is made at once (unflushed, the server holds a
  turn's text until it has about 40 characters and 8 words), with `new_turn` on a reply's first
  clause once the socket has spoken. Its audio, base64 raw PCM at 24 kHz, is read in whole
  samples by the HTTP adapter's reader (adapters/pcm_takes.py: the same silence trim and
  cut-short flag) until the frame that ends the clause. `tts.timeout_s` bounds the handshake and
  each wait for a frame.
- **A cut**: v4 has no multi-context socket, so a clause cannot be dropped from its socket. A cut
  closes it, sending no `close_socket` (which would make the rest of the audio), and opens a new
  one at once in the background, which the next clause finds open.
- **The idle limit**: the server ends a socket that hears nothing for 20 s, so
  `{"keep_alive": true}` goes once `KEEP_ALIVE_S` pass with nothing sent, never during a clause.
- **Sessions**: each open socket holds one dialogue session, from a pool of its own (14 on the
  free plan to 105 on Scale; past it, `too_many_concurrent_requests`), for as long as it is open:
  a call holds one, two for a moment after a cut or a change of language.
- **Failures**: a refused handshake, a close or no frame in time is a ProviderError as the
  socket helper maps it, an error frame its `refusal`; none names the key or the text. After
  one, every `say` raises it.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncGenerator, Mapping
from dataclasses import dataclass
from typing import Final
from urllib.parse import urlencode

from pydantic import SecretStr

from t2_agentic_voice.adapters.elevenlabs_frames import (
    KEEP_ALIVE,
    PROVIDER,
    Frame,
    clause_message,
    details,
    voices_message,
)
from t2_agentic_voice.adapters.pcm_takes import PcmTake, no_voice
from t2_agentic_voice.adapters.provider_socket import (
    Opener,
    Socket,
    close_quietly,
    open_socket,
    socket_failure,
)
from t2_agentic_voice.core.errors import ProviderError
from t2_agentic_voice.core.settings.tts import LanguageTag, TtsVoice
from t2_agentic_voice.core.settings.words import primary_code
from t2_agentic_voice.domain.ports.text_to_speech import AudioChunk

DIALOGUE_URL: Final = "wss://api.elevenlabs.io/v1/text-to-dialogue/stream-input"
RATE: Final = 24_000
DIALOGUE_MODELS: Final = ("eleven_v3", "eleven_v4")  # the prefixes the socket takes
KEEP_ALIVE_S: Final = 8.0  # under the server's 20 s, with a quarter of it to notice
MAX_FRAME: Final = 1 << 24  # a long clause's audio, base64, in one frame

Key = tuple[str, str, str]  # a socket's model, voice and language code


def on_dialogue_socket(model: str) -> bool:
    """Whether ElevenLabs' Text-to-Dialogue socket takes `model`."""
    return model.startswith(DIALOGUE_MODELS)


async def open_dialogue(url: str, headers: Mapping[str, str], open_timeout_s: float) -> Socket:
    """The dialogue socket at `url`, its frames up to `MAX_FRAME` bytes."""
    return await open_socket(url, headers, open_timeout_s, max_size=MAX_FRAME)


@dataclass
class _Line:
    """One open socket: its key, when a message last went on it, and whether it has spoken."""

    socket: Socket
    key: Key
    sent_at: float = 0.0
    spoke: bool = False

    async def send(self, message: str) -> None:
        await self.socket.send(message)
        self.sent_at = asyncio.get_running_loop().time()


class DialogueStream:
    """One call's session on ElevenLabs' Text-to-Dialogue socket, a `SpeechStream` (the module's
    docstring): each language's model and voice from `voices`, its socket for `language` opened
    at once in the background. `opener` replaces the socket's connection (a test's fake)."""

    def __init__(
        self,
        *,
        api_key: SecretStr,
        voices: Mapping[LanguageTag, TtsVoice] | Mapping[str, TtsVoice],
        language: str,
        timeout_s: float,
        trim_silence: bool = False,
        url: str = DIALOGUE_URL,
        opener: Opener = open_dialogue,
        keep_alive_s: float = KEEP_ALIVE_S,
    ) -> None:
        self._api_key = api_key
        self._voices: dict[str, TtsVoice] = dict(voices.items())
        self._url, self._open = url, opener
        self._timeout_s, self._trim, self._keep_alive_s = timeout_s, trim_silence, keep_alive_s
        self._line: _Line | None = None  # the socket open
        self._busy: _Line | None = None  # the socket a clause is on
        self._pending: asyncio.Task[_Line] | None = None  # the socket opening
        self._pending_key: Key | None = None
        self._broken: ProviderError | None = None
        self._closed = False
        self._closing: set[asyncio.Task[None]] = set()
        key = self._key_of(language)
        if key is not None:
            self._open_soon(key)
        loop = asyncio.get_running_loop()
        self._keeper = loop.create_task(self._keep_alive(), name="t2v-tts-keep-alive")

    def __repr__(self) -> str:
        return f"DialogueStream(languages={sorted(self._voices)!r})"

    async def say(
        self, text: str, *, language: str, new_turn: bool
    ) -> AsyncGenerator[AudioChunk, None]:
        """`text`, one clause, spoken on the socket of `language` (the port's `say`)."""
        voice = self._voices.get(language)
        if voice is None:
            raise no_voice()
        if self._broken is not None:
            raise self._broken
        self.cut()  # a clause still open is cut: one `say` at a time
        take = PcmTake(rate=RATE, trim=self._trim)
        line: _Line | None = None
        problem: ProviderError | None = None
        ended = False
        try:
            line = await self._ready((voice.model, voice.voice, primary_code(language)))
            self._busy = line
            await line.send(clause_message(text, voice.voice, new_turn=new_turn and line.spoke))
            line.spoke = True
            while not ended:
                frame = await self._frame(line)
                chunk = take.feed(frame.pcm())
                if chunk is not None:
                    yield chunk
                ended = frame.ends
        except Exception as error:  # every failure, the socket's and the answer's; never a cancel
            # On a socket a cut let go, the clause ends there: that is no failure.
            if line is None or line is self._line:
                problem = error if isinstance(error, ProviderError) else _failure(error)
        finally:
            if self._busy is line:
                self._busy = None
            if line is not None and not ended:  # a cut, or a failure: the socket is let go
                self._drop(line, reopen=problem is None)
        if problem is not None:
            self._broken = problem
            raise problem from None
        if not ended:
            return
        last = take.last(text, language)
        if last is not None:
            yield last

    def cut(self) -> None:
        """Drop the clause in flight, if any: its socket closed, a new one opening."""
        line, self._busy = self._busy, None
        if line is not None:
            self._drop(line, reopen=True)

    async def aclose(self) -> None:
        """Close the session's sockets and stop its keep-alive; a second close does nothing."""
        if self._closed:
            return
        self._closed = True
        pending = self._pending
        self._forget_pending()
        self._keeper.cancel()
        await asyncio.gather(self._keeper, *([pending] if pending else []), return_exceptions=True)
        line, self._line, self._busy = self._line, None, None
        if line is not None:
            await close_quietly(line.socket)
        await asyncio.gather(*self._closing, return_exceptions=True)

    def _key_of(self, language: str) -> Key | None:
        voice = self._voices.get(language)
        if voice is None or not on_dialogue_socket(voice.model):
            return None
        return voice.model, voice.voice, primary_code(language)

    async def _ready(self, key: Key) -> _Line:
        """The socket for `key`: the one open, the one opening, or one opened now, any other
        let go."""
        self._settle()
        if self._broken is not None:
            raise self._broken
        if self._closed:
            raise ProviderError("connection_lost", True, details=details("closed"))
        line = self._line
        if line is not None and line.key == key:
            return line
        if line is not None:
            self._drop(line, reopen=False)
        pending = self._pending
        if pending is not None and self._pending_key == key:
            with contextlib.suppress(Exception):  # its failure is read by `_settle`
                await asyncio.shield(pending)  # a cut here leaves it opening for the next
            self._settle()
        else:
            self._forget_pending()
            self._line = await self._connect(key)
        if self._broken is not None:
            raise self._broken
        if self._line is None:  # the session closed while it opened
            raise ProviderError("connection_lost", True, details=details("closed"))
        return self._line

    async def _connect(self, key: Key) -> _Line:
        """A new socket for `key`, its voice registered; a ProviderError when it fails."""
        model, voice, code = key
        asked = {"model_id": model, "output_format": f"pcm_{RATE}", "language_code": code}
        query = urlencode(asked)
        headers = {"xi-api-key": self._api_key.get_secret_value()}
        socket: Socket | None = None
        line: _Line | None = None
        problem: ProviderError | None = None
        try:
            socket = await self._open(f"{self._url}?{query}", headers, self._timeout_s)
            opening = _Line(socket=socket, key=key)
            await opening.send(voices_message(voice))
            line = opening
        except Exception as error:  # never a cancel
            problem = _failure(error)
        finally:
            if socket is not None and line is None:
                self._close_soon(socket)
        if line is None:  # raised here, past the handler, so it chains to nothing
            raise problem or ProviderError("server_error", False, details=details("not_open"))
        return line

    async def _frame(self, line: _Line) -> Frame:
        """The socket's next frame, within `timeout_s`; an error frame raises its refusal."""
        async with asyncio.timeout(self._timeout_s):
            raw = await line.socket.recv()
        frame = Frame.read(raw)
        if frame.error is not None:
            raise frame.refusal()
        return frame

    async def _keep_alive(self) -> None:
        """`{"keep_alive": true}` on the open socket once `keep_alive_s` pass with nothing sent
        on it, never during a clause; a failed one breaks the session."""
        loop = asyncio.get_running_loop()
        while True:
            self._settle()
            line, wait = self._line, self._keep_alive_s / 4
            if line is not None and line is not self._busy:
                due = line.sent_at + self._keep_alive_s - loop.time()
                if due <= 0:
                    try:
                        await line.send(KEEP_ALIVE)
                    except Exception as error:  # never a cancel
                        self._broken = self._broken or _failure(error)
                        self._drop(line, reopen=False)
                    continue
                wait = min(wait, due)
            await asyncio.sleep(wait)

    def _open_soon(self, key: Key) -> None:
        self._pending_key = key
        loop = asyncio.get_running_loop()
        self._pending = loop.create_task(self._connect(key), name="t2v-tts-socket")

    def _settle(self) -> None:
        """A socket opened in the background becomes the one open; its failure breaks the
        session."""
        pending = self._pending
        if pending is None or not pending.done():
            return
        self._pending = None
        if pending.cancelled():
            return
        error = pending.exception()
        if error is not None:
            failure = error if isinstance(error, ProviderError) else _failure(error)
            self._broken = self._broken or failure
        elif self._line is None and not self._closed:
            self._line = pending.result()
        else:
            self._close_soon(pending.result().socket)

    def _forget_pending(self) -> None:
        """The socket opening is not wanted: cancelled, or closed if it is open."""
        pending, self._pending = self._pending, None
        if pending is None:
            return
        if not pending.done():
            pending.cancel()
        elif not pending.cancelled() and pending.exception() is None:
            self._close_soon(pending.result().socket)

    def _drop(self, line: _Line, *, reopen: bool) -> None:
        """Let `line` go, when it is still the one open: closed in the background, and a new
        socket for its key opened at once when `reopen` (a cut)."""
        if line is not self._line:
            return
        self._line = None
        self._close_soon(line.socket)
        if reopen and not self._closed and self._broken is None:
            self._forget_pending()
            self._open_soon(line.key)

    def _close_soon(self, socket: Socket) -> None:
        loop = asyncio.get_running_loop()
        task = loop.create_task(close_quietly(socket), name="t2v-tts-socket-close")
        self._closing.add(task)
        task.add_done_callback(self._closing.discard)


def _failure(error: BaseException) -> ProviderError:
    """The ProviderError for one failure of the socket (the module's docstring)."""
    if isinstance(error, Exception):
        return socket_failure(PROVIDER, error)
    return ProviderError("server_error", False, details=details(type(error).__name__))

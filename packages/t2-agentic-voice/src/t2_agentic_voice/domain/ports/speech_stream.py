"""The streaming text-to-speech port (the design's 6.1, D-121), beside `TextToSpeech`, which stays
as it is: a text-to-speech that can also speak a call's replies over one socket a call, each
clause sent as the talker writes it, each reply one turn of the voice.

- `StreamingTextToSpeech`, which a text-to-speech meets as well (ElevenLabs' adapter; the clause
  cache passes on the one it wraps): `streams(language)` says whether `language`'s model and voice
  speak on the provider's socket; `open_stream(language=...)` opens one call's session, its
  socket opened at once in the background for `language` (the call's). It never raises: a
  failure to open shows at the first `say`.
- `SpeechStream`, one call's session. `say` speaks one clause on it, flushed at once, its audio
  as `AudioChunk`s as they come (mono PCM16 at the rate the provider gave, as the port's), ending
  with the clause's last; `new_turn` on a reply's first clause, so the voice starts a new turn
  there and one reply is one turn. One `say` at a time. A `say` closed or cancelled before its
  end, or a `cut()` while it runs, is a cut: what the socket still held of the clause is dropped
  and the session is ready for the next `say` (a provider that cannot drop one turn of a socket
  gets a new socket, opened at once in the background). The session keeps its socket alive under
  the provider's idle limit, follows each clause's language (a socket of another model, voice or
  language code is opened when a clause needs one) and is closed with `aclose()` at the call's
  end. Every failure, the socket's opening, a keep-alive's or a clause's, is a `ProviderError`
  naming no key or text; once one has come, every later `say` raises it.

Public through the `ports` facade, provisional (D-121).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol, runtime_checkable

from t2_agentic_voice.domain.ports.text_to_speech import AudioChunk


class SpeechStream(Protocol):
    """One call's session on a provider's streaming socket (the module's docstring)."""

    def say(self, text: str, *, language: str, new_turn: bool) -> AsyncIterator[AudioChunk]:
        """`text`, one clause, spoken in `language`'s model and voice and flushed, chunk by
        chunk as the provider streams it; `new_turn` for a reply's first clause. A cancel, or
        closing the iterator before its end, cuts it."""

    def cut(self) -> None:
        """A stop: the clause in flight, if any, is dropped (the module's docstring); nothing
        when none is."""

    async def aclose(self) -> None:
        """Close the session's sockets, at the call's end; a second close does nothing."""


@runtime_checkable
class StreamingTextToSpeech(Protocol):
    """A text-to-speech that can also speak over one socket a call (the module's docstring)."""

    def streams(self, language: str) -> bool:
        """Whether `language`'s model and voice speak on the provider's socket."""

    def open_stream(self, *, language: str) -> SpeechStream:
        """A new session for one call, its socket opened in the background for `language`;
        called in the running event loop, and never raising."""

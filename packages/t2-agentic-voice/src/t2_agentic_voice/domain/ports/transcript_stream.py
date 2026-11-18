"""The streaming speech-to-text port (plan 010's 5.1): a provider that hears a whole call as one
stream, beside the batch port (speech_to_text.py), which it leaves as it is. Optional: a
provider implements it as well as `SpeechToText`, and the batch port stays the fallback.

- `StreamingSpeechToText.open_stream` opens one call's stream in a language, with the call's
  prompt as context, and returns it once the provider is ready to hear. It raises
  `ProviderError` when the stream does not open; a cancel stops it at once.
- `TranscriptStream.feed` gives the stream the call's next audio, in order, as it comes, and never
  blocks; once the stream has failed or closed, audio fed is dropped.
- `TranscriptStream.commit` ends the stretch of audio fed since the last commit (the end of a turn)
  and returns its number. `committed` waits for that commit's transcript: the words the provider
  heard in that stretch, in the stream's language. It raises `ProviderError` when the stream
  failed before the answer came, and a cancel stops only that wait, never the commit, so another
  wait may read the same answer.
- `TranscriptStream.failure` is None while the stream hears, and the failure once it failed (its
  connection lost, the provider's error), after which nothing more is answered.
- `TranscriptStream.aclose` closes it; a commit still waiting then raises `ProviderError`.

Runtime-checkable, so the bridge knows a provider that streams. Provisional (D-021's facades):
the ElevenLabs adapter implements it with Scribe v3 Live (adapters/elevenlabs_live.py).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from t2_agentic_voice.core.errors import ProviderError
from t2_agentic_voice.domain.ports.speech_to_text import Pcm16, Transcript


class TranscriptStream(Protocol):
    """One call's open stream (the module's docstring)."""

    @property
    def failure(self) -> ProviderError | None:
        """Why the stream stopped hearing; None while it hears."""

    def feed(self, pcm16: Pcm16) -> None:
        """The call's next audio, mono 16-bit PCM at the stream's sample rate, in order."""

    def commit(self) -> int:
        """End the audio fed since the last commit; its number, from 0, for `committed`."""

    async def committed(self, number: int) -> Transcript:
        """The transcript of commit `number`: ProviderError when the stream failed first."""

    async def aclose(self) -> None:
        """Close the stream, its connection and its tasks."""


@runtime_checkable
class StreamingSpeechToText(Protocol):
    """A speech-to-text provider that also hears a call as one stream (the module's
    docstring)."""

    async def open_stream(
        self, *, language: str | None, prompt: str | None, sample_rate: int
    ) -> TranscriptStream:
        """One call's stream: `language` the one to hear (None: the provider detects it),
        `prompt` text it may take as context (None: none), `sample_rate` the audio's. Raises
        `ProviderError` when it does not open; a cancel stops it at once."""

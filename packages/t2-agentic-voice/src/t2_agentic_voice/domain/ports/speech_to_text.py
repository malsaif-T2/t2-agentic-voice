"""The speech-to-text port, as the design's 6.1 gives it: a clip of speech in, a transcript out.

Every speech-to-text adapter implements `SpeechToText`. It raises `ProviderError` on a
provider's failure, and stops at once when its task is cancelled, leaving no task or connection
behind. Whoever builds an adapter closes it with `aclose()`, the one close every port that
holds connections has (the text-to-speech port and the used-token store too), so no caller
looks a close up by name. Public, and stable, through the `ports` facade (D-021).
"""

from __future__ import annotations

from typing import Annotated, Protocol

from pydantic import AfterValidator, BaseModel, ConfigDict, Field


class DataFlow(BaseModel):
    """Where a provider processes and keeps what it is sent, in the provider's own terms; a
    team reads it before it sends callers' audio there."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    provider: str  # "Groq"
    processed_in: str  # "not stated by the provider"
    stored_in: str  # "US (Google Cloud buckets), for data Groq retains"
    retention: str  # how long, and the switches that change it


def _whole_samples(value: bytes) -> bytes:
    """`value` when it holds whole 16-bit samples."""
    if len(value) % 2:
        raise ValueError("pcm16 holds whole 16-bit samples: an even number of bytes")
    return value


# Mono, 16-bit little-endian PCM, in whole samples of two bytes: a clip's audio, and a chunk's of
# the text-to-speech port.
Pcm16 = Annotated[bytes, AfterValidator(_whole_samples)]


def pcm16_seconds(pcm16: bytes, sample_rate: int) -> float:
    """How long `pcm16` plays at `sample_rate` samples a second."""
    return len(pcm16) / 2 / sample_rate


class AudioClip(BaseModel):
    """One stretch of speech: mono, 16-bit little-endian PCM, `sample_rate` samples a second."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    pcm16: Pcm16
    sample_rate: int = Field(default=16_000, gt=0)

    @property
    def seconds(self) -> float:
        """How long the clip lasts."""
        return pcm16_seconds(self.pcm16, self.sample_rate)


class Transcript(BaseModel):
    """What a speech-to-text provider heard in one clip."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    text: str
    # The language heard, or the one the request named, in the provider's code ("ar", "en").
    language: str | None
    # The provider's own confidence, when it gives one, on the provider's own scale (Whisper's:
    # the mean log-probability of its segments, 0 or below, not a share from 0 to 1).
    confidence: float | None = None
    # What the provider bills for the request, for usage metering.
    billed_seconds: float | None = Field(default=None, ge=0)
    # The provider's own estimate that the clip holds no speech (Whisper gives one), kept so a
    # silence rule can be tried later on stored results (the owner's ruling, D-021).
    no_speech_prob: float | None = Field(default=None, ge=0, le=1)
    # The headroom the provider reported for its key with this answer (Groq's
    # `x-ratelimit-remaining-requests` and `-tokens`), for the call's usage; None when the
    # adapter reads none, or the provider sent none it could read. GroqSTT reads them from the
    # SDK's raw response (adapters/groq_client.py's `raw_response` and `headroom`).
    remaining_requests: int | None = Field(default=None, ge=0)
    remaining_tokens: int | None = Field(default=None, ge=0)


class SpeechToText(Protocol):
    """A speech-to-text provider behind the port. `name` identifies it in logs and traces;
    `data_flow` says where the audio goes."""

    name: str
    data_flow: DataFlow

    async def transcribe(
        self, clip: AudioClip, *, language: str | None, prompt: str | None
    ) -> Transcript:
        """What was said in `clip`. `language` is a hint in the provider's code (`None`: let
        it detect the language); `prompt` is text the provider may take as context (`None`:
        none). Raises `ProviderError` on the provider's failure; a cancel stops it at once."""

    async def aclose(self) -> None:
        """Close what the adapter holds open, its connections; an adapter that holds none
        returns at once. Called once, when its owner (the runtime, a run) is done with it."""

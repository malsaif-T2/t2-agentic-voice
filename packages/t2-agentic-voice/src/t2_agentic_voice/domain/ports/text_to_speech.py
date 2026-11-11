"""The text-to-speech port, as the design's 6.1 gives it: a clause of text in, its speech out as a
stream of chunks, in the model and voice of the clause's language.

Every text-to-speech adapter implements `TextToSpeech`. It raises `ProviderError` on a
provider's failure, stops at once when its task is cancelled, leaving no task or connection
behind, and closes its connections with `aclose()`. The caller keeps each clause within
`max_chars` (the clause splitter does). Public, and stable, through the `ports` facade (D-021).

What a call's usage needs of a response travels on its chunks, since one adapter serves every
call at once: the rate-limit headroom the provider reported, on the first chunk of the response,
and a take that came back cut short, on its last.

`HeldSpeech`, beside the port and not in the `ports` facade, is what a text-to-speech that keeps
takes meets as well (adapters/clause_cache.py's `ClauseCache`): the take it holds for a text,
which the text-to-speech bridge asks for first and plays with no request. The port itself is
unchanged, so an adapter that keeps nothing never meets it.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, field_validator

from t2_agentic_voice.domain.ports.speech_to_text import DataFlow


class AudioChunk(BaseModel):
    """One piece of a clause's speech: mono, 16-bit little-endian PCM, `sample_rate` samples a
    second, the rate read from the provider's audio, never assumed. A chunk may be empty: the
    last one of a take, when it only carries `cut_short`."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    pcm16: bytes
    sample_rate: int = Field(gt=0)
    # What the provider still allows its key, as the response that carried this chunk reported
    # it (Groq's `x-ratelimit-remaining-requests` and `-tokens`): on the first chunk of a
    # response, None on the others and on a phrase played from a cache.
    remaining_requests: int | None = Field(default=None, ge=0)
    remaining_tokens: int | None = Field(default=None, ge=0)
    # On the last chunk of a take: the audio came back shorter than its text needs, so the
    # clause was cut short; flagged, not made again (plan 003's decision log).
    cut_short: bool = False

    @field_validator("pcm16")
    @classmethod
    def _whole_samples(cls, value: bytes) -> bytes:
        if len(value) % 2:
            raise ValueError("pcm16 holds whole 16-bit samples: an even number of bytes")
        return value

    @property
    def seconds(self) -> float:
        """How long the chunk plays."""
        return len(self.pcm16) / 2 / self.sample_rate


class TextToSpeech(Protocol):
    """A text-to-speech provider behind the port. `name` identifies it in logs and traces;
    `data_flow` says where the text goes. `language` is one of the declaration's language tags
    (`ar-SA`, `ar`, `en`), each spoken in the model and voice the settings give it."""

    name: str
    data_flow: DataFlow

    def max_chars(self, language: str) -> int | None:
        """The longest text one request of `language` takes, in characters (200 for both of
        Groq's Orpheus models), which the clause splitter honours; None when the provider sets
        no limit."""

    def synthesize(self, text: str, *, language: str) -> AsyncIterator[AudioChunk]:
        """`text` spoken in `language`'s model and voice, chunk by chunk as the provider streams
        it. Raises `ProviderError` on the provider's failure, a text over `max_chars` included;
        a cancel stops it at once and closes its response."""

    async def check_language(self, language: str) -> datetime | None:
        """Return when `language` can be spoken as far as the provider shows without speaking;
        otherwise raise naming what is missing, with a FIX line: ConfigurationError for a
        language the settings give no model or voice, ProviderError when the provider refuses
        the model or the voice (no access). It sends no synthesis request, so a model whose
        terms are not accepted may show only at its first synthesis. It returns the provider's
        time as its answer gave it, aware (UTC), which `t2v doctor` measures this machine's
        clock against (Groq's `Date` header, whole seconds), or None when it gave none."""

    async def aclose(self) -> None:
        """Close what the adapter holds open, its connections; an adapter that holds none
        returns at once. Called once, when the runtime stops."""


@runtime_checkable
class HeldSpeech(Protocol):
    """A text-to-speech that keeps the takes it made (the clause cache): `held` gives the take
    it holds for exactly `text` in `language`, whole, from its own store with no request, or
    None when it holds none (a miss: the clause is then requested as any other). It never
    raises for a miss or a store that fails."""

    async def held(self, text: str, *, language: str) -> AudioChunk | None:
        """The take held for `text` in `language`, or None."""

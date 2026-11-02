"""The phrase cache (the design's 10.4): the fixed phrases a runtime declares at its start (the
greetings, the echo's frames and the notices a call speaks: domain/declaration.py's
`fixed_phrases`), each synthesized once and kept under a folder of
`storage.var_dir`, keyed by a hash of its text, model and voice, so a phrase plays with no
request and a cache hit sends nothing. Built by plan 003's Track B; until then a stub.

Only declared phrases are kept: text built from heard words never reaches the cache, since
caching it would keep call content by default (invariant 8; plan 003's decision log). A file is
written whole, to a temporary name and then renamed, so a stopped write leaves no half phrase.
The session reads a phrase's audio through voice's `PhraseAudio` protocol
(voice/session/io.py), which this class meets.

A phrase longer than the provider's `max_chars` for its language (200 characters for both of
Orpheus's models; a team's greeting or notice has no bound) is still spoken whole, so the runtime
refuses none: `declare` cuts it into clauses with the clause splitter (`split_clauses`,
domain/text/clauses.py) at that `max_chars`, each synthesized and kept as a phrase of its own,
and `audio` returns their takes joined in order, as one chunk. A phrase within `max_chars` is
one request, never cut. Takes of one phrase share their sample rate, read from each take; two
rates fail `declare` with a ProviderError (`server_error`). Track B's tests, beyond the plan's:
with a fake text-to-speech whose `max_chars` is 200, a 250-character phrase of two sentences
sends two requests, each within 200, and its `audio` is the first take then the second; a phrase
within 200 that holds a comma sends one.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path

from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.settings.tts import LanguageTag, TtsVoice
from t2_agentic_voice.domain.ports.text_to_speech import AudioChunk, TextToSpeech

_STUB = "the phrase cache is built by plan 003's Track B"


class PhraseCache:
    """The fixed phrases of one runtime, synthesized through `tts` in each language's model and
    voice (`voices`, the settings' `tts.languages`, which key each file) and kept in `folder`.
    Built cheaply, with no IO; `declare` does the IO."""

    def __init__(
        self, tts: TextToSpeech, *, folder: Path, voices: Mapping[LanguageTag, TtsVoice]
    ) -> None:
        raise NotImplementedError(_STUB)

    @classmethod
    def from_settings(
        cls, settings: VoiceSettings, tts: TextToSpeech, *, folder: Path
    ) -> PhraseCache:
        """The cache the settings describe: `tts.languages`' voices, and `tts.cache_phrases`,
        which says whether the phrases are kept in `folder` between runs."""
        raise NotImplementedError(_STUB)

    async def declare(self, phrases: Iterable[tuple[str, LanguageTag]]) -> int:
        """Have each phrase's audio at hand, in its language: read from its file, or
        synthesized once and written; then kept in memory. Called once, at the runtime's start,
        the only time the cache asks the provider; returns how many requests it sent, one for
        each phrase it synthesized within `max_chars` and one for each clause of a longer one."""
        raise NotImplementedError(_STUB)

    def audio(self, text: str, *, language: LanguageTag) -> AudioChunk:
        """A declared phrase's audio, whole, from memory, with no request; LookupError for any
        text not declared."""
        raise NotImplementedError(_STUB)

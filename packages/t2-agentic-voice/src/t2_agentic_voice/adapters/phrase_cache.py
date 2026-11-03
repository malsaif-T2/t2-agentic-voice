"""The phrase cache (the design's 10.4): the fixed phrases of the runtime's agent (the greetings,
the echo's frames and the notices a call speaks: domain/fixed_phrases.py), each synthesized once
and kept under a folder of `storage.var_dir`, so a phrase plays with no request and a cache hit
sends nothing. Built by plan 003's Track B; until then a stub. Public through the `stores`
facade, so a timing run builds the phrase audio its file-fed calls play as the runtime does
(testing's `echo_timings` takes it, since `testing` never imports adapters).

Only declared phrases are kept: text built from heard words never reaches the cache, since
caching it would keep call content by default (invariant 8; plan 003's decision log). A file is
written whole, to a temporary name and then renamed, so a stopped write leaves no half phrase.
The session reads a phrase's audio through voice's `PhraseAudio` protocol
(voice/session/io.py), which this class meets.

**What is sent.** A phrase is said as the agent's pronunciation map says it: `declare` applies
`pronounce` (domain/text/pronounce.py) with `agent.pronounce` in the phrase's language, then
makes the provider's text of that (`provider_text`, domain/text/invisible.py: each no-break
space a space, each joiner and direction mark dropped), and sends only that text. A phrase is
kept, and `audio` finds it, under the phrase as written, which captions show; its file is keyed
by a hash of the text sent, the model and the voice, so a changed map or phrase is synthesized
anew.

**Packing.** A phrase whose text sent is longer than the provider's `max_chars` for its language
(200 characters for both of Orpheus's models; a team's greeting or notice has no bound) is still
spoken whole, so the runtime refuses none: `declare` cuts that text into clauses with the clause
splitter (`split_clauses`, domain/text/clauses.py) at that `max_chars` and packs them greedily,
in order, into requests of at most `max_chars` characters, the clauses of a request joined by a
space and a request ended only where its next clause would pass `max_chars`. So a phrase of n
characters costs about n / `max_chars` requests, the map applied first, and no request passes
`max_chars`; a phrase within `max_chars` is one request, never cut. `audio` returns the takes
joined in order, as one chunk. Takes of one phrase share their sample rate, read from each take;
two rates fail `declare` with a ProviderError (`server_error`).

**Pacing.** At start the requests go one at a time, each sent once the one before has answered.
A request the provider refuses as `rate_limited` waits the delay it asked for (`retry_after_s`,
at most `MAX_RETRY_DELAY_S`, and that bound when it gave none) and is sent again, at most
`RETRIES` times; its next refusal fails `declare` with a ProviderError (`rate_limited`) whose
details name the phrase's kind and language (`{"phrase": "greeting", "language": "en"}`, from
`FixedPhrase`), never its text. Any other ProviderError fails `declare` at once. Each delay
goes through `_sleep` (`asyncio.sleep` unless a test gives its own).

Track B's tests, beyond the plan's: with `FakeTextToSpeech(limit=200)`
(tests/t2_agentic_voice/fakes.py), a 204-character greeting of eight sentences sends two
requests, each within 200, and its `audio` is the two takes joined; a phrase within 200 that
holds a comma sends one; a 429 and then a success waits once, the delay asked for, and sends the
request once more; three 429s fail with the phrase's kind and language and no text of it; with
`pronounce={"LT-": {"en": "L T"}}`, the request says "L T" while `audio` finds the phrase as
written, and a map that takes a phrase past 200 sends two requests, each within 200; a Saudi
greeting holding a right-to-left mark and a no-break space is sent with neither, the space a
plain one, and `audio` finds the greeting as written.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping
from pathlib import Path

from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.settings.tts import LanguageTag, TtsVoice
from t2_agentic_voice.domain.declaration import VoiceAgent
from t2_agentic_voice.domain.ports.text_to_speech import AudioChunk, TextToSpeech

_STUB = "the phrase cache is built by plan 003's Track B"

# The longest a rate-limited request waits before it is sent again, in seconds, whatever delay
# the provider asked for; and how many times one request is sent again (plan 003's decision log).
MAX_RETRY_DELAY_S = 60.0
RETRIES = 2


class PhraseCache:
    """The fixed phrases of one runtime, synthesized through `tts` in each language's model and
    voice (`voices`, the settings' `tts.languages`, which key each file) and kept in `folder`.
    Built cheaply, with no IO; `declare` does the IO."""

    def __init__(
        self,
        tts: TextToSpeech,
        *,
        folder: Path,
        voices: Mapping[LanguageTag, TtsVoice],
        _sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        raise NotImplementedError(_STUB)

    @classmethod
    def from_settings(
        cls, settings: VoiceSettings, tts: TextToSpeech, *, folder: Path
    ) -> PhraseCache:
        """The cache the settings describe: `tts.languages`' voices, and `tts.cache_phrases`,
        which says whether the phrases are kept in `folder` between runs."""
        raise NotImplementedError(_STUB)

    async def declare(self, agent: VoiceAgent) -> int:
        """Have each of `agent`'s fixed phrases (domain/fixed_phrases.py) at hand in its
        language, said through `agent.pronounce`: read from its file, or synthesized once and
        written; then kept in memory. Called once, at the runtime's start or before a timing
        run, the only time the cache asks the provider; returns how many requests it sent, one
        for each request it packed and none for a phrase its file held: what the fixed phrases
        cost the provider's budget (run T's, for a timing run)."""
        raise NotImplementedError(_STUB)

    def audio(self, text: str, *, language: LanguageTag) -> AudioChunk:
        """A declared phrase's audio, whole, from memory, with no request; LookupError for any
        text not declared."""
        raise NotImplementedError(_STUB)

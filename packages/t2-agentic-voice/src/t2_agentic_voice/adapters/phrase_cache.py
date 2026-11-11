"""The phrase cache (the design's 10.4): the fixed phrases of the runtime's agent (the greetings,
the echo's frames and the notices a call speaks: domain/fixed_phrases.py), each synthesized once
and kept under a folder of `storage.var_dir`, so a phrase plays with no request and a cache hit
sends nothing. Public through the `stores` facade, so a timing run builds the phrase audio its
file-fed calls play as the runtime does (testing's `echo_timings` takes it, since `testing`
never imports adapters).

Only declared phrases are kept here: text built from heard words never reaches this cache
(invariant 8; plan 003's decision log). The clauses a talker speaks are kept by the clause cache
(adapters/clause_cache.py), never the echo's words. A file is written whole, to a temporary name
and then renamed (adapters/wav_files.py), so a stopped write leaves no half phrase. The session
reads a phrase's audio through voice's `PhraseAudio` protocol (voice/session/io.py), which this
class meets.

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
`FixedPhrase`), never its text. Any other ProviderError fails `declare` at once, its details
naming the phrase the same way. Each delay goes through `_sleep` (`asyncio.sleep` unless a test
gives its own). Every request sent counts in what `declare` returns, one refused and sent again
included, since each is a request the provider's limits saw.

**Files.** Each phrase is a WAV file, mono 16-bit at its take's sample rate, named by its key
(`phrase_key`) in `folder`; a file that cannot be read as one is synthesized anew and replaced.
A phrase is kept only while `keep_files` holds (the settings' `tts.cache_phrases`): without it,
each start synthesizes every phrase again and writes nothing. Two phrases with the same key (both
Arabic presets share their frame, model and voice) are synthesized once. A take that came back
cut short is kept in memory for this run, its flag on its audio, which the session carries to
`ClausePlayed` (plan 003's decision log, 2026-11-03), but is never written: a cut take kept on
disk would cut that phrase in every call until someone deleted its file, so the next start asks
for it again.

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
import hashlib
from collections.abc import Awaitable, Callable, Mapping
from pathlib import Path

from pydantic import JsonValue

from t2_agentic_voice.adapters.wav_files import take_of, wav_of, write_whole
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.errors import ConfigurationError, ProviderError
from t2_agentic_voice.core.settings.base import setting_name
from t2_agentic_voice.core.settings.tts import LanguageTag, TtsVoice
from t2_agentic_voice.domain.declaration import VoiceAgent
from t2_agentic_voice.domain.fixed_phrases import FixedPhrase, fixed_phrases
from t2_agentic_voice.domain.ports.text_to_speech import AudioChunk, TextToSpeech
from t2_agentic_voice.domain.text.clauses import split_clauses
from t2_agentic_voice.domain.text.invisible import provider_text
from t2_agentic_voice.domain.text.pronounce import pronounce

# The longest a rate-limited request waits before it is sent again, in seconds, whatever delay
# the provider asked for; and how many times one request is sent again (plan 003's decision log).
MAX_RETRY_DELAY_S = 60.0
RETRIES = 2
# Hashed into every phrase's key beside its text, model and voice: the files' format, so a
# change to how a file is written makes new files rather than reading old ones wrong.
_FORMAT = "t2v-phrase-wav-1"


class PhraseCache:
    """The fixed phrases of one runtime, synthesized through `tts` in each language's model and
    voice (`voices`, the settings' `tts.languages`, which key each file) and kept in `folder`
    while `keep_files` holds. Built cheaply, with no IO; `declare` does the IO."""

    def __init__(
        self,
        tts: TextToSpeech,
        *,
        folder: Path,
        voices: Mapping[LanguageTag, TtsVoice],
        keep_files: bool = True,
        _sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._tts = tts
        self._folder = folder
        self._voices = voices
        self._keep_files = keep_files
        self._sleep = _sleep
        # Each declared phrase's audio, by its language and the phrase as written.
        self._held: dict[tuple[str, str], AudioChunk] = {}

    @classmethod
    def from_settings(
        cls, settings: VoiceSettings, tts: TextToSpeech, *, folder: Path
    ) -> PhraseCache:
        """The cache the settings describe: `tts.languages`' voices, and `tts.cache_phrases`,
        which says whether the phrases are kept in `folder` between runs."""
        return cls(
            tts,
            folder=folder,
            voices=settings.tts.languages,
            keep_files=settings.tts.cache_phrases,
        )

    async def declare(self, agent: VoiceAgent) -> int:
        """Have each of `agent`'s fixed phrases (domain/fixed_phrases.py) at hand in its
        language, said through `agent.pronounce`: read from its file, or synthesized once and
        written; then kept in memory. Called once, at the runtime's start or before a timing
        run, the only time the cache asks the provider; returns how many requests it sent, one
        for each request it packed and none for a phrase its file held: what the fixed phrases
        cost the provider's budget (run T's, for a timing run). ConfigurationError for a
        language `voices` gives no model or voice."""
        sent = 0
        made: dict[str, AudioChunk] = {}  # by key: a phrase two languages share is made once
        for phrase in fixed_phrases(agent):
            said = provider_text(pronounce(phrase.text, agent.pronounce, language=phrase.language))
            key = phrase_key(said, self._voice(phrase.language))
            audio = made.get(key)
            if audio is None:
                audio = self._read(key)
            if audio is None:
                audio, requests = await self._synthesize(said, phrase)
                sent += requests
                self._write(key, audio)
            made[key] = self._held[phrase.language, phrase.text] = audio
        return sent

    def audio(self, text: str, *, language: LanguageTag) -> AudioChunk:
        """A declared phrase's audio, whole, from memory, with no request; LookupError for any
        text not declared, whose message holds no text."""
        held = self._held.get((language, text))
        if held is None:
            raise LookupError(
                f"No fixed phrase of that text was declared in {language}. FIX: speak a "
                "phrase the agent declares (its greeting, its echo frame or a notice)."
            )
        return held

    def _voice(self, language: LanguageTag) -> TtsVoice:
        voice = self._voices.get(language)
        if voice is None:
            setting = setting_name("tts", "languages")
            raise ConfigurationError(
                f"The phrase cache has no model or voice for the language {language}. FIX: give "
                f"{setting} a model and a voice for it.",
                details={"setting": setting},
            )
        return voice

    async def _synthesize(self, said: str, phrase: FixedPhrase) -> tuple[AudioChunk, int]:
        """`said` spoken in `phrase`'s language, in as few requests as fit (above): its takes
        joined, flagged cut short if any take was, and how many requests that sent."""
        pcm, rates, cut, sent = bytearray(), set[int](), False, 0
        for text in packed(said, self._tts.max_chars(phrase.language)):
            chunks, attempts = await self._take(text, phrase)
            sent += attempts
            pcm += b"".join(chunk.pcm16 for chunk in chunks)
            rates |= {chunk.sample_rate for chunk in chunks}
            cut = cut or any(chunk.cut_short for chunk in chunks)
        if len(rates) != 1:
            error = "no_audio" if not rates else "sample_rates_differ"
            raise ProviderError("server_error", False, details=_named({"error": error}, phrase))
        return AudioChunk(pcm16=bytes(pcm), sample_rate=rates.pop(), cut_short=cut), sent

    async def _take(self, text: str, phrase: FixedPhrase) -> tuple[list[AudioChunk], int]:
        """One request's take, sent again after each refusal as `rate_limited`, at most
        `RETRIES` times (above), and how many requests that sent."""
        for attempt in range(RETRIES + 1):
            try:
                take = [
                    chunk async for chunk in self._tts.synthesize(text, language=phrase.language)
                ]
            except ProviderError as error:
                refused = error
            else:
                return take, attempt + 1
            if refused.kind != "rate_limited" or attempt == RETRIES:
                break
            asked = refused.retry_after_s
            await self._sleep(MAX_RETRY_DELAY_S if asked is None else min(asked, MAX_RETRY_DELAY_S))
        raise ProviderError(
            refused.kind,
            refused.retryable,
            refused.retry_after_s,
            details=_named(dict(refused.details), phrase),
        ) from None

    def _path(self, key: str) -> Path:
        return self._folder / f"{key}.wav"

    def _read(self, key: str) -> AudioChunk | None:
        """The phrase's audio from its file, or None: with no file, with files not kept, or
        with a file that cannot be read as the cache writes one (it is made anew)."""
        if not self._keep_files:
            return None
        try:
            data = self._path(key).read_bytes()
        except FileNotFoundError:
            return None
        return take_of(data)

    def _write(self, key: str, audio: AudioChunk) -> None:
        """Write the phrase's file whole, to a temporary name and then renamed (above); nothing
        for a take cut short, or with files not kept."""
        if not self._keep_files or audio.cut_short:
            return
        self._folder.mkdir(parents=True, exist_ok=True)
        write_whole(self._path(key), wav_of(audio))


def phrase_key(said: str, voice: TtsVoice) -> str:
    """The key of a phrase's file: a hash of the text sent for it, the model and the voice (the
    design's 10.4), and the files' format."""
    seed = "\n".join((_FORMAT, voice.model, voice.voice, said))
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:32]


def packed(text: str, max_chars: int | None) -> list[str]:
    """`text` as the requests that say it (above): itself when it fits `max_chars`, else its
    clauses packed greedily, in order, each request at most `max_chars` characters."""
    if max_chars is None or len(text) <= max_chars:
        return [text]
    requests: list[str] = []
    for clause in split_clauses(text, max_chars=max_chars):
        joined = f"{requests[-1]} {clause}" if requests else clause
        if requests and len(joined) <= max_chars:
            requests[-1] = joined
        else:
            requests.append(clause)
    return requests


def _named(details: dict[str, JsonValue], phrase: FixedPhrase) -> dict[str, JsonValue]:
    """`details` naming the phrase by its kind and language, never its text."""
    return details | {"phrase": phrase.kind, "language": phrase.language}

"""The clause cache (the design's 10.4; plan 007, by the owner's rulings of 2026-11-10 amending
D-033): every clause the agent speaks in a call with a talker kept on disk by its exact text, so
the same clause in the same voice plays again with no request. It asks no consent: what it keeps
is what the agent produced. The runtime builds it only for a talker agent's calls (api/voices.py),
so the echo's words said back never reach it.

`ClauseCache` is a `TextToSpeech` that wraps another and meets `HeldSpeech`: the text-to-speech
bridge asks `held` before it requests a clause. Built with no IO; `open` reads its folder
(clause_files.py); `aclose` lets its writer finish, at most `CLOSE_TIMEOUT_S`, drops the rest, and
never closes the adapter it wraps (whoever built that closes it). Public through `stores`.

- **The key:** a SHA-256 of the files' format, the wrapped adapter's `name`, the language, its
  model and voice, `tts.trim_silence`, and the text exactly as the provider is sent it (after the
  speaking rules, the pronunciation map and `provider_text`), cut to 32 hex characters.
- **Keeping:** `synthesize` passes each chunk on at once, unchanged, keeping a copy; only once the
  stream has ended whole is the take queued for the writer: one rate, some audio, none cut short.
  A take that raised, came back cut short, gave no audio or was stopped is never kept.
  `synthesize` never serves a held take.
- **Writing:** one writer task, its queue at most `WRITES_QUEUED` (when full, the take is
  dropped); each write in a thread, whole (wav_files.py's `write_whole`). Past `max_mb` it
  removes the takes played longest ago until under `TRIM_TO` of it; a file the system will not
  let go of stays for the next round.
- **Reading:** a key the index holds is read in a thread within `READ_TIMEOUT_S`, else it is a
  miss and the clause is requested as today; a file that is no take is a miss, counted, its entry
  dropped and its file removed by the writer. `held` never raises.
- **The socket** (D-121): `streams` and `open_stream` pass on the wrapped adapter's
  (`StreamingTextToSpeech`); a clause spoken on a call's socket is never kept: it was
  spoken within its reply's turn, after the clauses before it.
- **Logs** never hold a text or a key (a key is a hash of a short text that can be guessed back,
  GP-19): `clause_cache_opened`, `_closed` and `_trimmed` at INFO; at WARNING
  `clause_unreadable`, and `clause_write_failed` and `clause_lookup_failed` (a lookup's own bug,
  the clause then requested) with the error's type; and `clause_writer_failed` at ERROR, with the
  error's type, the writer going on.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import time
from collections.abc import AsyncIterator, Mapping
from datetime import datetime
from pathlib import Path

from t2_agentic_voice.adapters.clause_counts import ClauseCounts, NotKept, Tally
from t2_agentic_voice.adapters.clause_files import MAX_TAKE_BYTES, ClauseFiles
from t2_agentic_voice.adapters.wav_files import wav_of, write_whole
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.logging import get_logger
from t2_agentic_voice.core.settings.tts import LanguageTag, TtsVoice
from t2_agentic_voice.domain.ports.speech_stream import SpeechStream, StreamingTextToSpeech
from t2_agentic_voice.domain.ports.text_to_speech import AudioChunk, TextToSpeech

log = get_logger(__name__)

# The agent's numbers (plan 007): the takes queued for the writer, the longest a take is read
# before it is a miss, the longest the close waits for the writer; and what the bound trims to.
WRITES_QUEUED = 64
READ_TIMEOUT_S = 0.1
CLOSE_TIMEOUT_S = 5.0
TRIM_TO = 0.9
_MB = 1_000_000
_FORMAT = "t2v-clause-wav-1"  # in every key: a change to the files' format makes new keys


class ClauseCache:
    """Every clause `tts` says kept in `folder` (the module's docstring), keyed with `voices`
    (the settings' `tts.languages`) and `trim_silence`, at most `max_mb` megabytes."""

    def __init__(
        self,
        tts: TextToSpeech,
        *,
        folder: Path,
        voices: Mapping[LanguageTag, TtsVoice],
        trim_silence: bool,
        max_mb: int,
    ) -> None:
        self._tts = tts
        self.name, self.data_flow = tts.name, tts.data_flow
        self._files = ClauseFiles(folder)
        self._voices: dict[str, TtsVoice] = dict(voices.items())
        self._trim, self._max_bytes = trim_silence, max_mb * _MB
        self._queue: asyncio.Queue[tuple[str, AudioChunk | None]] = asyncio.Queue(WRITES_QUEUED)
        self._writer: asyncio.Task[None] | None = None
        self._tally = Tally()

    @classmethod
    def from_settings(
        cls, settings: VoiceSettings, tts: TextToSpeech, *, folder: Path
    ) -> ClauseCache:
        """The cache the settings describe over `tts`: `tts.languages`, `tts.trim_silence` and
        `tts.clause_cache_mb`."""
        group = settings.tts
        return cls(
            tts,
            folder=folder,
            voices=group.languages,
            trim_silence=group.trim_silence,
            max_mb=group.clause_cache_mb,
        )

    def max_chars(self, language: str) -> int | None:
        return self._tts.max_chars(language)

    async def check_language(self, language: str) -> datetime | None:
        return await self._tts.check_language(language)

    async def synthesize(self, text: str, *, language: str) -> AsyncIterator[AudioChunk]:
        """`text` through the wrapped adapter, each chunk passed on as it came; the take kept
        once it ended whole, after the loop, never in the `finally`."""
        take: list[AudioChunk] = []
        why: NotKept | None = "stopped"
        stream = self._tts.synthesize(text, language=language)
        try:
            async for chunk in stream:
                take.append(chunk)
                yield chunk
            why = None
        except Exception:
            why = "failed"
            raise
        finally:  # a cancel or an early close closes the provider's stream too
            if why is not None and self._key(text, language) is not None:
                self._tally.why(why)
            close = getattr(stream, "aclose", None)
            if close is not None:
                await close()
        self._keep(text, language, take)

    async def held(self, text: str, *, language: str) -> AudioChunk | None:
        """The take held for exactly `text` in `language`, read from its file; None for a miss,
        which a disk that fails is too."""
        started = time.perf_counter()
        try:
            found = await self._looked_up(text, language)
        except Exception as error:  # a bug of its own still leaves the clause to the request
            log.warning("clause_lookup_failed", error=type(error).__name__)
            found = None
        self._tally.looked_up(time.perf_counter() - started, hit=found is not None)
        return found

    def streams(self, language: str) -> bool:
        """Whether the adapter it wraps speaks `language` on its socket (D-121)."""
        tts = self._tts
        return isinstance(tts, StreamingTextToSpeech) and tts.streams(language)

    def open_stream(self, *, language: str) -> SpeechStream:
        """The wrapped adapter's session for one call, once `streams` said it has one."""
        tts = self._tts
        if not isinstance(tts, StreamingTextToSpeech):
            raise TypeError("the text-to-speech the clause cache wraps has no socket")
        return tts.open_stream(language=language)

    async def open(self) -> None:
        """Read the folder (clause_files.py's `scan`) and start the writer."""
        if self._writer is not None:
            return
        entries, parts = await asyncio.to_thread(self._files.scan)
        self._files.opened(entries)
        self._writer = asyncio.create_task(self._write_all(), name="t2v-clause-cache-writer")
        files = self._files
        log.info(
            "clause_cache_opened", entries=len(entries), megabytes=files.megabytes, parts=parts
        )

    async def clear(self) -> None:
        """Remove every take it keeps (its own files, in its own folder), what its writer had
        been given written first, and reset its counts."""
        await self._written()
        await asyncio.to_thread(self._files.remove_takes)
        self._files.opened([])
        self._tally = Tally()

    def counts(self) -> ClauseCounts:
        """Its counts so far (clause_counts.py's `ClauseCounts`)."""
        files = self._files
        return self._tally.counts(entries=len(files.index), megabytes=files.megabytes)

    def taken(self) -> ClauseCounts:
        """Its counts so far, then reset; the entries and megabytes it holds stay."""
        counts = self.counts()
        self._tally = Tally()
        return counts

    async def aclose(self) -> None:
        """Keep and hold no more; let the writer finish what it was given, at most
        `CLOSE_TIMEOUT_S`, and drop the rest. The wrapped adapter stays open."""
        writer = self._writer
        if writer is None:
            return
        await self._written()
        self._writer, dropped = None, self._queue.qsize()
        writer.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await writer
        files = self._files
        entries, megabytes = len(files.index), files.megabytes
        log.info("clause_cache_closed", entries=entries, megabytes=megabytes, dropped=dropped)

    def _key(self, text: str, language: str) -> str | None:
        """The key of `text` sent in `language`; None for a language with no model or voice,
        whose clauses are never kept."""
        voice = self._voices.get(language)
        if voice is None:
            return None
        trim = "trimmed" if self._trim else "as-is"
        seed = [_FORMAT, self._tts.name, language, voice.model, voice.voice, trim, text]
        return hashlib.sha256(json.dumps(seed).encode()).hexdigest()[:32]

    def _keep(self, text: str, language: str, take: list[AudioChunk]) -> None:
        """Queue a take that ended whole for the writer, or count why it is not kept."""
        key = self._key(text, language)
        if key is None:
            return
        rates = {chunk.sample_rate for chunk in take if chunk.pcm16}
        pcm = b"".join(chunk.pcm16 for chunk in take)
        why: NotKept | None = None
        if any(chunk.cut_short for chunk in take):
            why = "cut_short"
        elif not pcm:
            why = "no_audio"
        elif len(rates) != 1:
            why = "sample_rates"
        elif len(pcm) + 44 > MAX_TAKE_BYTES:  # 44: a WAV file's header
            why = "too_large"
        elif self._writer is None:
            why = "closed"
        elif key in self._files.index:
            why = "held"
        else:
            try:
                self._queue.put_nowait((key, AudioChunk(pcm16=pcm, sample_rate=rates.pop())))
            except asyncio.QueueFull:
                why = "queue_full"
        if why is not None:
            self._tally.why(why)

    async def _looked_up(self, text: str, language: str) -> AudioChunk | None:
        key, files = self._key(text, language), self._files
        entry = None if key is None or self._writer is None else files.index.get(key)
        if key is None or entry is None:
            return None
        try:
            async with asyncio.timeout(READ_TIMEOUT_S):
                found = await asyncio.to_thread(files.read, key)
        except TimeoutError:  # slow: a miss, its entry kept
            return None
        except FileNotFoundError:  # gone: a miss, its entry dropped
            files.drop(key, entry)
            return None
        except OSError:  # held by another for now: a miss, its entry kept
            return None
        if found is None:
            self._tally.unreadable += 1
            files.drop(key, entry)
            with contextlib.suppress(asyncio.QueueFull):
                self._queue.put_nowait((key, None))  # its file removed by the writer
            log.warning("clause_unreadable")
            return None
        files.played(key, entry)
        return found

    async def _written(self) -> None:
        """Wait until the writer has done what it was given, at most `CLOSE_TIMEOUT_S`."""
        if self._writer is not None:
            with contextlib.suppress(TimeoutError):
                async with asyncio.timeout(CLOSE_TIMEOUT_S):
                    await self._queue.join()

    async def _write_all(self) -> None:
        """The writer: each take queued written (a `None` take: a file that was no take
        removed), the bound kept after each; a failure logged by its type, the writer going on."""
        await self._trimmed()
        while True:
            key, audio = await self._queue.get()
            try:
                if audio is None and key not in self._files.index:
                    await asyncio.to_thread(self._files.remove, key)
                elif audio is not None:
                    await self._write(key, audio)
            except Exception as error:
                log.error("clause_writer_failed", error=type(error).__name__)
            finally:
                self._queue.task_done()

    async def _write(self, key: str, audio: AudioChunk) -> None:
        if key in self._files.index:  # two takes of one clause at once: the first is kept
            self._tally.why("held")
            return
        data = wav_of(audio)
        try:
            await asyncio.to_thread(write_whole, self._files.path(key), data)
        except OSError as error:
            self._tally.write_failures += 1
            log.warning("clause_write_failed", error=type(error).__name__)
            return
        self._files.add(key, len(data))
        self._tally.kept += 1
        await self._trimmed()

    async def _trimmed(self) -> None:
        """Past the bound, remove the takes played longest ago until under `TRIM_TO` of it."""
        files = self._files
        if files.bytes <= self._max_bytes:
            return
        removed = 0
        for key, entry in list(files.index.items()):
            if files.bytes <= self._max_bytes * TRIM_TO:
                break
            if await asyncio.to_thread(files.remove, key):  # else it stays for the next round
                files.drop(key, entry)
                removed += 1
        self._tally.removed += removed
        entries, megabytes = len(files.index), files.megabytes
        log.info("clause_cache_trimmed", removed=removed, entries=entries, megabytes=megabytes)

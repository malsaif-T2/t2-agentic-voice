"""The clause cache (adapters/clause_cache.py, plan 007): every clause said through it kept on
disk by its exact text, its language, its voice, its adapter and the trimming, and given back
only for exactly that (`held`); a take kept only once it ended whole; two takes of one clause,
a slow read and a file gone; its counts; and nothing of a text or a key in a log line. Its
files, its bound, a disk that refuses, its close and `clear`: test_clause_cache_files.py. On
the fakes' text-to-speech, in a test's own folder."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
from t2_agentic_voice.adapters import clause_cache
from t2_agentic_voice.adapters.clause_counts import ClauseCounts
from t2_agentic_voice.adapters.wav_files import write_whole
from t2_agentic_voice.core.errors import ProviderError
from t2_agentic_voice.core.settings.tts import LanguageTag, TtsVoice
from t2_agentic_voice.domain.ports.text_to_speech import AudioChunk, HeldSpeech

from tests.leaks import holding, shown
from tests.t2_agentic_voice.adapters.clause_support import (
    TEXT,
    VOICES,
    OddSpeech,
    OtherSpeech,
    cache_of,
    kept,
    said,
    take,
    takes_in,
)
from tests.t2_agentic_voice.fakes import FakeTextToSpeech

ARABIC = "طلبك مفتوح، وبنتصل عليك اليوم."


def test_it_is_a_text_to_speech_that_holds_speech_and_wraps_another(tmp_path: Path) -> None:
    fake = FakeTextToSpeech(limit=150)
    cache = cache_of(fake, tmp_path / "clauses")
    assert isinstance(cache, HeldSpeech) and not isinstance(fake, HeldSpeech)
    assert (cache.name, cache.data_flow, cache.max_chars("en")) == ("fake", fake.data_flow, 150)
    assert asyncio.run(cache.check_language("en")) is None and fake.checked == ["en"]
    assert not (tmp_path / "clauses").exists()  # built with no IO


def test_a_take_is_given_back_for_its_own_text_in_a_later_cache(tmp_path: Path) -> None:
    """Each chunk passes on as it came; the take is kept whole and given back, with no request,
    by a later cache over the same folder for the same text, language, voice and adapter."""
    fake = FakeTextToSpeech(sample_rate=22_050)

    async def scene() -> tuple[list[AudioChunk], AudioChunk | None]:
        first = cache_of(fake, tmp_path)
        await first.open()
        chunks = await kept(first)
        await first.aclose()
        later = cache_of(FakeTextToSpeech(sample_rate=22_050), tmp_path)
        await later.open()
        found = await later.held(TEXT, language="en")
        await later.aclose()
        return chunks, found

    chunks, found = asyncio.run(scene())
    direct = asyncio.run(_direct(FakeTextToSpeech(sample_rate=22_050), TEXT))
    assert chunks == direct  # unchanged, chunk by chunk
    assert found is not None and (found.pcm16, found.sample_rate) == (take(TEXT, fake), 22_050)
    assert (found.cut_short, found.remaining_requests) == (False, None)
    assert fake.calls == [(TEXT, "en")]


async def _direct(fake: FakeTextToSpeech, text: str) -> list[AudioChunk]:
    return [chunk async for chunk in fake.synthesize(text, language="en")]


@pytest.mark.parametrize(
    ("text", "language"),
    [
        (TEXT + ".", "en"),  # one character more
        (TEXT.replace(" ", "  ", 1), "en"),  # a space more
        (TEXT.rstrip("."), "en"),  # one character less
        ("Ticket 4521 is open.", "en"),  # one digit changed, below
        (ARABIC, "ar"),  # the other Arabic preset, the same model and voice
    ],
)
def test_a_take_is_never_given_for_another_text_or_language(
    text: str, language: str, tmp_path: Path
) -> None:
    async def scene() -> tuple[AudioChunk | None, AudioChunk | None]:
        cache = cache_of(FakeTextToSpeech(), tmp_path)
        await cache.open()
        await kept(cache, TEXT)
        await kept(cache, "Ticket 4522 is open.")
        await kept(cache, ARABIC, "ar-SA")
        other = await cache.held(text, language=language)
        own = await cache.held(TEXT, language="en")
        await cache.aclose()
        return other, own

    other, own = asyncio.run(scene())
    assert other is None and own is not None


ENGLISH = VOICES["en"]
VOICE = {**VOICES, "en": TtsVoice(model=ENGLISH.model, voice="tara")}
MODEL = {**VOICES, "en": TtsVoice(model=VOICES["ar"].model, voice=ENGLISH.voice)}


@pytest.mark.parametrize(
    ("voices", "trim_silence", "adapter"),
    [(VOICE, False, False), (MODEL, False, False), (None, True, False), (None, False, True)],
    ids=["another-voice", "another-model", "trimmed", "another-adapter"],
)
def test_a_take_is_never_given_for_another_voice_model_trimming_or_adapter(
    voices: dict[LanguageTag, TtsVoice] | None, trim_silence: bool, adapter: bool, tmp_path: Path
) -> None:
    async def scene() -> tuple[AudioChunk | None, AudioChunk | None]:
        first = cache_of(FakeTextToSpeech(), tmp_path)
        await first.open()
        await kept(first)
        await first.aclose()
        fake = OtherSpeech() if adapter else FakeTextToSpeech()
        other = cache_of(fake, tmp_path, voices=voices, trim_silence=trim_silence)
        await other.open()
        found = await other.held(TEXT, language="en")
        await other.aclose()
        same = cache_of(FakeTextToSpeech(), tmp_path)
        await same.open()
        own = await same.held(TEXT, language="en")
        await same.aclose()
        return found, own

    found, own = asyncio.run(scene())
    assert found is None and own is not None


@pytest.mark.parametrize(
    ("text", "why"),
    [("half", "failed"), ("cut", "cut_short"), ("two rates", "sample_rates"), ("", "no_audio")],
)
def test_a_take_that_is_not_whole_is_never_kept(text: str, why: str, tmp_path: Path) -> None:
    """A take that raised mid-stream, came back cut short, came at two rates or gave no audio
    is passed on as it came and never kept; no `.part` is left."""
    fake = OddSpeech(cut_short={"cut"})

    async def scene() -> tuple[ClauseCounts, AudioChunk | None]:
        cache = cache_of(fake, tmp_path)
        await cache.open()
        if why == "failed":
            with pytest.raises(ProviderError):
                await said(cache, text)
        else:
            await said(cache, text)
        await cache._written()
        found = await cache.held(text, language="en")
        counts = cache.counts()
        await cache.aclose()
        return counts, found

    counts, found = asyncio.run(scene())
    assert found is None and counts.kept == 0 and counts.not_kept == {why: 1}
    assert list(tmp_path.iterdir()) == []


def test_a_take_closed_after_its_first_chunk_or_cancelled_is_never_kept(tmp_path: Path) -> None:
    fake = FakeTextToSpeech(delay_s=0.0)

    async def scene() -> ClauseCounts:
        cache = cache_of(fake, tmp_path)
        await cache.open()
        stream = cache.synthesize(TEXT, language="en")
        assert isinstance(stream, AsyncGenerator)
        await anext(stream)
        await stream.aclose()  # the bridge stopped reading it
        slow = cache_of(FakeTextToSpeech(delay_s=5.0), tmp_path)
        await slow.open()
        task = asyncio.create_task(said(slow))
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        await cache._written()
        counts = cache.counts()
        assert slow.counts().not_kept == {"stopped": 1}
        await slow.aclose()
        await cache.aclose()
        return counts

    counts = asyncio.run(scene())
    assert (counts.kept, counts.not_kept) == (0, {"stopped": 1})
    assert list(tmp_path.iterdir()) == []


def test_two_takes_of_one_clause_at_once_keep_one_file(tmp_path: Path) -> None:
    async def scene() -> ClauseCounts:
        cache = cache_of(FakeTextToSpeech(), tmp_path)
        await cache.open()
        await asyncio.gather(said(cache), said(cache))
        await cache._written()
        assert await cache.held(TEXT, language="en") is not None
        counts = cache.counts()
        await cache.aclose()
        return counts

    counts = asyncio.run(scene())
    assert (counts.kept, counts.not_kept, counts.entries) == (1, {"held": 1}, 1)
    assert len(takes_in(tmp_path)) == 1 and len(list(tmp_path.iterdir())) == 1


def test_a_slow_read_is_a_miss_its_entry_kept_and_a_file_gone_is_dropped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A read past 100 ms is a miss, the clause then requested as today, and its entry stays;
    a file someone removed is a miss, its entry dropped and the clause kept anew."""
    fake = FakeTextToSpeech()

    async def scene() -> None:
        cache = cache_of(fake, tmp_path)
        await cache.open()
        await kept(cache)
        read = cache._files.read

        def slow(key: str) -> AudioChunk | None:
            time.sleep(0.4)
            return read(key)

        monkeypatch.setattr(cache._files, "read", slow)
        started = time.perf_counter()
        assert await cache.held(TEXT, language="en") is None
        assert time.perf_counter() - started < 0.35
        monkeypatch.setattr(cache._files, "read", read)
        assert await cache.held(TEXT, language="en") is not None  # its entry stayed
        (path,) = takes_in(tmp_path)
        path.unlink()
        assert await cache.held(TEXT, language="en") is None
        assert cache.counts().entries == 0
        await kept(cache)
        assert await cache.held(TEXT, language="en") is not None
        counts = cache.counts()
        assert (counts.hits, counts.misses, counts.unreadable) == (2, 2, 0)
        await cache.aclose()

    asyncio.run(scene())
    assert fake.calls == [(TEXT, "en"), (TEXT, "en")]


def test_before_open_and_after_close_it_passes_every_take_on_and_holds_none(
    tmp_path: Path,
) -> None:
    fake = FakeTextToSpeech()

    async def scene() -> None:
        cache = cache_of(fake, tmp_path)
        assert len(await said(cache)) > 0 and await cache.held(TEXT, language="en") is None
        await cache.open()
        await kept(cache)
        await cache.aclose()
        await cache.aclose()  # a second close does nothing
        assert await cache.held(TEXT, language="en") is None
        assert len(await said(cache, "Another clause.")) > 0

    asyncio.run(scene())
    assert len(takes_in(tmp_path)) == 1 and not fake.closed


def test_its_counts_and_taken_which_resets_them(tmp_path: Path) -> None:
    async def scene() -> tuple[ClauseCounts, ...]:
        cache = cache_of(FakeTextToSpeech(), tmp_path)
        await cache.open()
        assert await cache.held(TEXT, language="en") is None
        await kept(cache)
        assert await cache.held(TEXT, language="en") is not None
        first = cache.taken()
        second = cache.counts()
        await cache.aclose()
        return first, second

    first, second = asyncio.run(scene())
    assert (first.hits, first.misses, first.kept, first.entries) == (1, 1, 1, 1)
    assert (len(first.hit_s), len(first.miss_s)) == (1, 1)
    assert all(0 <= s < 0.2 for s in (*first.hit_s, *first.miss_s))
    assert 0 < first.megabytes < 1
    assert (second.hits, second.misses, second.kept, second.hit_s) == (0, 0, 0, ())
    assert (second.entries, second.megabytes) == (first.entries, first.megabytes)  # what it holds


MARK = "zx-made-up-mark-77"


def test_no_log_line_and_no_count_holds_a_text_or_a_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """A key is a hash of a short text that can be guessed back (GP-19): opened, a hit, a
    miss, an unreadable file, a failed write, a trim and the close log neither."""
    caplog.set_level(logging.DEBUG, logger="t2_agentic_voice")
    text = f"Your code is {MARK}."
    keys: set[str] = set()
    write = write_whole

    def refused(path: Path, data: bytes) -> None:
        raise PermissionError(f"made-up: {path.name} {MARK} is held")

    async def scene() -> ClauseCounts:
        cache = cache_of(FakeTextToSpeech(seconds_per_char=0.2), tmp_path, max_mb=1)
        await cache.open()
        await kept(cache, text)
        keys.update(path.stem for path in takes_in(tmp_path))
        assert await cache.held(text, language="en") is not None
        assert await cache.held(f"{text}!", language="en") is None
        (path,) = takes_in(tmp_path)
        path.write_bytes(b"made-up, no WAV")
        assert await cache.held(text, language="en") is None
        monkeypatch.setattr(clause_cache, "write_whole", refused)
        await kept(cache, text)
        monkeypatch.setattr(clause_cache, "write_whole", write)
        for each in range(3):
            await kept(cache, f"{text} {each}, and more words to fill the megabyte it keeps.")
            keys.update(path.stem for path in takes_in(tmp_path))
        counts = cache.counts()
        await cache.aclose()
        return counts

    counts = asyncio.run(scene())
    logged = {r.getMessage() for r in caplog.records}
    assert {"clause_cache_opened", "clause_unreadable", "clause_cache_trimmed"} <= logged
    assert {"clause_write_failed", "clause_cache_closed"} <= logged
    assert (counts.unreadable, counts.write_failures, counts.removed) == (1, 1, 2)
    surfaces = shown(caplog=caplog) | {"counts": repr(counts)}
    assert holding(MARK, surfaces) == [] and len(keys) == 4
    assert all(holding(key, surfaces) == [] for key in keys)
    (failed,) = [r for r in caplog.records if r.getMessage() == "clause_write_failed"]
    assert vars(failed)["fields"]["error"] == "PermissionError"

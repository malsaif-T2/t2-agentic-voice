"""The clause cache's files (adapters/clause_cache.py, plan 007): each take a whole WAV named by
its key; a file that does not read as the cache writes one a miss, counted, removed and kept anew
by the next take; a `.part` a crash left removed at `open`, and every file of another name left
as it is (GP-21); the bound, the takes played longest ago removed first, a hit keeping its own,
and a file Windows will not let go of left for the next round; a write or a rename the disk
refuses, which leaves nothing behind; its close, which lets its writer finish (at most 5 s) and
never closes the adapter it wraps; and `clear`. On the fakes' text-to-speech, in a test's own
folder."""

from __future__ import annotations

import asyncio
import io
import threading
import time
import wave
from pathlib import Path

import pytest
from t2_agentic_voice.adapters import clause_cache
from t2_agentic_voice.adapters.clause_counts import ClauseCounts
from t2_agentic_voice.adapters.wav_files import write_whole
from t2_agentic_voice.domain.ports.text_to_speech import AudioChunk

from tests.t2_agentic_voice.adapters.clause_support import (
    TEXT,
    cache_of,
    kept,
    said,
    take,
    takes_in,
    wav,
)
from tests.t2_agentic_voice.fakes import FakeTextToSpeech, tone

# Each test here reads its takes within a limit no machine's load reaches (conftest.py).
pytestmark = pytest.mark.usefixtures("relaxed_reads")

KEY = "0123456789abcdef0123456789abcdef"


def _read(path: Path) -> tuple[int, int, int, bytes]:
    with wave.open(io.BytesIO(path.read_bytes()), "rb") as reader:
        return (
            reader.getnchannels(),
            reader.getsampwidth(),
            reader.getframerate(),
            reader.readframes(reader.getnframes()),
        )


def test_each_take_is_one_whole_wav_named_by_its_key(tmp_path: Path) -> None:
    fake = FakeTextToSpeech(sample_rate=22_050)

    async def scene() -> None:
        cache = cache_of(fake, tmp_path / "clauses")
        await cache.open()
        await kept(cache)
        await cache.aclose()

    asyncio.run(scene())
    (path,) = list((tmp_path / "clauses").iterdir())
    assert len(path.stem) == 32 and int(path.stem, 16) >= 0 and path.suffix == ".wav"
    assert _read(path) == (1, 2, 22_050, take(TEXT, fake))


def _junk(kind: str, whole: bytes) -> bytes:
    if kind == "truncated":
        return whole[:30]  # cut inside its header
    if kind == "stereo":
        return wav(b"\x00" * 400, channels=2)
    if kind == "8-bit":
        return wav(b"\x80" * 400, width=1)
    if kind == "frames":  # its header counts more frames than its data holds
        return whole[:-100]
    if kind == "large":  # a whole WAV, past the 4 MB a take may be
        return wav(tone(90.0, 24_000))
    return b"made-up, no WAV"


@pytest.mark.parametrize("kind", ["truncated", "stereo", "8-bit", "no-wav", "frames", "large"])
def test_a_file_that_is_no_take_is_a_miss_removed_and_kept_anew(kind: str, tmp_path: Path) -> None:
    fake = FakeTextToSpeech()

    async def scene() -> tuple[ClauseCounts, AudioChunk | None]:
        first = cache_of(fake, tmp_path)
        await first.open()
        await kept(first)
        await first.aclose()
        (path,) = takes_in(tmp_path)
        path.write_bytes(_junk(kind, path.read_bytes()))
        cache = cache_of(fake, tmp_path)
        await cache.open()
        assert await cache.held(TEXT, language="en") is None
        await cache._written()
        assert not path.exists()  # removed by its writer
        counts = cache.counts()
        await kept(cache)  # the next take is kept anew
        found = await cache.held(TEXT, language="en")
        await cache.aclose()
        return counts, found

    counts, found = asyncio.run(scene())
    assert (counts.unreadable, counts.misses, counts.hits, counts.entries) == (1, 1, 0, 0)
    assert found is not None and found.pcm16 == take(TEXT, fake)
    assert len(fake.calls) == 2


def test_open_removes_its_own_parts_and_leaves_every_other_file(tmp_path: Path) -> None:
    """A `.part` of its own pattern, left by a crash, is removed; nothing else is read, touched
    or removed, at `open`, at the bound or at `clear` (GP-21)."""
    folder = tmp_path / "clauses"
    folder.mkdir()
    (folder / f"{KEY}.0123456789abcdef.part").write_bytes(b"half a take")
    others = {
        "notes.txt": b"the owner's",
        f"{KEY.upper()}.wav": b"not its own name",
        f"{KEY}.wav.bak": b"a copy",
        f"{KEY}.part": b"no random part",
        "phrase.wav": wav(b"\x00" * 400),
    }
    for name, data in others.items():
        (folder / name).write_bytes(data)
    (folder / "inner").mkdir()

    async def scene() -> ClauseCounts:
        cache = cache_of(FakeTextToSpeech(seconds_per_char=0.2), folder, max_mb=1)
        await cache.open()
        opened = cache.counts()
        for each in range(3):
            await kept(cache, f"Clause {each}, said with words enough to fill the bound it has.")
        await cache.clear()
        await cache.aclose()
        return opened

    opened = asyncio.run(scene())
    assert opened.entries == 0
    left = {path.name: path.read_bytes() for path in folder.iterdir() if path.is_file()}
    assert left == others and (folder / "inner").is_dir()


SAMPLES_S = 4.0  # each take: 4 s at 24 kHz, 192,044 bytes as a file


def _clause(letter: str) -> str:
    """A clause of 40 characters, 4 s at 0.1 s a character."""
    return f"Clause {letter} of the bound test, said now.".ljust(40, ".")


def test_past_its_bound_the_takes_played_longest_ago_are_removed_first(tmp_path: Path) -> None:
    """Five takes fit under 1 MB; the sixth passes it, so the oldest two are removed (under nine
    tenths of it, 900,000 bytes); a hit on the oldest first keeps it."""
    fake = FakeTextToSpeech(seconds_per_char=SAMPLES_S / 40)

    async def scene() -> tuple[ClauseCounts, dict[str, bool]]:
        cache = cache_of(fake, tmp_path, max_mb=1)
        await cache.open()
        for letter in "ABCDE":
            await kept(cache, _clause(letter))
        assert await cache.held(_clause("A"), language="en") is not None
        await kept(cache, _clause("F"))
        found = {
            letter: await cache.held(_clause(letter), language="en") is not None
            for letter in "ABCDEF"
        }
        counts = cache.counts()
        await cache.aclose()
        return counts, found

    counts, found = asyncio.run(scene())
    assert found == {"A": True, "B": False, "C": False, "D": True, "E": True, "F": True}
    assert (counts.removed, counts.entries, len(takes_in(tmp_path))) == (2, 4, 4)
    assert counts.megabytes == pytest.approx(4 * 192_044 / 1_000_000)


def test_a_file_windows_will_not_let_go_of_stays_for_the_next_round(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = FakeTextToSpeech(seconds_per_char=SAMPLES_S / 40)
    unlink = Path.unlink
    held: set[str] = set()

    def refusing(self: Path, missing_ok: bool = False) -> None:
        if self.name in held:
            raise PermissionError("made-up: another process holds it")
        unlink(self, missing_ok=missing_ok)

    monkeypatch.setattr(Path, "unlink", refusing)

    async def scene() -> tuple[set[str], set[str], set[str], int]:
        cache = cache_of(fake, tmp_path, max_mb=1)
        await cache.open()
        for letter in "ABCDE":
            await kept(cache, _clause(letter))
        oldest = {path.name for path in takes_in(tmp_path)}
        held.update(oldest)  # the five files held by another process
        await kept(cache, _clause("F"))  # past the bound: the five stay, F's own goes
        after_f = {path.name for path in takes_in(tmp_path)}
        entries = cache.counts().entries
        held.clear()
        await kept(cache, _clause("G"))  # the next round: the two oldest go
        after_g = {path.name for path in takes_in(tmp_path)}
        await cache.aclose()
        return oldest, after_f, after_g, entries

    oldest, after_f, after_g, entries = asyncio.run(scene())
    assert after_f == oldest and entries == 5  # the bound held: F's take was the one to go
    assert len(after_g) == 4 and len(oldest - after_g) == 2  # under 900,000 bytes again


def test_a_rename_the_disk_refuses_drops_its_part_and_the_take(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def refused(self: Path, target: Path) -> Path:
        raise PermissionError("made-up: the file is held")

    monkeypatch.setattr(Path, "replace", refused)

    async def scene() -> tuple[ClauseCounts, AudioChunk | None]:
        cache = cache_of(FakeTextToSpeech(), tmp_path)
        await cache.open()
        await kept(cache)
        found = await cache.held(TEXT, language="en")
        counts = cache.counts()
        await cache.aclose()
        return counts, found

    counts, found = asyncio.run(scene())
    assert found is None and (counts.write_failures, counts.kept, counts.entries) == (1, 0, 0)
    assert list(tmp_path.iterdir()) == []


def test_a_write_the_disk_refuses_leaves_nothing_and_the_clause_plays_as_today(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def refused(self: Path, data: bytes) -> int:
        raise OSError("made-up: the disk is full")

    monkeypatch.setattr(Path, "write_bytes", refused)
    fake = FakeTextToSpeech()

    async def scene() -> tuple[list[AudioChunk], ClauseCounts]:
        cache = cache_of(fake, tmp_path)
        await cache.open()
        chunks = await kept(cache)
        assert await cache.held(TEXT, language="en") is None
        again = await kept(cache)  # requested as today, and tried again
        counts = cache.counts()
        await cache.aclose()
        return chunks + again, counts

    chunks, counts = asyncio.run(scene())
    assert b"".join(c.pcm16 for c in chunks) == take(TEXT, fake) * 2
    assert (counts.write_failures, counts.kept) == (2, 0) and list(tmp_path.iterdir()) == []


def test_its_close_drains_its_writer_and_never_closes_the_adapter_it_wraps(
    tmp_path: Path,
) -> None:
    fake = FakeTextToSpeech()

    async def scene() -> None:
        cache = cache_of(fake, tmp_path)
        await cache.open()
        await said(cache, "First clause.")
        await said(cache, "Second clause.")
        await cache.aclose()  # the two writes queued, done before it returns

    asyncio.run(scene())
    assert len(takes_in(tmp_path)) == 2 and not fake.closed


def test_a_writer_that_hangs_is_given_up_on_at_close(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Its close waits at most `CLOSE_TIMEOUT_S` (5 s, shortened here) for its writer, then
    drops what is left."""
    monkeypatch.setattr(clause_cache, "CLOSE_TIMEOUT_S", 0.2)
    release = threading.Event()
    write = write_whole

    def stuck(path: Path, data: bytes) -> None:
        release.wait(5.0)
        write(path, data)

    monkeypatch.setattr(clause_cache, "write_whole", stuck)

    async def scene() -> float:
        cache = cache_of(FakeTextToSpeech(), tmp_path)
        await cache.open()
        await said(cache, "First clause.")
        await said(cache, "Second clause.")
        started = time.perf_counter()
        await cache.aclose()
        took = time.perf_counter() - started
        release.set()  # the write in its thread ends
        return took

    took = asyncio.run(scene())
    assert took < 1.0
    (closed,) = [r for r in caplog.records if r.getMessage() == "clause_cache_closed"]
    assert vars(closed)["fields"]["dropped"] == 1


def test_clear_removes_its_takes_and_resets_its_counts(tmp_path: Path) -> None:
    (tmp_path / "notes.txt").write_text("the owner's", encoding="utf-8")

    async def scene() -> None:
        cache = cache_of(FakeTextToSpeech(), tmp_path)
        await cache.open()
        await kept(cache, "First clause.")
        await kept(cache, "Second clause.")
        assert await cache.held("First clause.", language="en") is not None
        await said(cache, "Third clause.")  # still queued: cleared too
        await cache.clear()
        counts = cache.counts()
        assert (counts.hits, counts.misses, counts.kept, counts.entries) == (0, 0, 0, 0)
        assert (counts.megabytes, counts.hit_s, counts.miss_s) == (0.0, (), ())
        assert await cache.held("First clause.", language="en") is None
        await kept(cache, "First clause.")  # kept again after it
        assert await cache.held("First clause.", language="en") is not None
        await cache.aclose()

    asyncio.run(scene())
    assert len(takes_in(tmp_path)) == 1
    assert (tmp_path / "notes.txt").read_text(encoding="utf-8") == "the owner's"

"""The clause cache's folder (adapters/clause_cache.py): its takes, each `<key>.wav`, and the index
of them the cache keeps in memory, in the order they were last played, so a miss is a dictionary
look-up and the bound removes the one played longest ago first.

Only files of its own naming are ever read, touched or removed: a take, `<32 hex>.wav`, and a
`.part` its writer left, `<32 hex>.<16 hex>.part` (adapters/wav_files.py's `write_whole`); every
other file in the folder is left as it is (GP-21). The index is read and changed on the event
loop only; the file methods run in a thread.
"""

from __future__ import annotations

import contextlib
import os
import re
from dataclasses import dataclass
from pathlib import Path

from t2_agentic_voice.adapters.wav_files import take_of
from t2_agentic_voice.domain.ports.text_to_speech import AudioChunk

# The largest take file read (the agent's number, plan 007): about 87 s of speech at 24 kHz.
MAX_TAKE_BYTES = 4 * 1024 * 1024
_MB = 1_000_000
_TAKE = re.compile(r"[0-9a-f]{32}\.wav")
_PART = re.compile(r"[0-9a-f]{32}\.[0-9a-f]{16}\.part")


@dataclass(eq=False)
class Entry:
    """One take in the index: its file's size. Compared by identity, so a reader that comes
    back late never drops an entry made after the one it read."""

    size: int


class ClauseFiles:
    """The takes in `folder`, and their index (`index`, by key, the one played longest ago
    first; `bytes`, their files' sizes summed)."""

    def __init__(self, folder: Path) -> None:
        self.folder = folder
        self.index: dict[str, Entry] = {}
        self.bytes = 0

    @property
    def megabytes(self) -> float:
        return self.bytes / _MB

    def path(self, key: str) -> Path:
        return self.folder / f"{key}.wav"

    def add(self, key: str, size: int) -> None:
        """A take written for `key`, played last of all."""
        self.drop(key, self.index.get(key))
        self.index[key] = Entry(size)
        self.bytes += size

    def drop(self, key: str, entry: Entry | None) -> None:
        """Forget `key`'s entry, when it is still `entry`."""
        if entry is not None and self.index.get(key) is entry:
            del self.index[key]
            self.bytes -= entry.size

    def played(self, key: str, entry: Entry) -> None:
        """`key`'s take was played: it goes last in the order of removal."""
        if self.index.get(key) is entry:
            del self.index[key]
            self.index[key] = entry

    def opened(self, entries: list[tuple[str, int]]) -> None:
        """The index of the takes `scan` found."""
        self.index = {key: Entry(size) for key, size in entries}
        self.bytes = sum(size for _, size in entries)

    def scan(self) -> tuple[list[tuple[str, int]], int]:
        """The folder, made when missing: its takes by key and size, the one touched longest
        ago first, and how many `.part` files a stopped write left were removed. In a thread."""
        self.folder.mkdir(parents=True, exist_ok=True)
        found: list[tuple[float, str, int]] = []
        parts = 0
        for path in self.folder.iterdir():
            if _PART.fullmatch(path.name):
                with contextlib.suppress(OSError):
                    path.unlink(missing_ok=True)
                    parts += 1
            elif _TAKE.fullmatch(path.name) and path.is_file():
                with contextlib.suppress(OSError):
                    stat = path.stat()
                    found.append((stat.st_mtime, path.name[:32], stat.st_size))
        return [(key, size) for _, key, size in sorted(found)], parts

    def read(self, key: str) -> AudioChunk | None:
        """`key`'s take from its file, its time touched; None when the file is no take (past
        `MAX_TAKE_BYTES`, or not as the cache writes one). FileNotFoundError when it is gone. In a
        thread."""
        path = self.path(key)
        with path.open("rb") as file:
            data = file.read(MAX_TAKE_BYTES + 1)
        found = None if len(data) > MAX_TAKE_BYTES else take_of(data)
        if found is None or not found.pcm16:
            return None
        with contextlib.suppress(OSError):
            os.utime(path)
        return found

    def remove(self, key: str) -> bool:
        """Remove `key`'s file; whether it is gone (False when the system will not let go of
        it). In a thread."""
        try:
            self.path(key).unlink(missing_ok=True)
        except OSError:
            return False
        return True

    def remove_takes(self) -> None:
        """Remove every take of its own naming in the folder. In a thread."""
        for path in self.folder.iterdir():
            if _TAKE.fullmatch(path.name) and path.is_file():
                with contextlib.suppress(OSError):
                    path.unlink(missing_ok=True)

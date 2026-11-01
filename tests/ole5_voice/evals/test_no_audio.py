"""No audio in git (D-022): no audio file sits under `apps/`, `packages/`, `examples/`, `docs/` or
`tests/`, whatever its name. A file is audio by its extension or by its first bytes (a WAV, Ogg,
FLAC, MP3, Matroska or WebM, MP4 or M4A, AIFF or AMR header), so a renamed recording is found
too. The golden set's audio lives under the git-ignored `var/` or outside the repository, and
its manifests hold only paths and hashes. A self-test shows the search finds each kind."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
FOLDERS = ("apps", "packages", "examples", "docs", "tests")
SUFFIXES = {".wav", ".wave", ".webm", ".weba", ".ogg", ".oga", ".opus", ".mp3", ".m4a", ".aac"}
SUFFIXES |= {".flac", ".aif", ".aiff", ".amr", ".wma", ".mka", ".mp4"}


def _is_audio(head: bytes) -> bool:
    """Whether a file's first bytes are an audio container's header."""
    return (
        (head[:4] in (b"RIFF", b"RIFX", b"RF64") and head[8:12] in (b"WAVE", b"AVI "))
        or head[:4] in (b"OggS", b"fLaC", b"\x1aE\xdf\xa3", b".snd")
        or head[:3] == b"ID3"
        or head[:2] in (b"\xff\xfb", b"\xff\xf3", b"\xff\xf2", b"\xff\xf1", b"\xff\xf9")
        or head[4:8] == b"ftyp"
        or (head[:4] == b"FORM" and head[8:12] in (b"AIFF", b"AIFC"))
        or head[:5] == b"#!AMR"
    )


def audio_files(root: Path, folders: Sequence[str] = FOLDERS) -> list[str]:
    """Every audio file below the folders of `root`, by extension or by header."""
    found = []
    for folder in folders:
        for path in sorted(p for p in (root / folder).rglob("*") if p.is_file()):
            with path.open("rb") as file:
                head = file.read(12)
            if path.suffix.lower() in SUFFIXES or _is_audio(head):
                found.append(path.relative_to(root).as_posix())
    return found


def test_no_audio_file_is_in_the_repository() -> None:
    assert audio_files(ROOT) == []


def test_the_search_finds_audio_by_its_name_or_its_header(tmp_path: Path) -> None:
    headers = {
        "apps/a/evals/clip.WAV": b"",  # an empty file, by its name
        "packages/x/take.bin": b"RIFF\x24\x00\x00\x00WAVEfmt ",
        "examples/e/a.dat": b"OggS\x00\x02",
        "docs/d/b": b"fLaC\x00\x00\x00\x22",
        "tests/t/c.txt": b"ID3\x04\x00",
        "tests/t/d.json": b"\x1aE\xdf\xa3\x01\x00",  # Matroska or WebM
        "tests/t/e.data": b"\x00\x00\x00\x20ftypM4A ",
        "tests/t/f": b"FORM\x00\x00\x00\x10AIFF",
        "tests/t/g": b"\xff\xfb\x90\x00",  # an MP3 frame
    }
    plain = {"apps/a/notes.md": b"RIFF is a format", "tests/t/h.py": b"x = 1\n", "docs/i": b""}
    for name, data in (headers | plain | {"var/kept.wav": b"RIFF"}).items():
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_bytes(data)
    assert sorted(audio_files(tmp_path)) == sorted(headers)  # var/ is not searched

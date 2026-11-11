"""The model files a spoken-language classifier loads (plan 007's Block H, Q16), and what the two
classifier adapters share (silero_language.py, ecapa_language.py).

**The files.** Each classifier's files are fetched once, by hand, into the folder
`stt.classifier_dir` names, outside every repository and `var/`, as the guide's languages page
says; nothing downloads at run time (the design's 11). Each file is pinned here by its name,
its size and its SHA-256 (`ModelFile`), and `checked` reads every one at each load, so a file
missing, cut short or changed is a ConfigurationError naming the file, the setting and the
guide's page, never the file's bytes; `t2v doctor` shows each file's check (`problem`).

**One at a time.** One classification runs at a time a process, whichever adapter: a second
asked while one runs is busy, and the turn keeps its language (`ONE_AT_A_TIME`, taken on the
worker thread, so a cancelled request that never ran holds nothing).

**The caller's audio** reaches a model as float32 samples from -1 to 1 (`samples`), from the
call's mono 16-bit PCM at 16 kHz, the rate both models were trained on (`RATE`).
"""

from __future__ import annotations

import hashlib
import re
import threading
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import numpy as np
import numpy.typing as npt

from t2_agentic_voice.core.errors import ConfigurationError, ProviderError
from t2_agentic_voice.domain.ports.speech_to_text import AudioClip

# The guide's page that says where each file comes from and how to fetch it.
GUIDE: Final = "docs/guide/languages.md"
# The setting that names the folder.
SETTING: Final = "stt.classifier_dir"
# The sample rate both models hear.
RATE: Final = 16_000
# One classification at a time a process (the module's docstring).
ONE_AT_A_TIME = threading.Lock()
_CHUNK = 1 << 20
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")

type Samples = npt.NDArray[np.float32]


@dataclass(frozen=True, kw_only=True)
class ModelFile:
    """One pinned model file: its `name` in the folder, its `size` in bytes and its SHA-256 in
    lowercase hex."""

    name: str
    size: int
    sha256: str

    def __post_init__(self) -> None:
        if not _NAME.fullmatch(self.name) or ".." in self.name:
            raise ValueError("a model file's name is a plain file name in its folder")
        if not _SHA256.fullmatch(self.sha256):
            raise ValueError("a model file's pin is its SHA-256 in 64 lowercase hex digits")
        if self.size < 0:
            raise ValueError("a model file's size is a count of bytes")


def digest(path: Path) -> str:
    """The SHA-256 of the file at `path`, in lowercase hex, read in chunks."""
    found = hashlib.sha256()
    with path.open("rb") as file:
        while chunk := file.read(_CHUNK):
            found.update(chunk)
    return found.hexdigest()


def problem(folder: Path, file: ModelFile) -> str | None:
    """What is wrong with `file` in `folder`, with its fix; None when it matches its pin."""
    path = folder / file.name
    fix = f"FIX: fetch it again as {GUIDE} says, into the folder {SETTING} names."
    if not path.is_file():
        return f"The model file {file.name} in {SETTING} is missing. {fix}"
    size = path.stat().st_size
    if size != file.size:
        return f"The model file {file.name} in {SETTING} holds {size} bytes, not {file.size}. {fix}"
    if digest(path) != file.sha256:
        return f"The model file {file.name} in {SETTING} differs from its pinned SHA-256. {fix}"
    return None


def folder_problem(folder: Path | None) -> str | None:
    """What is wrong with the folder itself, with its fix; None when it is one."""
    if folder is None:
        return (
            f"{SETTING} is not set, and live_language classified needs the classifier's model "
            f"files. FIX: fetch them as {GUIDE} says and set {SETTING} to their folder."
        )
    if not folder.is_dir():
        return f"{SETTING} is not a folder. FIX: set it to the folder of the model files ({GUIDE})."
    return None


def checked(folder: Path | None, files: Sequence[ModelFile]) -> Path:
    """`folder`, once it is one and every file of `files` in it matches its pin; a
    ConfigurationError for the first that does not (the module's docstring)."""
    found = folder_problem(folder)
    if found is not None or folder is None:
        raise ConfigurationError(found or "", details={"setting": SETTING})
    for file in files:
        found = problem(folder, file)
        if found is not None:
            raise ConfigurationError(found, details={"setting": SETTING, "file": file.name})
    return folder


def heard_codes(name: str, among: Sequence[str], labels: Sequence[str]) -> tuple[str, ...]:
    """`among`, each a code the classifier `name` hears (`labels`), each once; a
    ConfigurationError before any call otherwise."""
    codes = tuple(dict.fromkeys(among))
    unheard = [code for code in codes if code not in labels]
    if not codes or unheard:
        raise ConfigurationError(
            f"The {name} classifier hears {', '.join(sorted(labels))}, and was asked for "
            f"{', '.join(unheard) or 'no language'}. FIX: give the agent languages it hears, or "
            "set stt.live_language to session."
        )
    return codes


def samples(clip: AudioClip) -> Samples:
    """`clip`'s mono 16-bit PCM as float32 samples from -1 to 1; a rejected `ProviderError` for
    a clip at another rate than `RATE`."""
    if clip.sample_rate != RATE:
        raise ProviderError("rejected", False)
    pcm = np.frombuffer(clip.pcm16, dtype="<i2")
    return (pcm.astype(np.float32) / np.float32(32_768)).astype(np.float32)

"""The golden set's shared models: the items and their variants, the manifests of the audio
(never the audio itself, D-022) and the committed split, with the field types every part uses.

What a run produces is in `runs.py`, and the recorder's own files in `takes.py`. Every model is
read-only and parses strictly, so a file with a misspelt or missing field fails as it is read
(GP-06), and its errors never echo the value refused, which may be a transcript or a key.
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import PurePosixPath
from typing import Annotated, Final, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints

Sha256 = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
# An item's, a variant's, a take's, a root's or a session's name.
Name = Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9_.-]{0,127}$")]
# The name of a held-out run's pooled group (`runs.HELD_OUT_MIN_ITEMS`). No language, device or
# split is named so, and no kind may be, so it never merges with a real value.
Other = Literal["other"]
OTHER: Final[Other] = "other"


def _not_other(kind: str) -> str:
    if kind == OTHER:
        raise ValueError(f'"{OTHER}" names the pooled group of a held-out run, never a kind')
    return kind


# An item's kind: `request`, `stop_word`, `listening_sound`, ... (never a reference's words).
Kind = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z_]{0,63}$"), AfterValidator(_not_other)]
# The kind of the items that read out a ticket number, over which ID recall is scored.
TICKET_KIND: Final = "ticket_number"
Commit = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{7,40}\+?$")]
Language = Literal["saudi", "msa", "english", "mixed", "none"]
Device = Literal["laptop", "wired", "bluetooth"]  # the microphone used
Split = Literal["dev", "held-out"]
# The names Windows keeps for a device, whatever their extension: COM and LPT ports 0 to 9, and
# 1 to 3 written as superscripts (U+00B9, U+00B2, U+00B3).
_DEVICES = frozenset(
    ["CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$"]
    + [f"{port}{n}" for port in ("COM", "LPT") for n in "0123456789¹²³"]
)


def _under_root(value: str) -> str:
    """A path below a named root: relative, with forward slashes and no `..`, and each part a
    plain name Windows keeps as written (no device name such as `nul` or `con.wav`, no part that
    ends in a dot or a space, no control character, none of `*?"<>|`), so no manifest or request
    names anything but a file below its root."""
    path = PurePosixPath(value)
    if (
        not value
        or "\\" in value
        or ":" in value
        or path.is_absolute()
        or not path.parts
        or path.as_posix() != value
        or not all(_plain(part) for part in path.parts)
    ):
        raise ValueError(
            "must be a relative path below its root, with / and no '..', each part a plain name"
        )
    return value


def _plain(part: str) -> bool:
    return not (
        part.strip(".") == ""  # `.`, `..`, `...`
        or part[-1] in ". "  # Windows drops them, so the name is another's alias
        or any(ord(c) < 0x20 or c in '*?"<>|' for c in part)
        or part.split(".")[0].rstrip(" ").upper() in _DEVICES
    )


RelativePath = Annotated[str, AfterValidator(_under_root)]


def _increasing(value: tuple[int, ...]) -> tuple[int, ...]:
    if any(ms < 0 for ms in value) or list(value) != sorted(set(value)):
        raise ValueError("turn ends are distinct milliseconds from the take's start, in order")
    return value


TurnEnds = Annotated[tuple[int, ...], AfterValidator(_increasing)]


class Model(BaseModel):
    """The base of the golden set's models: read-only, every field known, and an error that
    never echoes the value it refused."""

    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)


class AudioRef(Model):
    """One audio file, named without the file: its root (given at run time as
    `--audio <root>=<folder>`), its path below the root, and its SHA-256."""

    root: Name
    path: RelativePath
    sha256: Sha256


class Confirmation(Model):
    """One listen in which the owner confirmed that a variant says its reference."""

    at: datetime
    review_pass: int = Field(ge=1)


class Variant(Model):
    """One recording of an item, one take on one device. A take the lab's detector split in
    two is one variant, its segments in order, scored on their transcripts joined."""

    id: Name
    segments: tuple[AudioRef, ...] = Field(min_length=1)
    device: Device
    session: Name
    # What it says, under the spelling guide; empty when nothing is said.
    reference: str
    # Where the reference came from: the script's line, the owner's typed words, or no speech.
    reference_source: Literal["script", "typed", "none"]
    confirmations: tuple[Confirmation, ...] = ()
    # The true turn ends of a take of several clauses, in ms from its start.
    turn_ends_ms: TurnEnds = ()
    tags: tuple[Name, ...] = ()  # such as `over-assistant`, `duck`, `playback-headset`


class Item(Model):
    """One scripted utterance and its recordings (evaluation.md, "Items and splits here")."""

    id: Name
    source: Literal["talkover", "script"]
    kind: Kind
    language: Language
    text: str  # the scripted words; empty for an item with no speech
    alternatives: tuple[str, ...] = ()  # other references accepted as right
    terms: tuple[str, ...] = ()  # the product terms it holds, for term recall
    # A talk-over phrase's `want` label (refs.json), which the window measures are broken down
    # by; None for the new recordings.
    want: Name | None = None
    variants: tuple[Variant, ...] = Field(min_length=1)


class Consent(Model):
    """A speaker's agreement that their recordings are used in this golden set."""

    speaker: str = Field(min_length=1)
    agreed: Literal[True]
    on: date
    words: str = Field(min_length=1)  # what the speaker confirmed, in their words


class ManifestFile(Model):
    """One audio file: its path below the manifest's root, its hash and its format."""

    path: RelativePath
    sha256: Sha256
    seconds: float = Field(gt=0)
    sample_rate: int = Field(gt=0)
    device: Device
    session: Name


class Manifest(Model):
    """The audio files below one named root: their paths and hashes in git, never the audio."""

    root: Name
    consent: Consent | None = None  # every speaker of the new recordings agreed
    files: tuple[ManifestFile, ...] = Field(min_length=1)


class SplitFile(Model):
    """`split.json`, the committed split: its salt and each item's split, by item ID (Track D
    writes it, the runner reads it)."""

    salt: str = Field(min_length=1)
    items: dict[Name, Split] = Field(min_length=1)

"""The recorder's files: the script it shows, and what it writes under `--out`, which the import
reads back (Tracks G and D).

`script.toml` holds the script's lines and its fixed list of listening sounds (`load_script`).
Below `--out`, each session has its own folder, holding its `session.json` (the session's device
and the speaker's consent), and for each take its WAV file, its sidecar and one file for each
review: `session_file`, `take_audio`, `take_sidecar` and `review_file` name them. Each file is
written new, never rewritten. Every model parses strictly, as `models.py`'s do.
"""

from __future__ import annotations

import tomllib
from datetime import datetime
from pathlib import Path
from typing import Final, Literal

from pydantic import Field, TypeAdapter

from ole5_voice.evals.models import (
    Consent,
    Device,
    Kind,
    Language,
    Model,
    Name,
    RelativePath,
    Sha256,
    TurnEnds,
)

SESSION_FILE: Final = "session.json"
_BELOW_OUT: TypeAdapter[str] = TypeAdapter(RelativePath)


class ScriptLine(Model):
    """One line of `script.toml`: what the owner says, or does, for one new item."""

    id: Name
    kind: Kind
    language: Language
    say: tuple[str, ...] = ()  # the clauses, in order, with a pause between; none: no speech
    cue: str = ""  # what the page shows besides: the noise to make, "say nothing"
    reply: Name | None = None  # the agent's reply (its ID in `replies.json`) played meanwhile
    seconds: float | None = Field(default=None, gt=0)  # a fixed length, for silence and noise
    terms: tuple[str, ...] = ()

    @property
    def text(self) -> str:
        """The words the line asks for, as one reference."""
        return " ".join(self.say)


class Script(Model):
    """`script.toml`: `listening_sounds = [...]`, the fixed list that comes with the script (the
    spelling guide, Q8 of plan 002), then one `[[lines]]` table for each line."""

    listening_sounds: tuple[str, ...] = ()
    lines: tuple[ScriptLine, ...] = Field(min_length=1)


def load_script(path: Path) -> Script:
    """`script.toml`, read and checked, so the recorder and the import read it alike."""
    with path.open("rb") as file:
        return Script.model_validate(tomllib.load(file))


class SessionRecord(Model):
    """A session's `session.json`, written once, as the owner confirms the speaker's consent in
    `poe record`; the import copies the consent into the manifest, and refuses a session folder
    without one."""

    session: Name
    device: Device
    consent: Consent


class TrackSettings(Model):
    """The microphone track's settings, as the browser reports them."""

    echo_cancellation: bool | None = None
    noise_suppression: bool | None = None
    auto_gain_control: bool | None = None
    sample_rate: int | None = None
    channel_count: int | None = None


class TakeSidecar(Model):
    """The recorder's record of one take, beside its WAV file; neither is ever rewritten."""

    take: Name
    line: Name  # its script line
    session: Name
    device: Device
    microphone: str  # the input device's label, as the browser gives it
    output: str = ""  # the output device's label
    track: TrackSettings
    recorded_at: datetime
    file: RelativePath  # the WAV file's name, beside the sidecar: `<take>.wav`
    sha256: Sha256
    seconds: float = Field(gt=0)
    turn_ends_ms: TurnEnds = ()
    status: Literal["kept", "discarded"]


class Review(Model):
    """One check of a take in the recorder's review mode, written as a new file: the owner
    confirmed that it says its reference, or typed what it says instead."""

    take: Name
    review_pass: int = Field(ge=1)
    at: datetime
    verdict: Literal["confirmed", "typed"]
    text: str = ""  # what the owner typed


def session_file(session: str) -> str:
    """`<session>/session.json`, below `--out`."""
    return _below_out(f"{session}/{SESSION_FILE}")


def take_audio(session: str, take: str) -> str:
    """`<session>/<take>.wav`, below `--out`."""
    return _below_out(f"{session}/{take}.wav")


def take_sidecar(session: str, take: str) -> str:
    """`<session>/<take>.json`, below `--out`: the take's `TakeSidecar`."""
    return _below_out(f"{session}/{take}.json")


def review_file(session: str, take: str, review_pass: int) -> str:
    """`<session>/<take>.review-<pass>.json`, below `--out`: one `Review`."""
    return _below_out(f"{session}/{take}.review-{review_pass}.json")


def _below_out(path: str) -> str:
    """`path`, or ValueError when it would not name a plain file below `--out` (a session or a
    take named `nul`, say, on Windows)."""
    return _BELOW_OUT.validate_python(path)

"""The recorder's files: the script it shows, and what it writes under `--out`, which the import
reads back (`import_recordings.py`).

`script.toml` holds the script's lines and its fixed list of listening sounds (`Script`, read
with `items.read_toml` by the recorder, the import and `poe golden` alike).
Below `--out`, each session has its own folder, holding its `session.json` (the session's device
and the speaker's consent), and for each take its WAV file, its sidecar and one file for each
review: `session_file`, `take_audio`, `take_sidecar` and `review_file` name them. Each file is
written new, never rewritten. Every model parses strictly, as `models.py`'s do.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Final, Literal

from pydantic import Field, TypeAdapter

from ole5_voice.evals.models import (
    Consent,
    Device,
    Kind,
    Language,
    Model,
    Name,
    ReferenceSource,
    RelativePath,
    Sha256,
    TurnEnds,
    is_name,
)

SESSION_FILE: Final = "session.json"
# The highest review pass: a review's file name gives its pass in at most six digits.
MAX_REVIEW_PASS: Final = 999_999
# A review's file name: its take, a `Name` (`is_name` checks it), then its pass.
_REVIEW_FILE: Final = re.compile(r"^(?P<take>.+)\.review-(?P<number>[1-9][0-9]{0,5})\.json$")
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

    @property
    def source(self) -> ReferenceSource:
        """Its takes' reference source: the script's, or none for a line of no words."""
        return "script" if self.text else "none"


class Script(Model):
    """`script.toml`: `listening_sounds = [...]`, the fixed list that comes with the script (the
    spelling guide, Q8 of plan 002), then one `[[lines]]` table for each line."""

    listening_sounds: tuple[str, ...] = ()
    lines: tuple[ScriptLine, ...] = Field(min_length=1)


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
    review_pass: int = Field(ge=1, le=MAX_REVIEW_PASS)
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


def parse_review_file(name: str) -> tuple[str, int] | None:
    """The take and the pass a review's file name gives (the last part of `review_file`'s), or
    None for any other file's name: the one reading of it, the recorder's and the import's."""
    found = _REVIEW_FILE.match(name)
    if found is None or not is_name(found["take"]):
        return None
    return found["take"], int(found["number"])


def _below_out(path: str) -> str:
    """`path`, or ValueError when it would not name a plain file below `--out` (a session or a
    take named `nul`, say, on Windows)."""
    return _BELOW_OUT.validate_python(path)

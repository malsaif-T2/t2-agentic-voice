"""The recorded calls' manifests (plan 003's decision log, the recordings; run C): for each call
the recorder kept under `storage.var_dir/recordings/<call ID>/` (the caller's track, the agent's
audio and the playback timeline, voice/session's recorder), a manifest committed under
`apps/ole5-voice-agent/evals/calls/<call ID>.json`, so a later plan imports the calls as golden
items, as plan 002's import did. A manifest holds the call's consent and, for each file, its
path in the call's folder, SHA-256 and length (bytes, and for a WAV file its rate, channels and
seconds), never the audio or any text of the call; no audio is in git.

The consent is the one the calls were recorded under, given on the command line
(`--consent-version`, `privacy.consent_version` in the recorded sessions, Q7's `m2-owner-test-1`),
with `record_audio` true: the recorder keeps a call only under a verified signed consent that
allows it (docs/SECURITY.md, invariant 8). A manifest is written once: a call whose manifest is
already there, the same, is left as it is, and one whose manifest differs is refused, never
written over. Files whose names start with a dot (a write in progress) are left out.
`python -m ole5_voice.evals.call_manifests --recordings <var_dir>/recordings --consent-version
<version>`.
"""

from __future__ import annotations

import argparse
import json
import sys
import wave
from collections.abc import Sequence
from pathlib import Path
from typing import Annotated, Final, Literal

from pydantic import Field, StringConstraints
from t2_agentic_voice import configure_logging, get_logger

from ole5_voice import LOGGERS
from ole5_voice.evals.audio import sha256_file
from ole5_voice.evals.items import EVALS
from ole5_voice.evals.models import Model, RelativePath, Sha256

CALLS: Final = EVALS / "calls"
# A call's ID, as the router mints it and names the call's folder (core/events.py's pattern).
CallIdText = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_-]{1,64}$")]
ConsentVersion = Annotated[str, StringConstraints(min_length=1, max_length=64, pattern=r"^\S+$")]
_DESCRIPTION = (
    "Write a manifest for each recorded call: its consent, and each file's hash and length."
)
log = get_logger(__name__)


class CallConsent(Model):
    """The consent a call was recorded under: the version of the text agreed to, and that the
    caller agreed to have its audio recorded."""

    version: ConsentVersion
    record_audio: Literal[True] = True


class CallFile(Model):
    """One file of a recorded call: its path in the call's folder, its hash and its length; for
    a WAV file, its rate, its channels and how long it plays."""

    path: RelativePath
    sha256: Sha256
    bytes: int = Field(ge=0)
    sample_rate: int | None = Field(default=None, gt=0)
    channels: int | None = Field(default=None, gt=0)
    seconds: float | None = Field(default=None, ge=0)


class CallManifest(Model):
    """One recorded call's manifest: its ID, its consent and each of its files, in name order."""

    call_id: CallIdText
    consent: CallConsent
    files: tuple[CallFile, ...] = Field(min_length=1)


def _file(folder: Path, path: Path) -> CallFile:
    """`path`, a file of the call in `folder`, described."""
    found = CallFile(
        path=path.relative_to(folder).as_posix(),
        sha256=sha256_file(path),
        bytes=path.stat().st_size,
    )
    if path.suffix.lower() != ".wav":
        return found
    try:
        with wave.open(str(path), "rb") as wav:
            rate, channels, frames = wav.getframerate(), wav.getnchannels(), wav.getnframes()
    except (wave.Error, EOFError):
        return found  # not a WAV file the standard library reads: its hash and bytes only
    return found.model_copy(
        update={"sample_rate": rate, "channels": channels, "seconds": frames / rate}
    )


def manifest_of(folder: Path, *, consent_version: str) -> CallManifest:
    """The manifest of the call recorded in `folder`, named by its call ID."""
    files = sorted(
        path
        for path in folder.rglob("*")
        if path.is_file()
        and not any(part.startswith(".") for part in path.relative_to(folder).parts)
    )
    return CallManifest.model_validate(
        {
            "call_id": folder.name,
            "consent": {"version": consent_version, "record_audio": True},
            "files": [_file(folder, path).model_dump() for path in files],
        }
    )


def dump(manifest: CallManifest) -> str:
    """A manifest's committed text: JSON indented by two, its text as written, an LF at the end."""
    return json.dumps(manifest.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n"


def write_manifests(recordings: Path, out: Path, *, consent_version: str) -> tuple[int, int, int]:
    """A manifest in `out` for each call folder in `recordings`: how many were written, left as
    they were, and refused (a folder that is not a call's, holds no file, or whose manifest is
    there and differs)."""
    written = same = refused = 0
    for folder in sorted(path for path in recordings.iterdir() if path.is_dir()):
        try:
            text = dump(manifest_of(folder, consent_version=consent_version))
        except ValueError:  # a pydantic ValidationError: not a call ID, or no file
            refused += 1
            log.warning("call_refused", reason="not a recorded call's folder")
            continue
        target = out / f"{folder.name}.json"
        if target.exists():
            if target.read_bytes() == text.encode("utf-8"):
                same += 1
            else:
                refused += 1
                log.warning("call_refused", call=folder.name, reason="its manifest differs")
            continue
        out.mkdir(parents=True, exist_ok=True)
        target.write_bytes(text.encode("utf-8"))
        written += 1
        log.info("manifest_written", call=folder.name)
    return written, same, refused


def _version(text: str) -> str:
    """An argparse type: `text`, when it is a consent version a manifest takes."""
    try:
        return CallConsent(version=text).version
    except ValueError:  # a pydantic ValidationError, which never echoes the text
        raise argparse.ArgumentTypeError(
            "a consent version is 1 to 64 characters, no space"
        ) from None


def main(argv: Sequence[str] | None = None) -> int:
    """`python -m ole5_voice.evals.call_manifests`: 0 when every call has its manifest, 1 when one
    was refused, 2 when the recordings cannot be read."""
    parser = argparse.ArgumentParser(prog="call_manifests", description=_DESCRIPTION)
    parser.add_argument("--recordings", type=Path, required=True, help="var_dir's recordings")
    parser.add_argument(
        "--consent-version", type=_version, required=True, help="the consent recorded under"
    )
    parser.add_argument("--out", type=Path, default=CALLS, help="where (default: %(default)s)")
    args = parser.parse_args(argv)
    configure_logging(loggers=LOGGERS)
    if not args.recordings.is_dir():
        log.error("recordings_missing", fix="give --recordings the var_dir's recordings folder")
        return 2
    written, same, refused = write_manifests(
        args.recordings, args.out, consent_version=args.consent_version
    )
    log.info("manifests_done", written=written, unchanged=same, refused=refused)
    return 1 if refused else 0


if __name__ == "__main__":
    sys.exit(main())

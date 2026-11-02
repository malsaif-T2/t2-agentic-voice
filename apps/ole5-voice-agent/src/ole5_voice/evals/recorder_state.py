"""What `poe record` holds, writes and serves; `recorder.py` reads it at start and serves it.

The allow-list: the replies `replies.json` names, every take below `--out`, and the golden-set
variants whose files the manifests name below the `--audio` roots given. Each file is found by
an ID, never by a path a request gives, and sent only when no link leads to it, its bytes are
WAV, and they match the SHA-256 recorded for them, so no other file below a served folder (a
`.env` among them) is ever sent. The recorder writes only new files below `--out`, each named by
`takes.py`, never replacing one: the session's consent, each take and its sidecar, each review.

A review pass is one run of `poe record`, numbered one past the highest pass below `--out`, and
a take or a variant has at most one review a pass (its file's name says so), so a text the owner
types comes back for its own check in a later pass, against that text (Q9 of plan 002).
"""

from __future__ import annotations

import base64
import binascii
import contextlib
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from http import HTTPStatus
from pathlib import Path
from typing import Annotated, Any, Final, Literal

from pydantic import AfterValidator, ConfigDict, Field, ValidationError

from ole5_voice.evals.audio import AudioFormatError, parse_wav, sha256_of
from ole5_voice.evals.models import Consent, Device, Model, Name, RelativePath, TurnEnds, is_name
from ole5_voice.evals.takes import (
    Review,
    Script,
    ScriptLine,
    SessionRecord,
    TakeSidecar,
    TrackSettings,
    review_file,
    session_file,
    take_audio,
    take_sidecar,
)

MAX_BODY: Final = 16 * 1024 * 1024  # a take of about six minutes, as base64 in JSON


class RecorderError(Exception):
    """The recorder cannot start: the message says why, and what to give instead."""


class RefusedError(Exception):
    """A request the recorder turns away: its status and a fixed message, never the value."""

    def __init__(self, status: HTTPStatus, message: str) -> None:
        super().__init__(message)
        self.status = status


def _wav_beside(value: str) -> str:
    if "/" in value or not value.endswith(".wav"):
        raise ValueError("a reply's file is a .wav file beside replies.json")
    return value


class Reply(Model):
    """One agent reply in `replies.json`: what the page shows of it, and its file's name."""

    model_config = ConfigDict(frozen=True, extra="ignore", hide_input_in_errors=True)

    id: Name
    lang: str = ""
    topic: str = ""
    ms: int = Field(default=0, ge=0)
    file: Annotated[RelativePath, AfterValidator(_wav_beside)]


class ConsentUpload(Model):
    """The page's consent form: who speaks, and their agreement in their words."""

    speaker: str = Field(min_length=1, max_length=200)
    words: str = Field(min_length=1, max_length=4000)
    agreed: Literal[True]


class TakeUpload(Model):
    """One take from the page: its WAV file as base64, and what its sidecar records."""

    line: Name
    microphone: str = Field(max_length=500)
    output: str = Field(default="", max_length=500)
    track: TrackSettings
    turn_ends_ms: TurnEnds = ()
    status: Literal["kept", "discarded"]
    audio: str


class ReviewUpload(Model):
    """One check from the review mode: confirmed as it reads, or what it says, typed."""

    id: Name
    verdict: Literal["confirmed", "typed"]
    text: str = Field(default="", max_length=4000)


@dataclass(frozen=True)
class Audio:
    """An allow-listed file: its folder (resolved), its path below it, and its SHA-256 if one
    is recorded."""

    root: Path
    path: str
    sha256: str | None = None


@dataclass
class Entry:
    """One recording to check: a kept take below `--out`, or a golden-set variant."""

    id: str
    session: str
    of: str  # its script line or its item
    kind: str
    language: str
    reference: str
    source: str  # "script", "typed" or "none"
    audio: tuple[Audio, ...]
    reviews: list[Review] = field(default_factory=list)


def local_now() -> datetime:
    return datetime.now().astimezone()


@dataclass
class Recorder:
    """What the page reads and writes: the script, the replies, and the files below `--out`."""

    out: Path  # resolved
    script: Script
    session: str | None = None
    device: Device | None = None
    replies_dir: Path | None = None
    replies: dict[str, Reply] = field(default_factory=dict)
    consent: SessionRecord | None = None
    takes: dict[str, TakeSidecar] = field(default_factory=dict)
    entries: dict[str, Entry] = field(default_factory=dict)
    review_pass: int = 1
    skipped: list[str] = field(default_factory=list)  # takes and variants left out, and why
    clock: Callable[[], datetime] = local_now
    lock: threading.Lock = field(default_factory=threading.Lock)

    @property
    def lines(self) -> dict[str, ScriptLine]:
        return {line.id: line for line in self.script.lines}

    def state(self) -> dict[str, Any]:
        """Everything the page shows, as JSON."""
        with self.lock:
            return {
                "session": self.session,
                "device": self.device,
                "consent": self.consent.consent.model_dump(mode="json") if self.consent else None,
                "review_pass": self.review_pass,
                "lines": [line.model_dump(mode="json") for line in self.script.lines],
                "replies": [
                    r.model_dump(mode="json", exclude={"file"}) for r in self.replies.values()
                ],
                "takes": [
                    take.model_dump(mode="json", include={"take", "line", "status", "seconds"})
                    for take in self.takes.values()
                    if take.session == self.session
                ],
                "review": [self._shown(entry) for entry in self.entries.values()],
            }

    def _shown(self, entry: Entry) -> dict[str, Any]:
        typed = [r for r in entry.reviews if r.verdict == "typed"]
        last = max(entry.reviews, key=lambda r: r.review_pass, default=None)
        this_pass = any(r.review_pass == self.review_pass for r in entry.reviews)
        return {
            "id": entry.id,
            "of": entry.of,
            "kind": entry.kind,
            "language": entry.language,
            "reference": max(typed, key=lambda r: r.review_pass).text if typed else entry.reference,
            "source": "typed" if typed else entry.source,
            "segments": len(entry.audio),
            "reviews": [
                r.model_dump(mode="json", include={"review_pass", "verdict"}) for r in entry.reviews
            ],
            "due": not this_pass and (last is None or last.verdict == "typed"),
        }

    def add_consent(self, upload: ConsentUpload) -> dict[str, Any]:
        session, device = self._recording()
        consent = Consent(
            speaker=upload.speaker, agreed=True, on=self.clock().date(), words=upload.words
        )
        record = SessionRecord(session=session, device=device, consent=consent)
        with self.lock:
            self._write(session_file(session), _json(record))
            self.consent = record
        return {"file": session_file(session)}

    def add_take(self, upload: TakeUpload) -> dict[str, Any]:
        session, device = self._recording()
        if self.consent is None:
            raise RefusedError(
                HTTPStatus.CONFLICT, "the speaker's consent comes before the first take"
            )
        line = self.lines.get(upload.line)
        if line is None:
            raise RefusedError(HTTPStatus.NOT_FOUND, "the script has no such line")
        try:
            data = base64.b64decode(upload.audio, validate=True)
            wav = parse_wav(data)
        except binascii.Error:
            raise RefusedError(HTTPStatus.BAD_REQUEST, "the take's audio is not base64") from None
        except AudioFormatError as error:
            raise RefusedError(HTTPStatus.BAD_REQUEST, f"the take is refused: {error}") from None
        if upload.turn_ends_ms and upload.turn_ends_ms[-1] > wav.milliseconds:
            raise RefusedError(HTTPStatus.BAD_REQUEST, "a turn end lies past the take's end")
        if upload.status == "kept" and len(line.say) > 1 and not upload.turn_ends_ms:
            raise RefusedError(
                HTTPStatus.BAD_REQUEST, "a kept take of several clauses needs its turn ends"
            )
        with self.lock:
            take = self._new_take(line.id, session)
            sidecar = TakeSidecar(
                take=take,
                line=line.id,
                session=session,
                device=device,
                microphone=upload.microphone,
                output=upload.output,
                track=upload.track,
                recorded_at=self.clock(),
                file=f"{take}.wav",
                sha256=wav.sha256,
                seconds=wav.seconds,
                turn_ends_ms=upload.turn_ends_ms,
                status=upload.status,
            )
            self._write(take_audio(session, take), data)
            self._write(take_sidecar(session, take), _json(sidecar))
            self.takes[take] = sidecar
            if sidecar.status == "kept":
                self.entries[take] = take_entry(self.out, sidecar, line)
        return {"take": take, "status": sidecar.status}

    def add_review(self, upload: ReviewUpload) -> dict[str, Any]:
        text = upload.text.strip()
        if (upload.verdict == "typed") != bool(text):
            raise RefusedError(
                HTTPStatus.BAD_REQUEST, "a typed check holds the text, a confirmation none"
            )
        with self.lock:
            entry = self.entries.get(upload.id)
            if entry is None:
                raise RefusedError(HTTPStatus.NOT_FOUND, "no such take or variant to check")
            review = Review(
                take=entry.id,
                review_pass=self.review_pass,
                at=self.clock(),
                verdict=upload.verdict,
                text=text,
            )
            self._write(review_file(entry.session, entry.id, self.review_pass), _json(review))
            entry.reviews.append(review)
        return self._shown(entry)

    def reply(self, name: str) -> bytes:
        reply = self.replies.get(name)
        if reply is None or self.replies_dir is None:
            raise RefusedError(HTTPStatus.NOT_FOUND, "no such reply")
        return _wav_file(Audio(self.replies_dir, reply.file))

    def take(self, name: str) -> bytes:
        sidecar = self.takes.get(name)
        if sidecar is None:
            raise RefusedError(HTTPStatus.NOT_FOUND, "no such take")
        return _wav_file(Audio(self.out, take_audio(sidecar.session, sidecar.take), sidecar.sha256))

    def variant(self, name: str, segment: int) -> bytes:
        entry = self.entries.get(name)
        if entry is None or segment >= len(entry.audio):
            raise RefusedError(HTTPStatus.NOT_FOUND, "no such variant")
        return _wav_file(entry.audio[segment])

    def _recording(self) -> tuple[str, Device]:
        if self.session is None or self.device is None:
            raise RefusedError(
                HTTPStatus.CONFLICT, "this recorder only reviews: give --session and --device"
            )
        return self.session, self.device

    def _new_take(self, line: str, session: str) -> str:
        """The first take name of this line and session that names no file yet."""
        n = 0
        while True:
            n += 1
            take = f"{line}-{session}-{n}"
            names: tuple[str, ...] = ()
            with contextlib.suppress(ValidationError):  # a take named as a device is, on Windows
                names = (take_audio(session, take), take_sidecar(session, take))
            if not names or not is_name(take):
                raise RefusedError(
                    HTTPStatus.BAD_REQUEST, "the line's and session's names are too long"
                )
            if take not in self.takes and not any((self.out / name).exists() for name in names):
                return take

    def _write(self, rel: str, data: bytes) -> None:
        """A new file below `--out`, never replacing one, and never through a link."""
        path = self.out / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.parent.resolve() != path.parent:
            raise RefusedError(
                HTTPStatus.CONFLICT,
                "a folder below --out is a link; the recorder writes only into plain folders",
            )
        try:
            with path.open("xb") as file:
                file.write(data)
        except FileExistsError:
            raise RefusedError(
                HTTPStatus.CONFLICT, "that file is below --out already, and is never replaced"
            ) from None


def _json(model: Model) -> bytes:
    return model.model_dump_json(indent=2).encode() + b"\n"


def take_entry(out: Path, take: TakeSidecar, line: ScriptLine) -> Entry:
    return Entry(
        id=take.take,
        session=take.session,
        of=line.id,
        kind=line.kind,
        language=line.language,
        reference=line.text,
        source="script" if line.say else "none",
        audio=(Audio(out, take_audio(take.session, take.take), take.sha256),),
    )


def _wav_file(audio: Audio) -> bytes:
    """An allow-listed file's bytes, or RefusedError: never through a link (a symbolic link or a
    junction anywhere below its folder), never bytes that are not WAV, never other bytes than
    the SHA-256 recorded for it (which a hard link to another file cannot match)."""
    path = audio.root / audio.path
    try:
        if path.resolve(strict=True) != path or not path.is_file():
            raise RefusedError(HTTPStatus.NOT_FOUND, "no such file")
        data = path.read_bytes()
    except OSError:
        raise RefusedError(HTTPStatus.NOT_FOUND, "no such file") from None
    if data[:4] != b"RIFF" or data[8:12] != b"WAVE" or audio.sha256 not in (None, sha256_of(data)):
        raise RefusedError(HTTPStatus.CONFLICT, "the file is not the one recorded for it")
    return data

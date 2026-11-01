"""The golden set's shared models: the shapes every part of Ole5's evaluation reads and writes.

The items and their variants, the manifests of the audio (never the audio itself, D-022), the
script the owner records from with the recorder's take sidecars and reviews, and what a run
produces (answers, a variant's result, a scorecard, a history line); and the protocols one part
calls in another (the answerer, the matcher, the scorecard writer). Every model is read-only
and parses strictly, so a file with a misspelt or missing field fails as it is read (GP-06).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime
from pathlib import Path, PurePosixPath
from typing import Annotated, Literal, Protocol

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints

Sha256 = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
# An item's, a variant's, a take's, a root's or a session's name.
Name = Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9_.-]{0,127}$")]
# An item's kind: `request`, `stop_word`, `listening_sound`, ... (never a reference's words).
Kind = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z_]{0,63}$")]
Commit = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{7,40}\+?$")]
Language = Literal["saudi", "msa", "english", "mixed", "none"]
Device = Literal["laptop", "wired", "bluetooth"]  # the microphone used
Split = Literal["dev", "held-out"]
# How one request ended: answered, a provider's failure (the library's ProviderError kinds), or
# still running at the variant's wall-clock limit.
Outcome = Literal[
    "ok", "rate_limited", "timeout", "connection_lost", "server_error", "rejected", "stuck"
]


def _under_root(value: str) -> str:
    """A path below a named root: relative, with forward slashes and no `..`, so no manifest or
    request names a file outside its root."""
    path = PurePosixPath(value)
    if (
        not value
        or "\\" in value
        or ":" in value
        or path.is_absolute()
        or ".." in path.parts
        or path.as_posix() != value
    ):
        raise ValueError("must be a relative path below its root, with / and no '..'")
    return value


RelativePath = Annotated[str, AfterValidator(_under_root)]


def _increasing(value: tuple[int, ...]) -> tuple[int, ...]:
    if any(ms < 0 for ms in value) or list(value) != sorted(set(value)):
        raise ValueError("turn ends are distinct milliseconds from the take's start, in order")
    return value


TurnEnds = Annotated[tuple[int, ...], AfterValidator(_increasing)]


class _Model(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class AudioRef(_Model):
    """One audio file, named without the file: its root (given at run time as
    `--audio <root>=<folder>`), its path below the root, and its SHA-256."""

    root: Name
    path: RelativePath
    sha256: Sha256


class Confirmation(_Model):
    """One listen in which the owner confirmed that a variant says its reference."""

    at: datetime
    review_pass: int = Field(ge=1)


class Variant(_Model):
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


class Item(_Model):
    """One scripted utterance and its recordings (evaluation.md, "Items and splits here")."""

    id: Name
    source: Literal["talkover", "script"]
    kind: Kind
    language: Language
    text: str  # the scripted words; empty for an item with no speech
    alternatives: tuple[str, ...] = ()  # other references accepted as right
    terms: tuple[str, ...] = ()  # the product terms it holds, for term recall
    variants: tuple[Variant, ...] = Field(min_length=1)


class Consent(_Model):
    """A speaker's agreement that their recordings are used in this golden set."""

    speaker: str = Field(min_length=1)
    agreed: Literal[True]
    on: date
    words: str = Field(min_length=1)  # what the speaker confirmed, in their words


class ManifestFile(_Model):
    """One audio file: its path below the manifest's root, its hash and its format."""

    path: RelativePath
    sha256: Sha256
    seconds: float = Field(gt=0)
    sample_rate: int = Field(gt=0)
    device: Device
    session: Name


class Manifest(_Model):
    """The audio files below one named root: their paths and hashes in git, never the audio."""

    root: Name
    consent: Consent | None = None  # every speaker of the new recordings agreed
    files: tuple[ManifestFile, ...] = Field(min_length=1)


class ScriptLine(_Model):
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


class TrackSettings(_Model):
    """The microphone track's settings, as the browser reports them."""

    echo_cancellation: bool | None = None
    noise_suppression: bool | None = None
    auto_gain_control: bool | None = None
    sample_rate: int | None = None
    channel_count: int | None = None


class TakeSidecar(_Model):
    """The recorder's record of one take, beside its WAV file; neither is ever rewritten."""

    take: Name
    line: Name  # its script line
    session: Name
    device: Device
    microphone: str  # the input device's label, as the browser gives it
    output: str = ""  # the output device's label
    track: TrackSettings
    recorded_at: datetime
    file: RelativePath  # the WAV file's name, beside the sidecar
    sha256: Sha256
    seconds: float = Field(gt=0)
    turn_ends_ms: TurnEnds = ()
    status: Literal["kept", "discarded"]


class Review(_Model):
    """One check of a take in the recorder's review mode, written as a new file: the owner
    confirmed that it says its reference, or typed what it says instead."""

    take: Name
    review_pass: int = Field(ge=1)
    at: datetime
    verdict: Literal["confirmed", "typed"]
    text: str = ""  # what the owner typed


class Request(_Model):
    """One request an answerer made for a variant, and how it ended."""

    segment: int = Field(ge=0)
    attempt: int = Field(ge=1)
    latency_ms: float = Field(ge=0)
    billed_seconds: float = Field(ge=0)
    outcome: Outcome


class Window(_Model):
    """What was heard in the first `ms` of a variant's first segment."""

    ms: int = Field(gt=0)
    text: str
    reused: bool = False  # as long as the clip: the clip's own answer, not sent again


class Answer(_Model):
    """What an answerer returned for one variant."""

    variant: Name
    text: str  # the segments' transcripts, joined with a space
    language: str | None = None
    no_speech_prob: float | None = Field(default=None, ge=0, le=1)
    requests: tuple[Request, ...] = ()
    windows: tuple[Window, ...] = ()
    # An infrastructure failure, which is not an answer: left out of every rate, and listed.
    failure: Literal["provider", "stuck"] | None = None


class AnswerRequest(_Model):
    """What the runner hands an answerer for one variant."""

    segments: tuple[Path, ...] = Field(min_length=1)  # its audio files, resolved
    language: str | None  # the hint sent ("ar", "en"), from the item's label
    windows_ms: tuple[int, ...] = ()


class VariantResult(_Model):
    """One variant scored: its strata, its reference, its answer and the verdict."""

    item: Name
    variant: Name
    split: Split
    kind: Kind
    language: Language
    device: Device
    tags: tuple[Name, ...] = ()
    reference: str
    alternatives: tuple[str, ...] = ()
    answer: Answer
    right: bool | None  # None for an infrastructure failure


class Metrics(_Model):
    """The numbers of a run, or of one stratum of it; a rate is None where nothing counts."""

    variants: int = Field(ge=0)
    right: int = Field(ge=0)
    failures: int = Field(ge=0)
    accuracy: float | None = None
    wer: float | None = None
    cer: float | None = None
    term_recall: float | None = None
    id_recall: float | None = None
    silence_share: float | None = None  # of the empty-reference variants, those with output
    silence_chars: int = Field(default=0, ge=0)
    requests: int = Field(default=0, ge=0)
    retries: int = Field(default=0, ge=0)
    latency_median_ms: float | None = None
    latency_p90_ms: float | None = None
    billed_seconds: float = Field(default=0, ge=0)
    cost_usd: float = Field(default=0, ge=0)


class RunInfo(_Model):
    """What a run was: when, at which commit, with which answerer, settings and data, and why."""

    name: Name
    started_at: datetime
    commit: Commit  # with `+` when the tree was dirty
    answerer: Name
    model: str | None = None
    split: Split
    settings: dict[str, str]  # every setting resolved; a secret only as "set" or "not set"
    data_digest: Sha256
    note: str = Field(min_length=1)
    windows_ms: tuple[int, ...] = ()
    traced: bool = False


class Scorecard(_Model):
    """A run's scorecard. A held-out run's holds aggregates only, no variant."""

    run: RunInfo
    speakers: Literal["one speaker"] = "one speaker"  # the owner alone (D-006)
    complete: bool
    totals: Metrics
    breakdowns: dict[str, dict[str, Metrics]]  # by language, device, kind and split
    violations: int = Field(default=0, ge=0)
    violations_reason: str = "no hard constraint applies to speech-to-text"
    variants: tuple[VariantResult, ...] = ()


class HistoryLine(_Model):
    """One line of `history.jsonl` (evaluation.md, "Run history")."""

    time: datetime
    commit: Commit
    run: Name
    answerer: Name
    model: str | None = None
    settings: dict[str, str]
    split: Split
    items: int = Field(ge=0)
    variants: int = Field(ge=0)
    accuracy: float | None
    violations: int = Field(ge=0)
    billed_seconds: float = Field(ge=0)
    cost_usd: float = Field(ge=0)
    latency_median_ms: float | None
    breakdowns: dict[str, dict[str, float | None]]  # each stratum's accuracy
    scorecard: str  # the scorecard's file name
    data_digest: Sha256
    note: str = Field(min_length=1)
    complete: bool


class Answerer(Protocol):
    """Gives one variant's answer: the `reference` answerer, the `groq` one, ..."""

    name: str

    async def answer(self, variant: Variant, request: AnswerRequest) -> Answer:
        """The answer for `variant`, from its audio in `request`; a provider's failure after
        the last attempt is an answer with `failure="provider"`, not an exception."""


class Matcher(Protocol):
    """Judges an output against a variant's references, under the spelling guide."""

    def is_right(self, output: str, references: Sequence[str]) -> bool:
        """Whether `output` says one of `references` (the reference and its alternatives)."""


class ScorecardWriter(Protocol):
    """Builds a run's scorecard from its results, and writes it into the run's folder."""

    def __call__(
        self, run: RunInfo, results: Sequence[VariantResult], *, complete: bool, out: Path
    ) -> Scorecard:
        """The scorecard of `results`, also written below `out`."""

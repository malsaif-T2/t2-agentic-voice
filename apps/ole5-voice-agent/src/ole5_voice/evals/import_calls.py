"""The import of recorded calls' overlaps as golden items (plan 005's step 11, run C's calls):
`python -m ole5_voice.evals.import_calls --recordings <var_dir>/recordings --audio <folder>
--labels <labels.toml>`, reading each call folder the recorder kept (voice/session/recording.py:
`caller.wav`, `timeline.jsonl`; `call_manifests.py` commits its manifest), never writing there.

Each call's alignment is checked first, and a call whose caller's track is shifted is refused
whole, no clip cut from it (TD-070); then each turn whose speech began over a reply, or in its
tail, is an overlap (call_timeline.py says how both are read). Its clip is the caller's track
from `PAD_S` before its speech began to `PAD_S` after it stopped, written below `--audio` (never
in git) and named by the manifest `manifests/calls.json` (root `calls`); the texts that played
over it go into `overlap_replies.json`, by variant, which `poe overlap` plays the clip over.

**The owner's labels** (`--labels`, `CallLabels`; Q2 and step 11's review): what each overlap
is, by its call and turn: its kind, its language, its device, what was said (the owner's typed
words, empty for no speech, with the language `none`) and, for a stop word or a word asking the
agent to pause, its end in ms from the clip's start; or that it is left out, and why (`left_out`,
an overlap the owner heard as no one item). An overlap with no label is listed by its call and
turn and left out, as one the owner left out is, with its reason; a label of a read call's turn
that is no overlap is refused. Each
labelled overlap is an item of its own, `call-<call>-turn-<n>`, of the source `talkover` (said
over the agent), its one variant tagged `over-assistant` and `call`; its typed reference waits
for the owner's confirmation in a review (`--reviews`, the recorder's `--out`, session `calls`),
as `items.unchecked` says, before any run takes it.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

from pydantic import Field
from t2_agentic_voice import configure_logging, get_logger

from ole5_voice import LOGGERS
from ole5_voice.evals.audio import SAMPLE_RATE, sha256_of, write_wav
from ole5_voice.evals.call_timeline import Overlap, check_alignment, overlaps, timeline
from ole5_voice.evals.import_recordings import read_reviews
from ole5_voice.evals.items import (
    EVALS,
    GOLDEN_DIR,
    MANIFESTS_DIR,
    TERMS_FILE,
    GoldenSetError,
    dump_manifest,
    holds_term,
    load_terms,
    read_json,
    read_toml,
    reviewed,
    write_text,
)
from ole5_voice.evals.models import (
    AudioRef,
    Device,
    Item,
    Kind,
    Language,
    Manifest,
    ManifestFile,
    Model,
    Name,
    Variant,
    is_name,
)
from ole5_voice.evals.toml_write import dump_item

ROOT: Final = "calls"  # the cut clips' audio root (`--audio calls=<folder>`) and session
REPLIES_FILE: Final = "overlap_replies.json"
PAD_S: Final = 0.3  # the silence kept around a clip's speech, as the talk-over's (plan 002)
TAGS: Final = ("call", "over-assistant")
HEADER: Final = (
    "Written by `python -m ole5_voice.evals.import_calls` from the recorded calls and the",
    "owner's labels: import again rather than edit.",
)
_DESCRIPTION = "Import the recorded calls' overlaps as golden-set items (writes no call's folder)."
log = get_logger(__name__)


class CallLabel(Model):
    """The owner's word on one overlap: its call and turn, and what it is."""

    call: str = Field(min_length=1, max_length=64)
    turn: int = Field(ge=0)
    kind: Kind
    language: Language
    device: Device = "laptop"
    reference: str = ""
    word_end_ms: int | None = Field(default=None, ge=0)


class LeftOut(Model):
    """An overlap the owner listened to and left out of the set, and why, in a few words."""

    call: str = Field(min_length=1, max_length=64)
    turn: int = Field(ge=0)
    reason: str = Field(min_length=1, max_length=200)


class CallLabels(Model):
    """`--labels`: one `[[overlaps]]` table for each overlap the owner labelled, and one
    `[[left_out]]` table for each the owner left out."""

    overlaps: tuple[CallLabel, ...] = ()
    left_out: tuple[LeftOut, ...] = ()


class OverlapReplies(Model):
    """`overlap_replies.json`: the texts that played over each imported variant, by its ID."""

    replies: dict[Name, tuple[str, ...]] = Field(default_factory=dict)


@dataclass
class Imported:
    """What an import found: the items, their manifest, the texts over each variant, each clip's
    WAV file by its name, the overlaps left with no label, those left out with their reasons,
    and the calls refused."""

    items: list[Item] = field(default_factory=list)
    files: list[ManifestFile] = field(default_factory=list)
    replies: dict[str, tuple[str, ...]] = field(default_factory=dict)
    clips: dict[str, bytes] = field(default_factory=dict)
    unlabelled: list[tuple[str, int]] = field(default_factory=list)
    left_out: list[tuple[str, int, str]] = field(default_factory=list)
    refused: list[str] = field(default_factory=list)


def item_id(call: str, turn: int) -> str:
    """An overlap's item and variant ID; GoldenSetError for a call ID it cannot name."""
    found = f"call-{call.lower()}-turn-{turn}"
    if not is_name(found):
        raise GoldenSetError("a call's ID that names no item: letters, digits, - and _ only")
    return found


def build(
    recordings: Path, labels: CallLabels, *, terms: Sequence[str], reviews: Path | None = None
) -> Imported:
    """The labelled overlaps of every call folder in `recordings`, as items, each with its clip
    cut from its call's caller track and the texts that played over it."""
    named = {(label.call, label.turn): label for label in labels.overlaps}
    dropped = {(drop.call, drop.turn): drop.reason for drop in labels.left_out}
    if len(named.keys() | dropped.keys()) != len(labels.overlaps) + len(labels.left_out):
        raise GoldenSetError("--labels names an overlap twice")
    found, calls, read = Imported(), set(), set()
    for folder in sorted(path for path in recordings.iterdir() if path.is_dir()):
        try:
            lines = timeline(folder)
            pcm16 = check_alignment(folder, lines)
        except GoldenSetError as error:
            found.refused.append(folder.name)
            log.warning("call_refused", call=folder.name, problem=str(error))
            continue
        calls.add(folder.name)
        for overlap in overlaps(lines):
            read.add((folder.name, overlap.turn))
            key = (folder.name, overlap.turn)
            if key in dropped:
                found.left_out.append((*key, dropped[key]))
                continue
            label = named.get(key)
            if label is None:
                found.unlabelled.append((folder.name, overlap.turn))
                continue
            _add(found, label, overlap, pcm16, terms, reviews)
    if stray := sorted(k for k in named.keys() | dropped.keys() if k[0] in calls and k not in read):
        raise GoldenSetError(f"--labels names turns that are no overlap: {stray}")
    return found


def _add(
    found: Imported,
    label: CallLabel,
    overlap: Overlap,
    pcm16: bytes,
    terms: Sequence[str],
    reviews: Path | None,
) -> None:
    """One labelled overlap: its clip, its item and its manifest file."""
    name = item_id(label.call, overlap.turn)
    said = " ".join(label.reference.split())
    if (label.language == "none") != (said == ""):
        raise GoldenSetError(f"{name}: an overlap of no language is exactly one with no speech")
    first = max(0, round((overlap.speech_s - PAD_S) * SAMPLE_RATE)) * 2
    clip = pcm16[first : round((overlap.stopped_s + PAD_S) * SAMPLE_RATE) * 2]
    if not clip:
        raise GoldenSetError(f"{name}: its speech lies past its call's caller track")
    wav = write_wav(clip)
    sha, path = sha256_of(wav), f"{name}.wav"
    heard = read_reviews(reviews, ROOT, name) if reviews else []
    reference, source, confirmations = reviewed(said, "typed" if said else "none", heard)
    variant = Variant(
        id=name,
        segments=(AudioRef(root=ROOT, path=path, sha256=sha),),
        device=label.device,
        session=ROOT,
        reference=reference,
        reference_source=source,
        confirmations=confirmations,
        turn_ends_ms=() if label.word_end_ms is None else (label.word_end_ms,),
        tags=TAGS,
    )
    found.items.append(
        Item(
            id=name,
            source="talkover",
            kind=label.kind,
            language=label.language,
            text="",
            terms=tuple(term for term in terms if holds_term(reference, term)),
            variants=(variant,),
        )
    )
    found.files.append(
        ManifestFile(
            path=path,
            sha256=sha,
            seconds=len(clip) / 2 / SAMPLE_RATE,
            sample_rate=SAMPLE_RATE,
            device=label.device,
            session=ROOT,
        )
    )
    found.replies[name] = overlap.reply
    found.clips[path] = wav


def write(evals: Path, audio: Path, found: Imported) -> None:
    """Each clip below `audio`, never over another file; each item as `golden/<id>.toml`, never
    over another import's; the manifest `manifests/calls.json`; and `overlap_replies.json`."""
    for item in found.items:
        path = evals / GOLDEN_DIR / f"{item.id}.toml"
        if path.is_file() and "call" not in read_toml(path, Item).variants[0].tags:
            raise GoldenSetError(f"{path.name}: an item of another import has this ID")
    for name, wav in found.clips.items():
        target = audio / name
        if target.exists() and target.read_bytes() != wav:
            raise GoldenSetError(f"{name}: another file of this name is below --audio")
    for name, wav in found.clips.items():
        (audio / name).write_bytes(wav)
    for item in found.items:
        write_text(evals / GOLDEN_DIR / f"{item.id}.toml", dump_item(item, comments=HEADER))
    if found.files:
        manifest = Manifest(root=ROOT, files=tuple(sorted(found.files, key=lambda f: f.path)))
        write_text(evals / MANIFESTS_DIR / f"{ROOT}.json", dump_manifest(manifest))
    replies = OverlapReplies(replies=dict(sorted(found.replies.items())))
    write_text(evals / REPLIES_FILE, replies.model_dump_json(indent=2) + "\n")


def load_replies(evals: Path) -> dict[str, tuple[str, ...]]:
    """The texts over each imported variant (`overlap_replies.json`), none when no import
    wrote it."""
    path = evals / REPLIES_FILE
    return dict(read_json(path, OverlapReplies).replies) if path.is_file() else {}


def main(argv: Sequence[str] | None = None) -> int:
    """`python -m ole5_voice.evals.import_calls`: write the labelled overlaps of the recorded
    calls as items, their clips and their manifest. 0 when every call was read, 1 when one was
    refused or the import was, 2 when a folder it needs is missing."""
    parser = argparse.ArgumentParser(prog="import_calls", description=_DESCRIPTION)
    add = parser.add_argument
    add("--recordings", type=Path, required=True, help="var_dir's recordings folder")
    add("--labels", type=Path, required=True, help="the owner's labels of the overlaps (TOML)")
    add("--audio", type=Path, required=True, help="the folder the cut clips are written to")
    add("--evals", type=Path, default=EVALS, help="the golden set's folder")
    add("--reviews", type=Path, help="the recorder's --out, for the owner's reviews")
    args = parser.parse_args(argv)
    configure_logging(loggers=LOGGERS)
    if not args.recordings.is_dir() or not args.audio.is_dir():
        log.error("folder_missing", fix="give --recordings and --audio existing folders")
        return 2
    try:
        labels = read_toml(args.labels, CallLabels)
        found = build(
            args.recordings,
            labels,
            terms=load_terms(args.evals / TERMS_FILE),
            reviews=args.reviews,
        )
        write(args.evals, args.audio, found)
    except GoldenSetError as error:
        log.error("calls_not_imported", problem=str(error))
        return 1
    for call, turn in found.unlabelled:
        log.info("overlap_left_out", call=call, turn=turn, reason="no label")
    for call, turn, reason in found.left_out:
        log.info("overlap_left_out", call=call, turn=turn, reason=reason)
    log.info("calls_imported", items=len(found.items), refused=len(found.refused))
    return 1 if found.refused else 0


if __name__ == "__main__":
    sys.exit(main())

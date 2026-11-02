"""The import of the prototype's 124 talk-over segments as items, read in place (D-010).

It reads the lab's `refs.json` (one entry a segment) and `takes.json` (one entry a take) as
data, and each segment's WAV file for its hash, length and format, and writes only into this
repository: one item a phrase under `evals/golden/`, its takes as variants, and the manifest
`evals/manifests/talkover.json`, never the audio. A take the lab's detector split in two is one
variant, its segments in order (plan 002's decision log); a take with no segment is left out
and listed, and so is a take the owner left out after the review (`LEFT_OUT`). Every take was
captured by the laptop's microphone array, so the device is the laptop's; the condition,
whether the take began over the assistant, and the playback device are the variant's tags.
Given the recorder's `--out` as `--reviews`, the owner's reviews of each variant become its
confirmations, as for the new recordings.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter
from t2_agentic_voice import configure_logging, get_logger

from ole5_voice.evals.audio import AudioFormatError, Wav, read_wav
from ole5_voice.evals.files import read_model
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
    reviewed,
    write_text,
)
from ole5_voice.evals.models import (
    AudioRef,
    Item,
    Language,
    Manifest,
    ManifestFile,
    Name,
    ReferenceSource,
    RelativePath,
    Variant,
)
from ole5_voice.evals.toml_write import dump_item

log = get_logger(__name__)
ROOT: Final = "talkover"
_DESCRIPTION = (
    "Import the talk-over segments as golden-set items (writes only into this repository)."
)
# The lab's kinds as the golden set's (a kind never holds a reference's words); the lab's
# `request` is a repeat request or a short one, by its `want` label.
_KINDS: Final = {
    "sentence": "request",
    "unscripted": "request",
    "backchannel": "listening_sound",
    "command": "stop_word",
    "confirm": "confirmation",
}
# The dialect of each Arabic phrase: the agent's proposal from its text, each confirmed by the
# owner on 2026-11-01 (plan 002, Q7). `mixed` is Arabic with an English product term.
LANGUAGE: Final[Mapping[str, Language]] = {
    "b01_tamam": "saudi",
    "b02_eh": "saudi",
    "b03_aha": "saudi",
    "b04_tayyib": "saudi",
    "b05_aywa": "saudi",
    "b06_umm": "saudi",
    "b07_tamam_tamam": "saudi",
    "b08_kammil": "saudi",
    "k01_wagif": "saudi",
    "k02_khalas": "saudi",
    "k03_tawaqqaf": "msa",
    "k04_lahza": "saudi",
    "r01_muwazzaf": "saudi",
    "r02_ghalat": "saudi",
    "r03_repeat": "saudi",
    "r04_how_send": "msa",
    "s01_archive": "msa",
    "s02_inbox_morning": "saudi",
    "s03_signature_outlook": "mixed",
    "s04_pdf": "mixed",
    "s05_password": "msa",
    "s06_pause_error": "saudi",
    "s07_refer": "saudi",
    "s08_archived_where": "saudi",
    "s09_restore_deleted": "msa",
    "s10_mobile_notifications": "saudi",
    "s11_word_size": "mixed",
    "s12_language": "mixed",
    "u01_signature": "saudi",
    "u02_attachment": "saudi",
    "u03_ticket": "saudi",
    "y01_naam_irsilha": "msa",
    "y02_eh_irsilha": "saudi",
    "y04_naam": "msa",
}
# The takes the owner left out on 2026-11-01, after the review (plan 002): each clip was cut off
# at its start, so what is left of its listening sound is on no list a reference may use.
LEFT_OUT: Final[Mapping[str, str]] = {
    "b01_tamam__pause__speakers__184025": "cut off at its start",
    "b07_tamam_tamam__pause__speakers__184714": "cut off at its start",
}
HEADER: Final = (
    "Written by `python -m ole5_voice.evals.import_talkover` from the lab's refs.json and",
    "takes.json: import again rather than edit.",
)

Describe = Callable[[Path], Wav]


class _Lab(BaseModel):
    """The fields of the lab's records the import reads; it ignores the rest."""

    model_config = ConfigDict(frozen=True, extra="ignore", hide_input_in_errors=True)

    phrase_id: Name
    take: Name
    text: str
    lang: Literal["ar", "en"]
    kind: Literal["sentence", "unscripted", "backchannel", "command", "confirm", "request"]
    want: Name
    condition: Name
    device: Literal["speakers", "headset"]


class LabSegment(_Lab):
    """One entry of `refs.json`: a segment file and the take it was cut from."""

    segment_index: int = Field(ge=1)
    segments_in_take: int = Field(ge=1)
    over_bot: bool  # it began while the assistant was playing


class LabTake(_Lab):
    """One entry of `takes.json`: a take and its segment files, in order."""

    recorded_at: datetime
    segments: tuple[RelativePath, ...]


_REFS: Final = TypeAdapter(dict[str, LabSegment])
_TAKES: Final = TypeAdapter(dict[str, LabTake])


def _read[T](path: Path, shape: TypeAdapter[T]) -> T:
    """A lab file, whose records hold transcripts: its refusal names fields only."""
    return read_model(path, shape, lambda problem: GoldenSetError(f"{path.name}: {problem}"))


def _segments(take: LabTake, refs: Mapping[str, LabSegment]) -> list[LabSegment]:
    """The take's segments from `refs.json`, each agreeing with the take, in their order."""
    found = []
    for index, name in enumerate(take.segments, start=1):
        segment = refs.get(name)
        same = ("phrase_id", "take", "text", "lang", "kind", "want", "condition", "device")
        if (
            "/" in name
            or segment is None
            or any(getattr(segment, f) != getattr(take, f) for f in same)
            or (segment.segment_index, segment.segments_in_take) != (index, len(take.segments))
        ):
            raise GoldenSetError(f"refs.json and takes.json disagree on the segment {name}")
        found.append(segment)
    return found


def _kind(take: LabTake) -> str:
    if take.kind == "request":
        return "repeat_request" if take.want == "repeat" else "short_request"
    return _KINDS[take.kind]


def _terms(texts: Sequence[str], terms: Sequence[str]) -> tuple[str, ...]:
    """The product terms the texts hold, each as a whole word and as the product writes it."""
    return tuple(term for term in terms if any(holds_term(text, term) for text in texts))


def build(
    lab: Path,
    *,
    terms: Sequence[str],
    describe: Describe,
    reviews: Path | None = None,
    left_out: Mapping[str, str] | None = None,
) -> tuple[list[Item], Manifest, list[str]]:
    """The talk-over items, their manifest, and the takes left out for having no segment. A take
    named in `left_out` (`LEFT_OUT`, from `main`) is left out whole, its files with it."""
    refs = _read(lab / "refs.json", _REFS)
    takes = _read(lab / "takes.json", _TAKES)
    if sorted(refs) != sorted(name for take in takes.values() for name in take.segments):
        raise GoldenSetError("refs.json and takes.json name different segment files")
    skipped = left_out or {}
    if missing := sorted(set(skipped) - {take.take for take in takes.values()}):
        raise GoldenSetError(f"no take of the lab is named {', '.join(missing)}, left out")
    files: list[ManifestFile] = []
    phrases: dict[str, list[tuple[LabTake, Variant]]] = {}
    for key, take in sorted(takes.items()):
        if key != take.take:
            raise GoldenSetError(f"takes.json files the take {take.take} under another name")
        if take.take in skipped:
            continue
        segments, session = _segments(take, refs), f"{ROOT}-{take.recorded_at.date().isoformat()}"
        refs_of_take = []
        for name in take.segments:
            try:
                wav = describe(lab / name)
            except (OSError, AudioFormatError) as error:
                raise GoldenSetError(f"{name}: {error}") from None
            refs_of_take.append(AudioRef(root=ROOT, path=name, sha256=wav.sha256))
            files.append(
                ManifestFile(
                    path=name,
                    sha256=wav.sha256,
                    seconds=wav.seconds,
                    sample_rate=wav.sample_rate,
                    device="laptop",
                    session=session,
                )
            )
        if not segments:
            continue
        source: ReferenceSource = "typed" if take.kind == "unscripted" else "script"
        heard = read_reviews(reviews, session, take.take) if reviews else []
        reference, source, confirmations = reviewed(" ".join(take.text.split()), source, heard)
        tags = {take.condition, f"playback-{take.device}"}
        if segments[0].over_bot:
            tags.add("over-assistant")
        variant = Variant(
            id=take.take,
            segments=tuple(refs_of_take),
            device="laptop",
            session=session,
            reference=reference,
            reference_source=source,
            confirmations=confirmations,
            tags=tuple(sorted(tags)),
        )
        phrases.setdefault(take.phrase_id, []).append((take, variant))
    items = [_item(phrase, found, terms) for phrase, found in sorted(phrases.items())]
    manifest = Manifest(root=ROOT, files=tuple(sorted(files, key=lambda f: f.path)))
    return items, manifest, sorted(t.take for t in takes.values() if not t.segments)


def _item(phrase: str, found: list[tuple[LabTake, Variant]], terms: Sequence[str]) -> Item:
    first = found[0][0]
    if len({(t.text, t.lang, t.kind, t.want) for t, _ in found if t.kind != "unscripted"}) > 1:
        raise GoldenSetError(f"the takes of {phrase} disagree on their phrase")
    if first.lang == "en":
        language: Language = "english"
    elif phrase in LANGUAGE:
        language = LANGUAGE[phrase]
    else:
        raise GoldenSetError(f"no language is given for the Arabic phrase {phrase}")
    text = "" if first.kind == "unscripted" else " ".join(first.text.split())
    variants = tuple(v for _, v in found)
    return Item(
        id=phrase,
        source="talkover",
        kind=_kind(first),
        language=language,
        text=text,
        terms=_terms([text, *(v.reference for v in variants)], terms),
        want=first.want,
        variants=variants,
    )


def write(evals: Path, items: Sequence[Item], manifest: Manifest) -> None:
    """Each item as `golden/<id>.toml`, and the manifest as `evals/manifests/talkover.json`: only
    the files the import owns."""
    for item in items:
        write_text(evals / GOLDEN_DIR / f"{item.id}.toml", dump_item(item, comments=HEADER))
    write_text(evals / MANIFESTS_DIR / f"{ROOT}.json", dump_manifest(manifest))


def main(argv: Sequence[str] | None = None) -> int:
    """`python -m ole5_voice.evals.import_talkover`: write the talk-over items and manifest from
    the lab's refs.json and takes.json."""
    parser = argparse.ArgumentParser(prog="import_talkover", description=_DESCRIPTION)
    parser.add_argument("--lab", type=Path, required=True, help="the lab's talk-over folder")
    parser.add_argument("--evals", type=Path, default=EVALS, help="the golden set's folder")
    parser.add_argument("--reviews", type=Path, help="the recorder's --out, for the reviews")
    args = parser.parse_args(argv)
    configure_logging()
    try:
        terms = load_terms(args.evals / TERMS_FILE)
        items, manifest, left_out = build(
            args.lab, terms=terms, describe=read_wav, reviews=args.reviews, left_out=LEFT_OUT
        )
        write(args.evals, items, manifest)
    except GoldenSetError as error:
        log.error("talkover_not_imported", problem=str(error))
        return 1
    variants = sum(len(item.variants) for item in items)
    log.info("talkover_imported", items=len(items), variants=variants, files=len(manifest.files))
    if left_out:
        log.info("talkover_takes_left_out", reason="no segment", takes=left_out)
    for take, why in LEFT_OUT.items():
        log.info("talkover_take_left_out", take=take, reason=why, by="the owner, 2026-11-01")
    return 0


if __name__ == "__main__":
    sys.exit(main())

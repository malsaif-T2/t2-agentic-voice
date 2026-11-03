"""`poe golden`: validate every item, and freeze the expected answers into one file.

Each item is checked against the files of `evals/` (`items.py` lists them): its references
against the script or the phrase they come from, and against the spelling guide (every spelling
it rules out, every listening sound outside the script's list); its terms against `terms.toml`;
each segment against its root's manifest, and a new recording's against its speaker's consent;
the set against the committed split and the registered strata. A variant is accepted once its
reference and its independent check agree: the owner listened and confirmed it (Q9; for a typed
reference, in a later review pass). One not yet checked is left out and listed, and the frozen
answers hold only the accepted ones. Given `--audio <root>=<folder>`, every file of that root's
manifests is read, hashed and checked for its format with `audio.py`; without it no audio is
read, so the tests read none. Any problem fails the command and freezes nothing; `--check`
fails when `frozen.json` is not what the items give.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

from t2_agentic_voice import configure_logging, get_logger
from t2_agentic_voice.languages import SpellingIssue, SpellingRule, spelling_issues

from ole5_voice import LOGGERS
from ole5_voice.evals import cli
from ole5_voice.evals.audio import AudioFormatError, Wav, read_wav
from ole5_voice.evals.items import (
    EVALS,
    FROZEN_FILE,
    GOLDEN_DIR,
    MANIFESTS_DIR,
    SCRIPT_FILE,
    SPELLING_FILE,
    SPLIT_FILE,
    STRATA_FILE,
    TERMS_FILE,
    GoldenSetError,
    Strata,
    count_strata,
    holds_term,
    load_items,
    load_manifests,
    load_terms,
    read_toml,
    references,
    unchecked,
    write_text,
)
from ole5_voice.evals.matcher import LISTENING_SOUNDS_RULING, GuideError, SpellingGuide, load_guide
from ole5_voice.evals.models import Item, Manifest, ManifestFile, SplitFile, Variant
from ole5_voice.evals.split import load_split
from ole5_voice.evals.takes import Script

log = get_logger(__name__)
_DESCRIPTION = "Validate the golden set's items and freeze their expected answers."
ABOUT: Final = (
    "The golden set's expected answers, frozen by `uv run poe golden` from the items in "
    "golden/: each accepted variant's references (its own and its item's alternatives), and "
    "the variants left out until the owner's check. Never edited by hand: a changed item shows "
    "as a diff of this file, reviewed like code."
)
# How far a manifest's length may be from the file's, in seconds: under a sample at 16 kHz.
_SECONDS: Final = 1e-4

SpellingCheck = Callable[[str, Sequence[SpellingRule]], list[SpellingIssue]]
Read = Callable[[Path], Wav]


@dataclass
class Report:
    """What `validate` found: the problems that fail the set, the variants left out, and the
    frozen answers' text."""

    problems: list[str] = field(default_factory=list)
    left_out: list[tuple[str, str, str]] = field(default_factory=list)  # item, variant, why
    frozen: str = ""
    audio_files: int = 0


@dataclass(frozen=True)
class _Set:
    items: tuple[Item, ...]
    manifests: tuple[Manifest, ...]
    guide: SpellingGuide
    terms: tuple[str, ...]
    script: Script
    split: SplitFile
    strata: Strata


def _load(evals: Path) -> _Set:
    try:
        guide = load_guide(evals / SPELLING_FILE)
        guide.ruling(LISTENING_SOUNDS_RULING)  # `poe golden` applies it
    except GuideError as error:
        raise GoldenSetError(str(error)) from None
    return _Set(
        items=load_items(evals / GOLDEN_DIR),
        manifests=load_manifests(evals / MANIFESTS_DIR),
        guide=guide,
        terms=load_terms(evals / TERMS_FILE),
        script=read_toml(evals / SCRIPT_FILE, Script),
        split=load_split(evals / SPLIT_FILE),
        strata=read_toml(evals / STRATA_FILE, Strata),
    )


def _check_item(item: Item, found: _Set, check: SpellingCheck) -> list[str]:
    """The item's problems: its references, terms and spellings."""
    problems = []
    line = next((line for line in found.script.lines if line.id == item.id), None)
    if item.source == "script":
        if line is None:
            return [f"{item.id}: the script has no line of this ID"]
        same = (line.kind, line.language, line.text, line.terms)
        if same != (item.kind, item.language, item.text, item.terms):
            problems.append(f"{item.id}: its kind, language, text or terms are not its line's")
    for variant in item.variants:
        name = f"{item.id}/{variant.id}"
        if (variant.reference_source == "none") != (variant.reference == ""):
            problems.append(f"{name}: an empty reference is exactly one with no speech")
        if variant.reference_source == "script" and variant.reference != item.text:
            problems.append(f"{name}: its reference is not its item's scripted text")
        if (item.language == "none") != (variant.reference == ""):
            problems.append(f"{name}: an item of no language is exactly one with no speech")
        sounds = found.script.listening_sounds
        if item.kind == "listening_sound" and variant.reference not in sounds:
            ruling = LISTENING_SOUNDS_RULING
            problems.append(f"{name}: a listening sound outside the script's list ({ruling})")
    texts = [item.text, *(v.reference for v in item.variants)]
    for term in item.terms:
        if term not in found.terms or not any(holds_term(text, term) for text in texts):
            problems.append(f"{item.id}: the term {term} is not in terms.toml or not in its text")
    rules = found.guide.rules_for(item.kind)
    spelled = {(v.id, text) for v in item.variants for text in (v.reference, *item.alternatives)}
    for variant_id, text in sorted(spelled):
        for issue in check(text, rules):
            problems.append(
                f"{item.id}/{variant_id}: holds '{issue.found}', which the spelling guide's "
                f"{issue.rule} rules out: write {issue.write}"
            )
    return problems


def _check_segments(found: _Set) -> list[str]:
    """Every segment named by its root's manifest with its hash, device and session, a new
    recording's beside its speaker's consent; every manifest file named by one segment."""
    files: dict[tuple[str, str], tuple[Manifest, ManifestFile]] = {
        (m.root, f.path): (m, f) for m in found.manifests for f in m.files
    }
    used: Counter[tuple[str, str]] = Counter()
    problems = []
    for item in found.items:
        for variant in item.variants:
            for segment in variant.segments:
                key = (segment.root, segment.path)
                used[key] += 1
                manifest, file = files.get(key, (None, None))
                name = f"{item.id}/{variant.id}: {segment.root}:{segment.path}"
                if manifest is None or file is None:
                    problems.append(f"{name} is in no manifest")
                    continue
                if (file.sha256, file.device, file.session) != (
                    segment.sha256,
                    variant.device,
                    variant.session,
                ):
                    problems.append(f"{name}: its hash, device or session is not its manifest's")
                if item.source == "script" and manifest.consent is None:
                    problems.append(f"{name}: a new recording whose manifest holds no consent")
    for key in sorted(files):
        if used[key] != 1:
            problems.append(f"{key[0]}:{key[1]}: named by {used[key]} segments, not one")
    return problems


def _check_set(found: _Set) -> list[str]:
    problems = []
    ids = {item.id for item in found.items}
    if set(found.split.items) != ids:
        problems.append("split.json does not name exactly the items: run the split again")
    counted = count_strata(found.items, found.script)
    for part in ("items", "variants", "script"):
        if getattr(counted, part) != getattr(found.strata, part):
            problems.append(f"strata.toml: the {part} do not hold their registered counts")
    return problems


def _check_audio(found: _Set, audio: Mapping[str, Path], read: Read) -> tuple[list[str], int]:
    """Each file of each given root: below its folder, readable, 16 kHz mono 16-bit, and with
    the manifest's hash and length."""
    problems, checked = [], 0
    roots = {m.root for m in found.manifests}
    for root, folder in sorted(audio.items()):
        if root not in roots:
            problems.append(f"--audio {root}: no manifest names this root")
            continue
        base = folder.resolve()
        for manifest in (m for m in found.manifests if m.root == root):
            for file in manifest.files:
                name = f"{root}:{file.path}"
                path = (base / file.path).resolve()
                if not path.is_relative_to(base):
                    problems.append(f"{name}: leads outside its root's folder")
                    continue
                try:
                    wav = read(path)
                except (OSError, AudioFormatError) as error:
                    problems.append(f"{name}: {type(error).__name__}: {error}")
                    continue
                checked += 1
                if (wav.sha256, wav.sample_rate) != (file.sha256, file.sample_rate) or not (
                    math.isclose(wav.seconds, file.seconds, abs_tol=_SECONDS)
                ):
                    problems.append(f"{name}: its hash, rate or length is not its manifest's")
    return problems, checked


def _frozen(
    found: _Set, accepted: Mapping[str, Sequence[Variant]], left_out: list[tuple[str, str, str]]
) -> str:
    items = [
        {
            "id": item.id,
            "split": found.split.items.get(item.id),
            "kind": item.kind,
            "language": item.language,
            "want": item.want,
            "terms": list(item.terms),
            "variants": [
                {"id": v.id, "device": v.device, "expected": list(references(item, v))}
                for v in accepted[item.id]
            ],
        }
        for item in found.items
        if accepted[item.id]
    ]
    variants = sum(len(found) for found in accepted.values())
    frozen = {
        "about": ABOUT,
        "accepted": {"items": len(items), "variants": variants},
        "items": items,
        "left_out": [{"item": i, "variant": v, "why": why} for i, v, why in left_out],
    }
    return json.dumps(frozen, ensure_ascii=False, indent=2) + "\n"


def validate(
    evals: Path,
    *,
    check: SpellingCheck,
    audio: Mapping[str, Path] | None = None,
    read: Read = read_wav,
) -> Report:
    """Every check of the set in `evals`; `check` is the spelling check (`spelling_issues`) and
    `read` reads one audio file, for the roots in `audio` only."""
    report = Report()
    try:
        found = _load(evals)
    except GoldenSetError as error:
        report.problems.append(str(error))
        return report
    for item in found.items:
        report.problems += _check_item(item, found, check)
    report.problems += _check_segments(found) + _check_set(found)
    audio_problems, report.audio_files = _check_audio(found, audio or {}, read)
    report.problems += audio_problems
    accepted: dict[str, list[Variant]] = {}
    for item in found.items:
        accepted[item.id] = []
        for variant in item.variants:
            why = unchecked(variant)
            if why is None:
                accepted[item.id].append(variant)
            else:
                report.left_out.append((item.id, variant.id, why))
    report.frozen = _frozen(found, accepted, report.left_out)
    return report


def main(argv: Sequence[str] | None = None) -> int:
    """`uv run poe golden`: validate the golden set and freeze its expected answers."""
    parser = argparse.ArgumentParser(prog="poe golden", description=_DESCRIPTION)
    parser.add_argument("--evals", type=Path, default=EVALS, help="the golden set's folder")
    parser.add_argument(
        "--audio",
        type=cli.audio_root_type,
        action="append",
        default=[],
        metavar="ROOT=FOLDER",
        help="also check every audio file of a root (talkover, owner) in its folder",
    )
    parser.add_argument("--check", action="store_true", help="fail if frozen.json is stale")
    args = parser.parse_args(argv)
    try:
        audio = cli.audio_roots(args.audio)
    except ValueError as error:
        parser.error(str(error))
    configure_logging(loggers=LOGGERS)
    report = validate(args.evals, check=spelling_issues, audio=audio, read=read_wav)
    for item, variant, why in report.left_out:
        log.info("variant_left_out", item=item, variant=variant, why=why)
    for problem in report.problems:
        log.error("golden_problem", problem=problem)
    if report.problems:
        log.error("golden_failed", problems=len(report.problems), frozen="unchanged")
        return 1
    path = args.evals / FROZEN_FILE
    if args.check:
        if not path.is_file() or path.read_text(encoding="utf-8") != report.frozen:
            log.error("frozen_stale", fix="run `uv run poe golden` and review the diff")
            return 1
    else:
        write_text(path, report.frozen)
    log.info(
        "golden_valid",
        left_out=len(report.left_out),
        audio_files=report.audio_files,
        frozen="checked" if args.check else "written",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

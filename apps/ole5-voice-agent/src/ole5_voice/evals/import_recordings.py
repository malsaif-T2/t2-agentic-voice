"""The import of the owner's new takes: their sidecars and reviews as items and manifests.

It reads what `poe record` wrote below its `--out` (`takes.py` names each file): each session's
`session.json`, whose consent goes into the session's manifest, the take sidecars and the
reviews, and the script the takes were recorded from. It never reads the audio: each file's hash
and length come from its sidecar, and `poe golden --audio` checks them against the file. A kept
take is a variant of its script line's item; a discarded one is left out. A session folder that
holds takes but no `session.json` is refused, so no recording enters the set without its
speaker's consent. A folder that holds only reviews is the reviews of variants recorded
elsewhere (the talk-over), which `import_talkover` reads.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Final

from t2_agentic_voice import configure_logging, get_logger

from ole5_voice import LOGGERS
from ole5_voice.evals import cli
from ole5_voice.evals.audio import SAMPLE_RATE
from ole5_voice.evals.items import (
    EVALS,
    GOLDEN_DIR,
    MANIFESTS_DIR,
    SCRIPT_FILE,
    GoldenSetError,
    dump_manifest,
    read_json,
    read_toml,
    reviewed,
    write_text,
)
from ole5_voice.evals.models import AudioRef, Item, Manifest, ManifestFile, Variant
from ole5_voice.evals.takes import (
    SESSION_FILE,
    Review,
    Script,
    ScriptLine,
    SessionRecord,
    TakeSidecar,
    parse_review_file,
    review_file,
    take_audio,
    take_sidecar,
)
from ole5_voice.evals.toml_write import dump_item

log = get_logger(__name__)
ROOT: Final = "owner"
_DESCRIPTION = "Import the recorder's takes as golden-set items and manifests (no audio)."
HEADER: Final = (
    "Written by `python -m ole5_voice.evals.import_recordings` from the recorder's files:",
    "import again rather than edit.",
)


def read_reviews(out: Path, session: str, take: str) -> list[Review]:
    """The owner's reviews of one take below the recorder's `--out`, each checked against the
    name `takes.review_file` gives it."""
    found = []
    for path in sorted((out / session).glob(f"{take}.review-*.json")):
        review = read_json(path, Review)
        named = parse_review_file(path.name)
        expected = review_file(session, take, review.review_pass)
        if not named or path.relative_to(out).as_posix() != expected or review.take != take:
            raise GoldenSetError(f"{path.name}: not the review its name says")
        found.append(review)
    return found


def _variant(
    out: Path, record: SessionRecord, sidecar: TakeSidecar, line: ScriptLine, root: str
) -> tuple[Variant, ManifestFile]:
    session, take = record.session, sidecar.take
    if (sidecar.session, sidecar.device, sidecar.file) != (session, record.device, f"{take}.wav"):
        raise GoldenSetError(f"{take}.json: its session, device or file is not its folder's")
    path = take_audio(session, take)
    reference, source, confirmations = reviewed(
        line.text, line.source, read_reviews(out, session, take)
    )
    variant = Variant(
        id=take,
        segments=(AudioRef(root=root, path=path, sha256=sidecar.sha256),),
        device=record.device,
        session=session,
        reference=reference,
        reference_source=source,
        confirmations=confirmations,
        turn_ends_ms=sidecar.turn_ends_ms,
    )
    file = ManifestFile(
        path=path,
        sha256=sidecar.sha256,
        seconds=sidecar.seconds,
        sample_rate=SAMPLE_RATE,  # the recorder writes no other rate (`audio.py`'s check)
        device=record.device,
        session=session,
    )
    return variant, file


def build(out: Path, script: Script, *, root: str = ROOT) -> tuple[list[Item], dict[str, Manifest]]:
    """The new recordings' items, and each session's manifest by its file's name."""
    lines = {line.id: line for line in script.lines}
    variants: dict[str, list[Variant]] = {}
    manifests: dict[str, Manifest] = {}
    for folder in sorted(p for p in out.iterdir() if p.is_dir()):
        sidecars = [p for p in sorted(folder.glob("*.json")) if p.name != SESSION_FILE]
        takes = [p for p in sidecars if not parse_review_file(p.name)]
        if not takes and not any(folder.glob("*.wav")):
            continue  # only reviews: of variants recorded elsewhere
        if not (folder / SESSION_FILE).is_file():
            raise GoldenSetError(f"{folder.name}: a session without its {SESSION_FILE} (consent)")
        record = read_json(folder / SESSION_FILE, SessionRecord)
        if record.session != folder.name:
            raise GoldenSetError(f"{folder.name}/{SESSION_FILE}: names another session")
        files, named = [], set()
        for path in takes:
            sidecar = read_json(path, TakeSidecar)
            named.add(sidecar.take)
            if path.relative_to(out).as_posix() != take_sidecar(record.session, sidecar.take):
                raise GoldenSetError(f"{path.name}: not the sidecar of the take it names")
            if sidecar.line not in lines:
                raise GoldenSetError(f"{path.name}: the script has no line {sidecar.line}")
            if sidecar.status == "kept":
                variant, file = _variant(out, record, sidecar, lines[sidecar.line], root)
                variants.setdefault(sidecar.line, []).append(variant)
                files.append(file)
        reviewed_takes = {found[0] for p in sidecars if (found := parse_review_file(p.name))}
        orphans = sorted(reviewed_takes - named)
        if orphans:
            raise GoldenSetError(f"{folder.name}: reviews of takes it does not hold: {orphans}")
        if files:
            manifests[f"{root}-{record.session}"] = Manifest(
                root=root, consent=record.consent, files=tuple(files)
            )
    items = [
        Item(
            id=line,
            source="script",
            kind=lines[line].kind,
            language=lines[line].language,
            text=lines[line].text,
            terms=lines[line].terms,
            variants=tuple(sorted(found, key=lambda v: v.id)),
        )
        for line, found in sorted(variants.items())
    ]
    return items, manifests


def write(evals: Path, items: Sequence[Item], manifests: dict[str, Manifest]) -> None:
    """Each item as `golden/<id>.toml` and each manifest as `manifests/<name>.json`, never over
    an item another import wrote."""
    for item in items:
        path = evals / GOLDEN_DIR / f"{item.id}.toml"
        if path.is_file() and read_toml(path, Item).source != "script":
            raise GoldenSetError(f"{path.name}: an item of another source has this ID")
    for item in items:
        write_text(evals / GOLDEN_DIR / f"{item.id}.toml", dump_item(item, comments=HEADER))
    for name, manifest in manifests.items():
        write_text(evals / MANIFESTS_DIR / f"{name}.json", dump_manifest(manifest))


def main(argv: Sequence[str] | None = None) -> int:
    """`python -m ole5_voice.evals.import_recordings`: write the new recordings' items and
    manifests from the recorder's files (no audio)."""
    parser = argparse.ArgumentParser(prog="import_recordings", description=_DESCRIPTION)
    parser.add_argument("--takes", type=Path, required=True, help="the recorder's --out folder")
    parser.add_argument("--evals", type=Path, default=EVALS, help="the golden set's folder")
    parser.add_argument(
        "--root", type=cli.name, default=ROOT, help="the audio root's name (--audio NAME=...)"
    )
    args = parser.parse_args(argv)
    configure_logging(loggers=LOGGERS)
    try:
        script = read_toml(args.evals / SCRIPT_FILE, Script)
        if not args.takes.is_dir():
            raise GoldenSetError(f"{args.takes.name}: no such folder of takes")
        items, manifests = build(args.takes, script, root=args.root)
        write(args.evals, items, manifests)
    except GoldenSetError as error:
        log.error("recordings_not_imported", problem=str(error))
        return 1
    variants = sum(len(item.variants) for item in items)
    log.info("recordings_imported", items=len(items), variants=variants, sessions=len(manifests))
    return 0


if __name__ == "__main__":
    sys.exit(main())

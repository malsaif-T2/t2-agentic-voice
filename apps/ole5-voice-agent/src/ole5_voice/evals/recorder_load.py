"""What `poe record` reads at start (`recorder.py` serves it): the script, the replies
`replies.json` names, every session's files below `--out` (`takes.py`), and, for the review
mode, the golden-set variants below the `--audio` roots given whose files the manifests name.

Each file is parsed strictly and checked against its place (GP-06): a session record, a sidecar
or a review whose names differ from its file's is refused, naming the file, so the recorder
never starts on a guess. A folder below `--out` that is a link is not read.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import datetime
from pathlib import Path
from typing import Final

from pydantic import TypeAdapter

from ole5_voice.evals import items as golden_items
from ole5_voice.evals.files import read_model
from ole5_voice.evals.items import EVALS, GOLDEN_DIR, MANIFESTS_DIR, GoldenSetError, reviewed
from ole5_voice.evals.models import (
    Device,
    Item,
    Manifest,
    ManifestFile,
    Model,
    ReferenceSource,
    is_name,
)
from ole5_voice.evals.recorder_state import (
    Audio,
    Entry,
    Recorder,
    RecorderError,
    Reply,
    local_now,
    take_entry,
)
from ole5_voice.evals.takes import (
    SESSION_FILE,
    Review,
    Script,
    SessionRecord,
    TakeSidecar,
    parse_review_file,
)
from ole5_voice.evals.worktree import Git, run_git, worktree_tops

_REPO: Final = EVALS.parents[2]  # the checkout the recorder's code is in
_REPLIES: Final = TypeAdapter(list[Reply])


def _tracked(out: Path, git: Git) -> bool:
    """Whether `out` (resolved) is in this repository outside its git-ignored var/: inside any
    of its worktrees, as git lists them, but under neither the recorder's own checkout's `var/`
    nor the main checkout's, so no take lands where git tracks it or in a worktree that may be
    removed (plan 004, app8); with no git, only the recorder's own checkout is known."""
    own = _REPO.resolve()
    tops = [top.resolve() for top in worktree_tops(_REPO, git)] or [own]  # the main's first
    kept = (own / "var", tops[0] / "var")
    inside = any(out.is_relative_to(top) for top in (own, *tops))
    return inside and not any(out.is_relative_to(folder) for folder in kept)


def _parse[M: Model](model: type[M], path: Path) -> M:
    message = f"{path} is no valid {model.__name__}: fix it, or move it"
    return read_model(path, model, lambda _: RecorderError(message))


_Reviews = dict[tuple[str, str], list[Review]]


def _scan(out: Path) -> tuple[dict[str, SessionRecord], dict[str, TakeSidecar], _Reviews]:
    """Every session's record, take sidecars and reviews below `--out`, each checked against its
    place; a folder that is a link, or not named as a session is, is not read."""
    records: dict[str, SessionRecord] = {}
    takes: dict[str, TakeSidecar] = {}
    reviews: _Reviews = {}
    for folder in sorted(out.iterdir()) if out.is_dir() else []:
        if not folder.is_dir() or folder.resolve() != folder or not is_name(folder.name):
            continue
        for path in sorted(folder.glob("*.json")):
            if path.name == SESSION_FILE:
                records[folder.name] = record = _parse(SessionRecord, path)
                placed = record.session == folder.name
            elif named := parse_review_file(path.name):
                review = _parse(Review, path)
                reviews.setdefault((folder.name, review.take), []).append(review)
                placed = (review.take, review.review_pass) == named
            else:
                take = _parse(TakeSidecar, path)
                placed = (take.take, take.session, take.file) == (
                    path.stem,
                    folder.name,
                    f"{path.stem}.wav",
                ) and take.take not in takes
                takes[take.take] = take
            if not placed:
                raise RecorderError(f"{path} names another session, take or pass than its place")
    return records, takes, reviews


def _replies(path: Path) -> dict[str, Reply]:
    message = f"{path} is no valid replies.json: give --replies its folder"
    found = read_model(path, _REPLIES, lambda _: RecorderError(message))
    replies = {reply.id: reply for reply in found}
    if len(replies) != len(found):
        raise RecorderError(f"{path} gives two replies one ID")
    return replies


def _add_variants(
    recorder: Recorder, audio: dict[str, Path], manifests: Path, items: Sequence[Item]
) -> None:
    """The golden-set variants below the roots given, each of whose segments is a file that a
    manifest names, with the same SHA-256; a take of this recorder's comes first."""
    named: dict[tuple[str, str], ManifestFile] = {}
    for path in sorted(manifests.glob("*.json")):
        manifest = _parse(Manifest, path)
        named |= {(manifest.root, file.path): file for file in manifest.files}
    if missing := audio.keys() - {root for root, _ in named}:
        roots = ", ".join(sorted(missing))
        raise RecorderError(f"no manifest under {manifests} names the root(s) {roots}")
    folders = {root: folder.resolve() for root, folder in audio.items()}
    for item in items:
        for variant in item.variants:
            if (
                variant.id in recorder.entries
                or {s.root for s in variant.segments} - folders.keys()
            ):
                continue
            files = [named.get((s.root, s.path)) for s in variant.segments]
            if any(
                f is None or f.sha256 != s.sha256
                for f, s in zip(files, variant.segments, strict=True)
            ):
                recorder.skipped.append(
                    f"variant {variant.id}: a segment is no file its manifest names"
                )
                continue
            recorder.entries[variant.id] = Entry(
                id=variant.id,
                session=variant.session,
                of=item.id,
                kind=item.kind,
                language=item.language,
                reference=variant.reference,
                source=variant.reference_source,
                audio=tuple(Audio(folders[s.root], s.path, s.sha256) for s in variant.segments),
            )


def _check_reviews(reference: str, source: ReferenceSource, found: Sequence[Review]) -> None:
    """RecorderError for reviews the import would refuse (`items.reviewed`): an empty typed one,
    say, which the page never writes."""
    try:
        reviewed(reference, source, found)
    except GoldenSetError as error:
        problem = str(error)
    else:
        return
    raise RecorderError(f"{problem}, below --out: fix the review's file, or move it")


def load_recorder(
    *,
    out: Path,
    script: Path,
    session: str | None = None,
    device: Device | None = None,
    replies: Path | None = None,
    audio: dict[str, Path] | None = None,
    golden: Path = EVALS / GOLDEN_DIR,
    manifests: Path = EVALS / MANIFESTS_DIR,
    load_items: Callable[[Path], Sequence[Item]] | None = None,
    clock: Callable[[], datetime] = local_now,
    git: Git = run_git,
) -> Recorder:
    """The recorder for one run, or RecorderError naming what to give instead. `load_items`
    reads the golden set's items (`items.load_items` unless another is given), and `git`
    lists the repository's worktrees."""
    out = out.resolve()
    if _tracked(out, git):
        raise RecorderError(f"--out {out} is in the repository, outside its git-ignored var/")
    try:
        lines = golden_items.read_toml(script, Script)
    except GoldenSetError:
        lines = None
    if lines is None:  # raised outside the handler, so no exception chain leads to the file
        raise RecorderError(f"{script} is no valid script.toml: give --script")
    recorder = Recorder(out=out, script=lines, session=session, device=device, clock=clock)
    if len(recorder.lines) != len(lines.lines):
        raise RecorderError(f"{script} gives two lines one ID")
    if replies is not None:
        recorder.replies_dir = replies.resolve()
        recorder.replies = _replies(recorder.replies_dir / "replies.json")
    if missing := {line.reply for line in lines.lines if line.reply} - recorder.replies.keys():
        raise RecorderError(
            f"no replies.json names the replies {', '.join(sorted(missing))}: give --replies"
        )
    records, recorder.takes, reviews = _scan(out)
    recorder.consent = records.get(session) if session else None
    if recorder.consent is not None and recorder.consent.device != device:
        raise RecorderError(
            f"session {session} is recorded on the {recorder.consent.device} microphone"
        )
    for take in recorder.takes.values():
        line = recorder.lines.get(take.line)
        if line is None:
            recorder.skipped.append(f"take {take.take}: the script has no line {take.line}")
        elif take.status == "kept":
            recorder.entries[take.take] = take_entry(out, take, line)
    if audio:
        try:
            items = (load_items or golden_items.load_items)(golden)
        except (OSError, ValueError):
            raise RecorderError(f"the items under {golden} do not load: run poe golden") from None
        _add_variants(recorder, audio, manifests, items)
    for entry in recorder.entries.values():
        entry.reviews.extend(reviews.get((entry.session, entry.id), []))
        _check_reviews(entry.reference, entry.source, entry.reviews)
    passes = [review.review_pass for found in reviews.values() for review in found]
    recorder.review_pass = 1 + max(passes, default=0)
    return recorder

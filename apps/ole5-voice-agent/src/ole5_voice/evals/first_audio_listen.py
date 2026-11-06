"""`poe first-audio-listen`: the owner's check of run T's arm T1 (plan 006's registration, T: T1
is kept only if "the owner hears no clipped first syllable in ten of its replies").

`--run` names T1's dev run (its `--out` folder, whose scorecard says `tts.trim_silence` was on),
and `--seed` picks `--count` (10) of the openings its replies kept (first_audio_run.py), at
random over all of them in the run's order (`random.Random(seed).sample`), into a new folder,
`--out` (where git ignores it, as a run's), as `01.wav` onwards, with `sheet.toml`: one entry a
file, naming its recording and reply, with `clipped = "?"` for the owner to set to `yes` or `no`
after listening. `--read SHEET` reads a marked sheet back: how many were marked clipped, whole
and not yet; the check passes when every reply is marked and none is clipped.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Final, Literal

from pydantic import Field
from t2_agentic_voice import T2VoiceError, configure_logging, get_logger

from ole5_voice import LOGGERS
from ole5_voice.evals.files import read_model
from ole5_voice.evals.first_audio_card import AudioScorecard
from ole5_voice.evals.models import Model, Name
from ole5_voice.evals.run_parts import Parts
from ole5_voice.evals.runs import SCORECARD_FILE
from ole5_voice.evals.worktree import check_out, inspect, refused

COUNT: Final = 10  # the registration's ten replies
SHEET_FILE: Final = "sheet.toml"
_DESCRIPTION = "Write ten of run T1's reply openings for the owner's listen, or read the sheet."
log = get_logger(__name__)


class Mark(Model):
    """One reply on the sheet: its file, its recording and reply, and the owner's mark."""

    file: str = Field(pattern=r"^\d{2}\.wav$")
    item: Name
    variant: Name
    reply: int = Field(ge=0)
    clipped: Literal["?", "yes", "no"] = "?"


class Sheet(Model):
    """The sheet: the run the replies are T1's, the seed that picked them, and each mark."""

    run: Name
    seed: int
    replies: tuple[Mark, ...] = Field(min_length=1)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="poe first-audio-listen", description=_DESCRIPTION)
    add = parser.add_argument
    add("--run", type=Path, help="run T1's --out folder, or its scorecard")
    add("--seed", type=int, help="the seed that picks the replies")
    add("--count", type=int, default=COUNT, help=f"how many replies ({COUNT})")
    add("--out", type=Path, help="a new folder for the files and the sheet, which git ignores")
    add("--read", type=Path, help="read a marked sheet back instead")
    return parser


def _card(path: Path) -> tuple[AudioScorecard, Path]:
    """T1's scorecard and its folder; refused unless a dev run with the trim on."""
    file = path / SCORECARD_FILE if path.is_dir() else path
    try:
        card = read_model(file, AudioScorecard, lambda problem: ValueError(problem))
    except ValueError:
        raise refused("--run is not a run T scorecard", "give run T1's --out folder") from None
    if card.run.split != "dev" or card.run.settings.get("tts.trim_silence") != "true":
        raise refused(
            "--run is not a dev run with tts.trim_silence on", "give run T1's --out folder"
        )
    return card, file.parent


def pick(args: argparse.Namespace, parts: Parts) -> int:
    """Write the picked replies and the sheet."""
    card, folder = _card(args.run)
    found = [
        (result.item, result.variant, number, path)
        for result in card.variants
        for number, path in enumerate(result.openings)
        if path is not None
    ]
    if args.count < 1 or len(found) < args.count:
        raise refused(
            f"the run kept {len(found)} reply openings, fewer than --count {args.count}",
            "give a complete dev run of T1",
        )
    out = check_out(args.out, inspect(parts.folder, parts.git), parts.git)
    out.mkdir(parents=True)
    chosen = random.Random(args.seed).sample(found, args.count)  # noqa: S311  # a pick, not a key
    lines = [
        "# The owner's check of run T1 (plan 006's registration, T): listen to each file and",
        '# set its `clipped` to "yes" where its first syllable is cut, "no" where it is whole.',
        f"run = {json.dumps(card.run.name)}",
        f"seed = {args.seed}",
    ]
    for place, (item, variant, number, path) in enumerate(chosen, start=1):
        name = f"{place:02}.wav"
        (out / name).write_bytes((folder / path).read_bytes())
        lines += ["", "[[replies]]", f"file = {json.dumps(name)}"]
        lines += [f"item = {json.dumps(item)}", f"variant = {json.dumps(variant)}"]
        lines += [f"reply = {number}", 'clipped = "?"']
    (out / SHEET_FILE).write_bytes(("\n".join(lines) + "\n").encode("utf-8"))
    log.info("replies_written", count=args.count, of=len(found), out=str(out))
    return 0


def read(path: Path) -> int:
    """The marks of a sheet: 0 when every reply is marked, 1 while some are not."""
    try:
        sheet = read_model(path, Sheet, lambda problem: ValueError(problem), toml=True)
    except ValueError:
        raise refused("--read is not a listening sheet", f"give the {SHEET_FILE} written") from None
    marks = [mark.clipped for mark in sheet.replies]
    clipped, whole, unmarked = (marks.count(m) for m in ("yes", "no", "?"))
    verdict = "unmarked" if unmarked else "fails" if clipped else "passes"
    log.info("listened", run=sheet.run, clipped=clipped, whole=whole, unmarked=unmarked)
    log.info("owner_check", run=sheet.run, verdict=verdict)
    return 1 if unmarked else 0


def main(argv: Sequence[str] | None = None, *, parts: Parts | None = None) -> int:
    """`uv run poe first-audio-listen`: write T1's picked replies, or read a marked sheet. 2
    when refused."""
    parser = _parser()
    args = parser.parse_args(argv)
    if args.read is None and None in (args.run, args.seed, args.out):
        parser.error("picking needs --run, --seed and --out; reading needs --read")
    configure_logging(loggers=LOGGERS)
    try:
        return read(args.read) if args.read else pick(args, parts or Parts())
    except T2VoiceError as error:
        log.error("listen_refused", code=error.code, message=error.message)
        return 2


if __name__ == "__main__":
    sys.exit(main())

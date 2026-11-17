"""The folder of a run of the flight agent's scripted calls (`--out`, evals/run.py): what the run
is (`run.json`, written before anything is sent), each play's record as it finishes
(`plays.jsonl`), each session (`sessions.jsonl`), the scorecard (`scorecard.json`, each written
whole and then moved into place, and `scorecard.md`) and a copy of each session's history line
(`history.jsonl`).

A new run's folder must be one a run may write to (the library's `check_out`: a folder that does
not exist yet, outside the run's own worktree and every other linked one, and inside the main
checkout only where git ignores it, its `var/`); a resumed run's is the folder of a run already
begun, outside the run's worktree, at the run's commit or a later one that changed only the apps'
run histories (`HISTORIES`: a stopped session's history line, committed so the tree is clean
again). While a session runs the folder holds `run.lock`, made only
when no other run holds it, so two sessions never write one folder: a folder holding it is in
use, and refused. Its name, the run's, is a name (`NAME`).
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Final

from pydantic import BaseModel, ValidationError
from t2_agentic_voice.evals import Checkout, Git, check_out, run_refused

from flight_voice.evals.score import PlayRecord, RunInfo, ScenarioCard, Scorecard, Session

RUN_FILE: Final = "run.json"
PLAYS_FILE: Final = "plays.jsonl"
SESSIONS_FILE: Final = "sessions.jsonl"
SCORECARD_FILE: Final = "scorecard.json"
SCORECARD_MD: Final = "scorecard.md"
HISTORY_FILE: Final = "history.jsonl"
LOCK_FILE: Final = "run.lock"
NAME: Final = re.compile(r"^[a-z0-9][a-z0-9._-]{0,79}$")
HISTORIES: Final = re.compile(r"^apps/[^/]+/evals/history\.jsonl$")  # each app's run history


def folder_for(out: Path, *, resume: bool, checkout: Checkout, git: Git) -> RunFolder:
    """The run's folder (the module's docstring), refused before anything is sent."""
    if resume:
        target = out.expanduser().resolve()
        if not (target / RUN_FILE).is_file():
            raise run_refused(f"--resume: {target} holds no run", "give the --out of that run")
        if target.is_relative_to(checkout.top.resolve()):
            raise run_refused(
                "--out is inside the run's worktree, which is removed after the runs",
                "give a folder under the main checkout's var/, or outside the repository",
            )
    else:
        target = check_out(out, checkout, git)
    if not NAME.fullmatch(target.name):
        raise run_refused(
            "the --out folder's name, the run's, is not a name of lower-case letters, digits, "
            "dots, dashes and underscores",
            "name the folder like f-dev-1",
        )
    if (target / LOCK_FILE).exists():
        raise run_refused(
            f"--out {target} is in use by another run ({LOCK_FILE})",
            f"wait for that run to end, or remove {LOCK_FILE} when no run uses the folder",
        )
    return RunFolder(target)


def append_line(path: Path, line: BaseModel) -> None:
    """`line` added to the JSON lines file at `path` as one LF-ended line."""
    with path.open("ab") as file:
        file.write((line.model_dump_json() + "\n").encode("utf-8"))


class RunFolder:
    """A run's `--out` folder (the module's docstring)."""

    def __init__(self, out: Path) -> None:
        self.out = out

    def begin(self, info: RunInfo) -> None:
        """Make the folder, and write what the run is."""
        self.out.mkdir(parents=True)
        self._write(RUN_FILE, info.model_dump_json(indent=2) + "\n")

    @contextmanager
    def held(self) -> Iterator[None]:
        """The folder held for one session: `run.lock` made, refused when another run holds
        it, and removed when the session ends."""
        lock = self.out / LOCK_FILE
        try:
            handle = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            raise run_refused(f"--out {self.out} is in use by another run", "wait") from None
        os.close(handle)
        try:
            yield
        finally:
            lock.unlink(missing_ok=True)

    def info(self) -> RunInfo:
        return RunInfo.model_validate_json(self._read(RUN_FILE, RUN_FILE))

    def resumed(self, info: RunInfo, *, git: Git, top: Path) -> RunInfo:
        """The run begun in the folder, its first commit kept, refused unless it is `info` but
        for when it began, its estimate, and a commit `histories_only` allows (`git` in `top`)."""
        earlier = self.info()
        kept = {"started_at", "estimate_usd"}
        if differing := [
            n
            for n in RunInfo.model_fields
            if n not in kept
            and (
                not histories_only(earlier.commit, info.commit, git, top)
                if n == "commit"
                else _differs(n, earlier, info)
            )
        ]:
            raise run_refused(
                f"--resume: the run in --out differs in {', '.join(differing)}",
                "go on at the run's commit, or one that only adds its history lines, with the "
                "same command line and scenarios",
            )
        return earlier

    def plays(self) -> list[PlayRecord]:
        return [PlayRecord.model_validate_json(t) for t in self._lines(PLAYS_FILE)]

    def sessions(self) -> list[Session]:
        return [Session.model_validate_json(t) for t in self._lines(SESSIONS_FILE)]

    def add_play(self, record: PlayRecord) -> None:
        append_line(self.out / PLAYS_FILE, record)

    def add_session(self, session: Session) -> None:
        append_line(self.out / SESSIONS_FILE, session)

    def write_scorecard(self, card: Scorecard) -> None:
        """`scorecard.json` and `scorecard.md`, each written whole, then moved into place."""
        self._write(SCORECARD_FILE, card.model_dump_json(indent=2) + "\n")
        self._write(SCORECARD_MD, card_md(card))

    def _read(self, name: str, where: str) -> str:
        try:
            return (self.out / name).read_bytes().decode("utf-8")
        except (OSError, UnicodeDecodeError):
            raise run_refused(
                f"{where} in --out cannot be read", "give the folder of a run"
            ) from None

    def _lines(self, name: str) -> list[str]:
        if not (self.out / name).exists():
            return []
        return [line for line in self._read(name, name).splitlines() if line.strip()]

    def _write(self, name: str, text: str) -> None:
        part = self.out / f"{name}.part"
        part.write_bytes(text.encode("utf-8"))
        part.replace(self.out / name)


def _differs(name: str, one: RunInfo, two: RunInfo) -> bool:
    return bool(getattr(one, name) != getattr(two, name))


def histories_only(earlier: str, now: str, git: Git, top: Path) -> bool:
    """Whether commit `now` is `earlier`, or a later one whose changes since it are only to the
    apps' run histories (`HISTORIES`), as `git` says in `top`."""
    if now == earlier:
        return True
    if git(["merge-base", "--is-ancestor", earlier, now], top).returncode != 0:
        return False
    changed = git(["diff", "--name-only", "-z", earlier, now], top)
    names = [name for name in changed.stdout.split("\0") if name]
    return changed.returncode == 0 and all(HISTORIES.fullmatch(name) for name in names)


def read_folder(folder: RunFolder) -> tuple[list[PlayRecord], list[Session]]:
    """The records and sessions a resumed run's folder holds; refused when one cannot be read."""
    try:
        return folder.plays(), folder.sessions()
    except ValidationError:
        raise run_refused(
            "--resume: a record or a session in --out is not one this run writes",
            "give the folder of a run of this command",
        ) from None


def _verdict(card: ScenarioCard) -> str:
    skipped = f"skipped ({', '.join(card.skipped)})"
    return (
        skipped
        if card.skipped
        else {True: "passed", False: "failed", None: "unfinished"}[card.passed]
    )


def card_md(card: Scorecard) -> str:
    """`scorecard.md`: the run, its totals and a row per scenario."""
    run, totals = card.run, card.totals
    lines = [
        f"# Scripted flight calls: {run.name}",
        "",
        f"Commit {run.commit[:12]}, split {run.split}, the {run.agent} agent, "
        f"{run.model} at {run.effort}, "
        f"{run.repeats} plays each. Complete: {'yes' if card.complete else 'no'}"
        f"{'' if card.stopped is None else f' (stopped: {card.stopped})'}. "
        f"Violations: {totals.violations} ({'held' if card.held else 'BROKEN'}). "
        f"Spent ${card.cost_usd:.4f} of ${run.cap_usd:g}.",
        "",
        f"Passed {totals.passed} of {totals.played} scenarios played; {totals.skipped} skipped; "
        f"{totals.plays} plays.",
        "",
        "| Scenario | Plays | Passes | Verdict | Every play | Violations | Failed checks "
        "| Measures |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for each in card.scenarios:
        every = "" if each.all_plays is None else ("yes" if each.all_plays else "no")
        failed = ", ".join(f"{name} {n}" for name, n in each.failed.items())
        shown = " ".join(str(v) for v in each.violations)
        measured = ", ".join(f"{name} {v:g}" for name, v in each.measures.items())
        lines.append(
            f"| {each.id} | {each.plays} | {each.passes} | {_verdict(each)} | {every} "
            f"| {shown} | {failed} | {measured} |"
        )
    return "\n".join(lines) + "\n"

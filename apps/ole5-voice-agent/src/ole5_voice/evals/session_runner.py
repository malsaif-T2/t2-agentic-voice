"""What the spending runs share once their command line is read: one command's frame and its
exit codes (`main_of`), what they build closed whenever the run ends (`closed`), the measuring
run in its own loop with an interrupt or a library error ending it (`measured`); and, for runs
K, S and A, which measure the talker over units paced, capped and resumed by sessions, the
session itself (`SessionRun`), each run giving its own parts (talker_run.py, scenario_run.py,
action_run.py). Runs K0 (knowledge_depth.py) and T (first_audio.py) share the frame, the closing
and the measuring.

**Exit codes.** 0 when the run is complete; 1 when it is not, its scorecard and history line
written all the same: a failed smoke test, the cap, a model's day, an interrupt, or a library
error (a `T2VoiceError`) raised once the run began, since requests were spent; 2 when it is
refused before anything is sent. Any other error is a bug: raised, with its traceback, once the
scorecard and line are written. A held-out run's library lines but its errors are held back, as
they would tell each unit's path apart.

**A session** of K, S or A: before it, the shared history's check that it takes the run's line
(`check_history`), the run's paced chat model, its day's count started from the history
(`paced_chat`), and, for S and A, every scenario once and then again until each has its repeats
(`evenly`), so a run stopped early has played them evenly. Then the smoke test, which must end
with no failed, retried or refused request and no rule of its run's broken; with `--smoke-only`
its record is the run's; then each unit, a dev one's record written as it finishes with a
progress line of identifiers and verdicts, a held-out one's line a count; the cap or the key's
daily limit stops it (`StopRun`). Whatever ended it, the session's own count, its spend, the
scorecard and its history line, recorded twice (`history.record_line`); a held-out run that did
not finish keeps no result, and a dev run stopped by the day, the cap or an interrupt is told to
go on with `--resume`.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from abc import ABC, abstractmethod
from collections.abc import Callable, Coroutine, Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, ClassVar, Final, Literal, Protocol

from pydantic import BaseModel
from t2_agentic_voice import T2VoiceError, VoiceSettings, configure_logging, get_logger

from ole5_voice import LOGGERS
from ole5_voice.evals.chat_pacing import PacedChat
from ole5_voice.evals.factories import Closing
from ole5_voice.evals.history import record_line
from ole5_voice.evals.run_folder import RunFolder
from ole5_voice.evals.talker_args import TalkerParts, pacing
from ole5_voice.evals.talker_measure import StopRun
from ole5_voice.evals.talker_score import Session, Stopped
from ole5_voice.evals.worktree import refused

# Why a dev run that stopped can go on with `--resume`: its finished results are kept.
RESUMABLE: Final = ("daily_limit", "cap", "interrupted")
log = get_logger(__name__)


class _Scripted(Protocol):
    @property
    def id(self) -> str: ...


def main_of(
    parser: argparse.ArgumentParser,
    argv: Sequence[str] | None,
    require: Callable[[argparse.ArgumentParser, argparse.Namespace], None],
    run: Callable[[argparse.Namespace], int],
    refusal: str,
) -> int:
    """A spending run's command: its command line read and checked, logging set up, a held-out
    run's library lines but its errors held back, and the run; a refusal logged as `refusal`,
    exit 2. The exit codes are the module's docstring's."""
    args = parser.parse_args(argv)
    require(parser, args)
    configure_logging(loggers=LOGGERS)
    if getattr(args, "split", None) == "held-out":  # they would tell each unit's path apart
        logging.getLogger("t2_agentic_voice").setLevel(logging.ERROR)
    try:
        return run(args)
    except T2VoiceError as error:
        log.error(refusal, code=error.code, message=error.message)
        return 2


def closed(build: Callable[[Closing], int]) -> int:
    """`build`'s run, what it built closed whenever it ends, a refusal's included."""
    closing = Closing()
    try:
        return build(closing)
    finally:
        closing.close_now()


def measured[S](
    measuring: Coroutine[Any, Any, S], *, done: Callable[[], int], of: int
) -> S | Literal["interrupted", "error"]:
    """What `measuring`, run in its own loop, returns; `interrupted` at an interrupt; `error` at
    a library error, once the run began. Any other error is logged and raised: the caller, its
    `stopped` set to `error` before the call, writes its scorecard and line first."""
    try:
        return asyncio.run(measuring)
    except KeyboardInterrupt:
        log.warning("run_interrupted", done=done(), of=of)
        return "interrupted"
    except BaseException as error:
        log.error("run_failed", error=type(error).__name__, done=done(), of=of)
        if not isinstance(error, T2VoiceError):
            raise  # a bug's traceback, once the card and line are written
        return "error"


def check_history(parts: TalkerParts, line: BaseModel, run: str, kind: str) -> None:
    """Refused when the shared history takes no line of run `run`'s kind, `kind`."""
    if not parts.history_accepts(line):
        raise refused(
            f"the shared history takes no line of run {run}'s kind yet",
            f"name {kind} in run_lines.AnyLine, as the integration does",
        )


def first_session(started_at: datetime) -> Session:
    """The session a probe line is built with: a run's first, nothing measured yet."""
    return Session(started_at=started_at, stopped=None, variants=0)


def earlier[R: BaseModel](
    folder: RunFolder, shape: type[R], *, resume: bool
) -> tuple[list[R], list[Session]]:
    """A resumed run's records and sessions so far; none for a new run."""
    return (folder.results(shape), folder.sessions(Session)) if resume else ([], [])


def paced_chat(
    args: argparse.Namespace,
    parts: TalkerParts,
    closing: Closing,
    chat: VoiceSettings,
    history: Path,
    sessions: Sequence[Session],
) -> tuple[datetime, PacedChat]:
    """When the session begins, and its paced chat model (`talker_args.pacing`) on the chat
    adapter, kept in `closing`: each model's day counted from the shared `history`, and the
    earlier sessions' spend under the cap."""
    began = parts.now()
    paced = pacing(
        args,
        closing.add(parts.chat(chat)),
        today=parts.requests_today(history, began.date()),
        before_usd=sum(session.cost_usd for session in sessions),
        parts=parts,
    )
    return began, paced


def evenly[S: _Scripted](
    scenarios: Sequence[S], repeats: int, done: Iterable[tuple[str, int]]
) -> list[tuple[S, int]]:
    """Every scenario once, then every one again, until each has `repeats` plays, those `done`
    (by scenario and repeat) left out."""
    played = set(done)
    return [
        (scenario, repeat)
        for repeat in range(1, repeats + 1)
        for scenario in scenarios
        if (scenario.id, repeat) not in played
    ]


@dataclass(kw_only=True)
class SessionRun[U, R: BaseModel, C: BaseModel](ABC):
    """One session of a run of K, S or A (the module's docstring), measuring `todo` after the
    smoke test; each run's own parts are its subclass's: the smoke test's record and a unit's,
    the smoke test's own rule, a unit's progress line, the scorecard, the history line and the
    finished line."""

    event: ClassVar[str] = "variant_done"  # a unit's progress line
    folder: RunFolder
    data: Path  # the worktree's data folder, whose history the line is appended to
    parts: TalkerParts
    closing: Closing
    paced: PacedChat
    began: datetime
    sessions: list[Session]  # the earlier sessions'
    done: list[R]  # the earlier sessions' records
    todo: Sequence[U]
    expected: int  # the records a complete run holds
    held_out: bool
    smoke_only: bool
    records: list[R] = field(default_factory=list, init=False)  # this session's own

    @abstractmethod
    async def smoke_record(self) -> R:
        """The smoke test's record."""

    @abstractmethod
    async def record(self, each: U) -> R:
        """`each`'s record."""

    @abstractmethod
    def smoke_check(self, record: R) -> tuple[bool, dict[str, object]]:
        """Whether the smoke test broke its run's own rule, and what its `smoke_failed` says."""

    @abstractmethod
    def shown(self, each: U, record: R) -> dict[str, object]:
        """A dev unit's progress line: identifiers, verdicts and counts, never a text."""

    @abstractmethod
    def scorecard(
        self, records: list[R], *, complete: bool, stopped: Stopped | None, sessions: list[Session]
    ) -> C:
        """The run's scorecard of `records`, those it keeps, after `sessions`."""

    @abstractmethod
    def line(self, card: C, session: Session, number: int) -> BaseModel:
        """The history line of session `number` (from 1)."""

    @abstractmethod
    def finished(self, card: C, records: list[R]) -> dict[str, object]:
        """What the `run_finished` line says besides whether the run is complete."""

    def kept(self, every: list[R], complete: bool) -> list[R]:
        """The records the scorecard keeps: none for a held-out run that did not finish, which
        is run again whole."""
        return every if complete or not self.held_out else []

    def run(self) -> int:
        """The session, its scorecard and line written whatever ended it; 0 when the run is
        complete, else 1, a bug raised once they are written."""
        stopped: Stopped | None = "error"  # until the measuring returns why it stopped
        try:
            stopped = measured(self._measure(), done=lambda: len(self.records), of=len(self.todo))
        finally:
            self._close(stopped)
        return 0 if stopped is None else 1

    async def _measure(self) -> Stopped | None:
        spend = self.paced.spend
        try:
            record = await self.smoke_record()
            broke, said = self.smoke_check(record)
            if broke or spend.retries_and_failures():
                log.error("smoke_failed", **said, requests=spend.requests())
                return "smoke_failed"
            log.info("smoke_passed", requests=spend.requests())
            if self.smoke_only:
                self.records.append(record)
                self.folder.add_result(record)
                return None
            for number, each in enumerate(self.todo, start=1):
                record = await self.record(each)
                self.records.append(record)
                if self.held_out:
                    log.info(self.event, done=number, of=len(self.todo))
                    continue
                self.folder.add_result(record)
                log.info(self.event, done=number, of=len(self.todo), **self.shown(each, record))
        except StopRun as stop:
            log.warning(
                "run_stopped", reason=stop.reason, done=len(self.records), of=len(self.todo)
            )
            return stop.reason
        finally:
            await self.closing.aclose()  # the chat model and the knowledge base, in the run's loop
        return None

    def _close(self, stopped: Stopped | None) -> None:
        """The session, the scorecard and the session's history line, whatever stopped it."""
        every = [*self.done, *self.records]
        complete = stopped is None and len(every) == self.expected
        kept = self.kept(every, complete)
        spend = self.paced.spend
        session = Session(
            started_at=self.began,
            stopped=stopped,
            variants=len(self.records),
            spend=spend.spent(),
            cost_usd=spend.session_usd(),
        )
        self.folder.add_session(session)
        sessions = [*self.sessions, session]
        card = self.scorecard(kept, complete=complete, stopped=stopped, sessions=sessions)
        self.folder.write_scorecard(card)
        line = self.line(card, session, len(sessions))
        record_line(self.parts.append_line, line, self.data, self.folder.out)
        said = self.finished(card, kept)
        if stopped in RESUMABLE and not self.held_out:
            log.warning("run_resumable", fix="run the same command with --resume to go on")
        log.info("run_finished", complete=complete, **said)

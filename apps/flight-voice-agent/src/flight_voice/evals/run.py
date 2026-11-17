"""`poe eval-flights`: the flight agent's scripted calls (evals/scenarios.py) over one split, each
scenario `--repeats` times (three), each play one call through the seam (call.py) on the system
clock with the app's own agent and the real talker (`--model`, `gpt-oss-120b`, at `--effort`,
medium, D-074) against a new mock airline, checked in code (checks.py), kept in `--out`
(folder.py, score.py).

**Refused before anything is sent** (exit 2): the main checkout as the run's tree, a dirty tree
(the library's `run_checkout`); an `--out` a run may not write to, or one in use (folder.py);
scenarios that cannot be read or break a rule (rules.py's `problems`, but each kind's missing
held-out scenario while no held-out scenario exists yet); a model with no price or limits; a
resumed run that differs from the one begun; and the dry estimate of the run's most spend past
`--cap-usd` ($10, the owner's): for each play left and the smoke play, each turn's most talker
requests (`llm.max_requests_per_turn`), an uncertain overlap's request for each turn said over
the agent, and the yes rule's check for each turn that may answer a read-back, each reading
`--input-budget-tokens` and writing its model's most, at each model's price.

**Then** the smoke play, the first dev scenario once, which must end with no failed, retried or
refused request and no violation (one stuck on the agent's own turn is its verdict, kept); then
every scenario of the split once, then again, until each has its repeats (a scenario that needs a
capability that does not play yet is skipped and reported). Every model request goes through the
library's `PacedChat`, under the cap and each model's limits, the day's requests counted from every
app's run history (`requests_today`), so the key's day is shared with Ole5's runs. Each play's
record is written as it finishes, with a progress line of identifiers and verdicts, never a text.
Whatever ends the session, it is recorded, the scorecard written and one line appended to the app's
`evals/history.jsonl` (and copied beside the scorecard): commit it before `--resume`, since a dirty
tree is refused (a resume goes on at a later commit that changed only the run histories,
folder.py). Exit 0 when the run is complete, 1 when it is not (the smoke play failed, the cap, the
day's limit, an interrupt), 2 when it is refused.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, get_args

from t2_agentic_voice import LlmSettings, T2VoiceError, VoiceSettings, configure_logging, get_logger
from t2_agentic_voice.evals import (
    Git,
    ModelPacer,
    PacedChat,
    RunClock,
    RunSleep,
    Spend,
    every_history,
    requests_today,
    run_checkout,
    run_git,
    run_refused,
)
from t2_agentic_voice.groq import GroqChat
from t2_agentic_voice.ports import ChatModel

from flight_voice import LOGGERS
from flight_voice.evals import call
from flight_voice.evals import run_setup as setup
from flight_voice.evals.folder import HISTORY_FILE, RunFolder, append_line, folder_for, read_folder
from flight_voice.evals.scenarios import Scenario
from flight_voice.evals.score import PlayRecord, RunInfo, Session, Stopped, history_line, record_of
from flight_voice.evals.score import scorecard as scored
from flight_voice.settings import for_the_app

MODELS: Final = get_args(LlmSettings.model_fields["model"].annotation)
EFFORTS: Final = ("low", "medium", "high")
REPEATS: Final = 3
CAP_USD: Final = 10.0
log = get_logger(__name__)

# One play of a scenario on a chat model with the call's settings, as call.py's `play` plays it.
Play = Callable[[Scenario, ChatModel, VoiceSettings], Awaitable[call.PlayRead]]


def _groq(env_file: Path | None) -> ChatModel:
    """The chat adapter, its key from the environment and `env_file` when given."""
    return GroqChat.from_settings(VoiceSettings.from_env(env_file=env_file, env="dev"))


def _here() -> Path:
    return Path(__file__).resolve().parent


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class RunParts:
    """What a run is built from, each replaceable by a test's fake: the folder whose checkout
    runs, `git`, the chat adapter, one play, and the clocks."""

    folder: Path = field(default_factory=_here)
    git: Git = run_git
    chat: Callable[[Path | None], ChatModel] = _groq
    play: Play = call.play
    now: Callable[[], datetime] = _now
    clock: RunClock = time.perf_counter
    sleep: RunSleep = asyncio.sleep


def parser() -> argparse.ArgumentParser:
    made = argparse.ArgumentParser(
        prog="poe eval-flights",
        description="Play the flight agent's scripted calls over one split, into --out.",
    )
    add = made.add_argument
    add("--split", choices=("dev", "held-out"), required=True, help="the split, all of it")
    add("--repeats", type=setup.count, default=REPEATS, help=f"plays a scenario ({REPEATS})")
    add("--out", type=Path, required=True, help="a new absolute folder, the main checkout's var/")
    add("--model", choices=MODELS, default=setup.MODEL, help=f"the talker's ({setup.MODEL})")
    add("--effort", choices=EFFORTS, default="medium", help="its reasoning effort (medium)")
    add("--cap-usd", type=setup.amount, default=CAP_USD, help=f"the most it spends ({CAP_USD:g})")
    add("--resume", action="store_true", help="go on with the stopped run in --out")
    add("--env-file", type=Path, help="the .env the Groq key loads from")
    add("--price", type=setup.price, action="append", default=[], metavar="MODEL=IN/OUT")
    add("--limits", type=setup.limits, action="append", default=[], metavar="MODEL=RPM/TPM/RPD")
    add("--input-budget-tokens", type=setup.count, default=setup.INPUT_BUDGET)
    add("--max-attempts", type=setup.count, default=4, help="sends of a request turned away")
    return made


@dataclass
class _Run:
    """One session of a run, built and checked (`_built`), then played (`measure`)."""

    args: argparse.Namespace
    parts: RunParts
    folder: RunFolder
    info: RunInfo
    scenarios: list[tuple[Scenario, tuple[str, ...]]]
    smoke: Scenario
    todo: list[tuple[Scenario, int]]
    settings: VoiceSettings
    paced: PacedChat
    history: Path
    done: list[PlayRecord]
    sessions: list[Session]
    began: datetime
    commit: str  # HEAD as this session runs
    records: list[PlayRecord] = field(default_factory=list)

    async def _one(self, scenario: Scenario, repeat: int, *, smoke: bool = False) -> PlayRecord:
        start = self.parts.clock()
        settings = setup.play_settings(scenario, self.settings)
        read = await self.parts.play(scenario, self.paced, settings)
        return record_of(scenario, repeat, read, self.parts.clock() - start, smoke=smoke)

    def _stopped(self) -> Stopped | None:
        """Why the paced model refused a request (the cap, the key's day), whoever caught it."""
        return self.paced.stopped

    async def measure(self) -> Stopped | None:
        spend = self.paced.spend
        try:
            smoke = await self._one(self.smoke, 0, smoke=True)
            if (stopped := self._stopped()) is not None:
                return stopped
            broken = smoke.failure == "provider" or smoke.violations or spend.retries_and_failures()
            if broken or smoke.failure is not None:  # or stuck on the agent's own turn: kept
                self.folder.add_play(smoke)
                self.records.append(smoke)
            if broken:
                log.error("smoke_failed", scenario=smoke.scenario, failure=smoke.failure)
                return "smoke_failed"
            log.info("smoke_passed", scenario=smoke.scenario, requests=spend.requests())
            for number, (scenario, repeat) in enumerate(self.todo, start=1):
                record = await self._one(scenario, repeat)
                if (stopped := self._stopped()) is not None:  # dropped: a resumed run plays it
                    return stopped
                self.folder.add_play(record)
                self.records.append(record)
                log.info(
                    "play_done",
                    done=number,
                    of=len(self.todo),
                    scenario=record.scenario,
                    repeat=repeat,
                    passed=record.passed,
                    failed=list(record.failed),
                    violations=len(record.violations),
                )
        except (KeyboardInterrupt, asyncio.CancelledError):
            return "interrupted"
        finally:
            await self.paced.aclose()
        return None

    def close(self, stopped: Stopped | None) -> int:
        """The session recorded, the scorecard written and the history line appended."""
        spend = self.paced.spend
        session = Session(
            started_at=self.began,
            commit=self.commit,
            stopped=stopped,
            plays=len(self.records),
            spend=spend.spent(),
            cost_usd=round(spend.session_usd(), 6),
        )
        self.folder.add_session(session)
        sessions = [*self.sessions, session]
        records = [*self.done, *self.records]
        card = scored(self.info, self.scenarios, records, stopped=stopped, sessions=sessions)
        self.folder.write_scorecard(card)
        line = history_line(card, session, len(sessions))
        append_line(self.history, line)
        append_line(self.folder.out / HISTORY_FILE, line)
        if not card.held:
            log.warning("hard_constraint_broken", violations=card.totals.violations)
        if stopped in ("cap", "daily_limit", "interrupted"):
            log.warning("run_resumable", fix="commit the history line, then run with --resume")
        log.info("run_finished", complete=card.complete, passed=card.totals.passed)
        return 0 if card.complete else 1


def _built(args: argparse.Namespace, parts: RunParts) -> _Run:
    checkout = run_checkout(parts.folder, parts.git)
    every = setup.checked_scenarios(checkout.top / setup.CALLS)
    split = [s for s in every if s.split == args.split]
    scenarios = [(s, setup.waiting(s)) for s in split]
    playable = [s for s, skip in scenarios if not skip]
    smoke = next((s for s in every if s.split == "dev" and not setup.waiting(s)), None)
    if smoke is None or not playable:
        raise run_refused("the split has no scenario that plays", "write one, or name the split")
    folder = folder_for(args.out, resume=args.resume, checkout=checkout, git=parts.git)
    settings = for_the_app(setup.call_settings(args.model, args.effort))
    prices, limits = setup.prices_and_limits(args.model, args.price, args.limits)
    done, sessions = read_folder(folder) if args.resume else ([], [])
    played = {(r.scenario, r.repeat) for r in done if not r.smoke}  # a smoke's kept: its violations
    todo = [(s, r) for r in range(1, args.repeats + 1) for s in playable if (s.id, r) not in played]
    before = sum(s.cost_usd for s in sessions)
    most = setup.most_usd([smoke, *(s for s, _ in todo)], args, settings, prices)
    setup.check_estimate(most, before, args.cap_usd, plays=len(todo) + 1)
    began = parts.now()
    data = tuple(s.id for s in split)
    info = setup.run_info(args, folder.out.name, began, checkout.commit, most, prices, limits, data)
    info = folder.resumed(info, git=parts.git, top=checkout.top) if args.resume else info
    history = checkout.top / setup.HISTORY
    today = requests_today(every_history(history), began.astimezone(UTC).date())
    pacers = {
        m: ModelPacer(x, used_today=today.get(m, 0), clock=parts.clock, sleep=parts.sleep)
        for m, x in limits.items()
    }
    spend = Spend(prices=prices, cap_usd=args.cap_usd, before_usd=before)
    inner = parts.chat(args.env_file)  # refused before the folder is made: no key, say
    if not args.resume:
        folder.begin(info)
    paced = PacedChat(
        inner,
        pacers=pacers,
        spend=spend,
        input_budget=args.input_budget_tokens,
        attempts=args.max_attempts,
        sleep=parts.sleep,
    )
    return _Run(
        args,
        parts,
        folder,
        info,
        scenarios,
        smoke,
        todo,
        settings,
        paced,
        history,
        done,
        sessions,
        began,
        checkout.commit,
    )


def main(argv: Sequence[str] | None = None, *, parts: RunParts | None = None) -> int:
    """`uv run poe eval-flights` (the module's docstring): 0 complete, 1 not, 2 refused."""
    args = parser().parse_args(argv)
    configure_logging(loggers=LOGGERS)
    try:
        run = _built(args, parts or RunParts())
    except T2VoiceError as error:
        log.error("flights_refused", code=error.code, message=error.message)
        return 2
    with run.folder.held():
        stopped: Stopped | None = "interrupted"
        try:
            stopped = asyncio.run(run.measure())
        except KeyboardInterrupt:  # recorded as an interrupt, and resumed with --resume
            log.warning("run_interrupted")
        finally:
            code = run.close(stopped)
    log.info("run_session_ended", stopped=stopped, code=code)
    return code


if __name__ == "__main__":
    sys.exit(main())

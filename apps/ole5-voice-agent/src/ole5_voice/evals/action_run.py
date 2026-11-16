"""`poe eval-actions`: run A (plan 007's "The measurement, registered before any result"), the
scripted calls in which the agent acts, over one split, each scenario `--repeats` times (three,
as registered), against the mock ticket system, into a folder, `--out`, with the real model
(`gpt-oss-120b` at medium by default, Q9) and knowledge base, the call's settings those the
server's talker runs under (tickets/tools.py's `with_ticket_claims`).

As `poe eval-scenarios`, a run refuses before anything is sent what it cannot measure: the
checkout, the `--out`, the scenarios (read with `action_scenarios.problems`, refused when they
break a rule), an agent the factory builds without the knowledge tool or the ticket tools, the
prices and limits, the shared history (`run_folder.history_accepts`), and a dry estimate of the
run's most spend past the cap (`--cap-usd`, $10 by default, the owner's): each play's most
requests, each reading `--input-budget-tokens` and writing its model's most (action_setup.py).
Held-out is played only when `--split held-out` names it, and read once: refused when the shared
history holds a complete held-out run of A.

A smoke test comes first, the first dev scenario played once, which must end with no failed,
retried or refused request and no violation (one is counted, and kept for a resumed dev run as
a `smoke` record); then every scenario of the split once, then again, until each has
its repeats, so a run stopped early has played them evenly (action_play.py). A dev play's record
is written as it finishes, with a progress line of identifiers, verdicts and counts (its stray
count among them, D-084), never a text, and its mock's tickets kept under `--out/plays/`; a dev
run stopped by the key's daily limit, the cap or an interrupt goes on with `--resume`. A
held-out run is one whole session: it writes no record, its progress lines are counts only, the
library's lines but its errors held back, and one that does not finish keeps no result but its
violations. Each session, run as runs K's and S's are (session_runner.py), writes the scorecard
(action_card.py) and appends its history line (`action_history.ActionLine`); one violation of
the hard constraint, in any play, fails the run.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar, Final

from pydantic import BaseModel
from t2_agentic_voice import get_logger
from t2_agentic_voice.evals import TextCall, run_checkout, run_refused

from ole5_voice.evals.action_call import ActionCallFactory
from ole5_voice.evals.action_card import ActionRun, ActionScorecard, scorecard
from ole5_voice.evals.action_history import action_line
from ole5_voice.evals.action_play import ActionPlaying
from ole5_voice.evals.action_scenarios import ACTIONS_DIR, SPLITS, ActionScenario
from ole5_voice.evals.action_score import ActionPlayRecord
from ole5_voice.evals.action_setup import (
    AgentFactory,
    check_estimate,
    checked_agent,
    held_out_done,
    load_scenarios,
    most_usd,
)
from ole5_voice.evals.cli import count
from ole5_voice.evals.factories import Closing, knowledge_of
from ole5_voice.evals.items import HISTORY_FILE
from ole5_voice.evals.judge import Judge
from ole5_voice.evals.kb_points import RecordingKnowledge, digest
from ole5_voice.evals.run_folder import folder_for
from ole5_voice.evals.run_parts import DATA
from ole5_voice.evals.run_settings import env_file_of
from ole5_voice.evals.session_runner import (
    SessionRun,
    check_history,
    closed,
    earlier,
    evenly,
    first_session,
    main_of,
    paced_chat,
)
from ole5_voice.evals.talker_args import (
    TalkerParts,
    add_common,
    call_settings,
    chat_settings,
    require,
    shown,
)
from ole5_voice.evals.talker_score import PriceShown, Session, Stopped
from ole5_voice.tickets.tools import with_ticket_claims

REPEATS: Final = 3  # each scenario three times (the registration's run A)
MODEL: Final = "openai/gpt-oss-120b"  # the registered model and effort (Q9)
EFFORT: Final = "medium"
CAP_USD: Final = 10.00  # the owner's cap of 2026-11-10 (plan 007's Decision log)
PLAYS_DIR: Final = "plays"  # under --out, each dev play's mock
_DESCRIPTION = "Play run A's scripted ticket calls over one split, each three times, into --out."
log = get_logger(__name__)


@dataclass(frozen=True)
class ActionParts(TalkerParts):
    """What a run of A is built from, each replaceable by a test's fake: run K's and S's parts
    (`TalkerParts`), the call (`TextCall`, with a caller and an outbox), and whether the shared
    history holds a complete held-out run of A."""

    action_call: ActionCallFactory = TextCall
    held_out_run: Callable[[Path], bool] = held_out_done


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="poe eval-actions", description=_DESCRIPTION)
    add_common(parser)
    add = parser.add_argument
    add("--split", choices=SPLITS, help="the split the run plays, all of it")
    add("--repeats", type=count, default=REPEATS, help=f"plays a scenario ({REPEATS})")
    parser.set_defaults(model=MODEL, reasoning_effort=EFFORT, cap_usd=CAP_USD)
    return parser


def _require(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    """The command line's checks, as runs K's and S's (`talker_args.require`), but for the
    points' text, which run A does not read."""
    require(parser, args, "split", without=("points_text",))
    if args.points_text is not None:
        parser.error("run A reads no knowledge item's points: no --points-text")


def _run(args: argparse.Namespace, parts: ActionParts) -> int:
    return closed(lambda closing: _built(args, parts, closing))


def _built(args: argparse.Namespace, parts: ActionParts, closing: Closing) -> int:
    checkout = run_checkout(parts.folder, parts.git)
    data_dir = checkout.top / DATA
    folder_of_scenarios = data_dir / ACTIONS_DIR
    every = load_scenarios(folder_of_scenarios)
    split = [scenario for scenario in every if scenario.split == args.split]
    smoke = next(scenario for scenario in every if scenario.split == "dev")
    chat, call = chat_settings(args), with_ticket_claims(call_settings(args))
    kb = closing.add(knowledge_of(parts.load_factory, args.knowledge, env_file_of(args)))
    recording = RecordingKnowledge(kb)
    make = AgentFactory(parts.load_factory(args.agent), args.agent)
    agent = checked_agent(make, recording, args.search_tool)
    history = data_dir / HISTORY_FILE
    held_out = args.split == "held-out"
    if held_out and parts.held_out_run(history):
        raise run_refused(
            "the shared history holds a complete held-out run of A, and held-out is read once",
            "record its result; a target missed goes to the plan's Future improvements",
        )
    folder = folder_for(args.out, resume=args.resume, checkout=checkout, git=parts.git)
    done, sessions = earlier(folder, ActionPlayRecord, resume=args.resume)
    smokes = [play for play in done if play.smoke]  # an earlier smoke test's violations
    done = [play for play in done if not play.smoke]
    began, paced = paced_chat(args, parts, closing, chat, history, sessions)
    info = ActionRun(
        name=folder.out.name,
        started_at=began,
        commit=checkout.commit,
        arm=args.arm,
        model=args.model,
        judge_model=args.judge_model,
        split=args.split,
        settings=shown(args, chat, call, agent) | {"run.repeats": str(args.repeats)},
        prices={
            m: PriceShown(input_usd=p.input_usd, output_usd=p.output_usd) for m, p in args.price
        },
        cap_usd=args.cap_usd,
        estimate_usd=round(most_usd(args, paced, [smoke, *split * args.repeats]), 6),
        data_digest=digest(sorted(folder_of_scenarios.glob("*.toml"))),
        note=args.note,
        repeats=args.repeats,
        smoke_only=args.smoke_only,
    )
    if args.resume:
        info = folder.resumed(info)
    probe = scorecard(info, split, [], complete=False, stopped=None, sessions=[])
    line = action_line(probe, first_session(info.started_at), 1, len(split))
    check_history(parts, line, "A", "action_history.ActionLine")
    todo = evenly(split, args.repeats, ((play.scenario, play.repeat) for play in done))
    check_estimate(args, paced, [smoke, *(scenario for scenario, _ in todo)], whole_day=held_out)
    playing = ActionPlaying(
        agent=make,
        paced=paced,
        settings=call,
        knowledge=recording,
        judge=Judge(paced, model=args.judge_model, max_output_tokens=args.judge_max_output_tokens),
        search_tool=args.search_tool,
        timeout_s=args.variant_timeout_s,
        call=parts.action_call,
        clock=parts.clock,
        kept=None if held_out else folder.out / PLAYS_DIR,
    )
    if not args.resume:
        folder.begin(info)
    log.info("run_started", run=info.name, split=info.split, plays=len(todo), done=len(done))
    session = _Session(
        folder=folder,
        data=data_dir,
        parts=parts,
        closing=closing,
        paced=paced,
        began=began,
        sessions=sessions,
        done=done,
        todo=todo,
        expected=1 if args.smoke_only else args.repeats * len(split),
        held_out=held_out,
        smoke_only=args.smoke_only,
        info=info,
        split=split,
        smoke=smoke,
        playing=playing,
        dropped=sum(len(play.violations) for play in smokes),
    )
    return session.run()


@dataclass(kw_only=True)
class _Session(SessionRun[tuple[ActionScenario, int], ActionPlayRecord, ActionScorecard]):
    """A session of run A (session_runner.py): each scenario's play one call against its own
    mock, checked turn by turn (action_play.py); the smoke test the first dev scenario, whose
    violations are counted, and kept for a resumed dev run as a `smoke` record, though its play
    is not the run's (`dropped`, with an unfinished held-out run's)."""

    event: ClassVar[str] = "play_done"
    info: ActionRun
    split: list[ActionScenario]
    smoke: ActionScenario
    playing: ActionPlaying
    dropped: int  # the violations of plays the scorecard does not keep

    async def smoke_record(self) -> ActionPlayRecord:
        record = await self.playing.play(self.smoke, 1, name=f"smoke-{self.smoke.id}")
        if record.violations:  # the hard constraint broken: counted, and kept for --resume
            self.dropped += len(record.violations)
            if not self.held_out:
                self.folder.add_result(record.model_copy(update={"smoke": True}))
        return record

    async def record(self, each: tuple[ActionScenario, int]) -> ActionPlayRecord:
        scenario, repeat = each
        return await self.playing.play(scenario, repeat, name=f"{scenario.id}-r{repeat}")

    def smoke_check(self, record: ActionPlayRecord) -> tuple[bool, dict[str, object]]:
        broke = record.failure is not None or bool(record.violations)
        return broke, {"failure": record.failure, "violations": len(record.violations)}

    def shown(
        self, each: tuple[ActionScenario, int], record: ActionPlayRecord
    ) -> dict[str, object]:
        return {
            "scenario": record.scenario,
            "repeat": each[1],
            "passed": record.passed,
            "failure": record.failure,
            "violations": len(record.violations),
            "stray_characters": record.stray_characters,
            "seconds": round(record.seconds, 2),
        }

    def kept(self, every: list[ActionPlayRecord], complete: bool) -> list[ActionPlayRecord]:
        """As every run's, but an unfinished held-out run's violations are counted still."""
        kept = super().kept(every, complete)
        if kept is not every:  # no result, but its violations: it is run again
            self.dropped += sum(len(play.violations) for play in every)
        return kept

    def scorecard(
        self,
        records: list[ActionPlayRecord],
        *,
        complete: bool,
        stopped: Stopped | None,
        sessions: list[Session],
    ) -> ActionScorecard:
        return scorecard(
            self.info,
            self.split,
            records,
            complete=complete,
            stopped=stopped,
            sessions=sessions,
            dropped=self.dropped,
        )

    def line(self, card: ActionScorecard, session: Session, number: int) -> BaseModel:
        return action_line(card, session, number, len(self.split))

    def finished(self, card: ActionScorecard, records: list[ActionPlayRecord]) -> dict[str, object]:
        if card.held is False:
            log.warning("hard_constraint_broken", violations=card.totals.violations)
        return {"plays": len(records), "passed": card.passed}


def main(argv: Sequence[str] | None = None, *, parts: ActionParts | None = None) -> int:
    """`uv run poe eval-actions`: play run A's scenarios over one split. 0 when the run is
    complete, 1 when it is not (a failed smoke test, the cap, the day's limit, an interrupt, a
    library error once it began), 2 when it is refused before anything is sent; whether it
    passed is its scorecard's."""
    parser = _parser()
    args = parser.parse_args(argv)
    found = ActionParts() if parts is None else parts
    return main_of(parser, args, _require, lambda given: _run(given, found), "actions_refused")


if __name__ == "__main__":
    sys.exit(main())

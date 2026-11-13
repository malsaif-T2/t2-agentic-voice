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
violations. Each session writes the scorecard (action_card.py) and appends its history line
(`action_history.ActionLine`); one violation of the hard constraint, in any play, fails the run.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Final

from t2_agentic_voice import T2VoiceError, configure_logging, get_logger
from t2_agentic_voice.evals import TextCall

from ole5_voice import LOGGERS
from ole5_voice.evals.action_call import ActionCallFactory
from ole5_voice.evals.action_card import ActionRun, scorecard
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
from ole5_voice.evals.chat_pacing import Spend
from ole5_voice.evals.cli import count
from ole5_voice.evals.factories import Closing, env_file_of, knowledge_of
from ole5_voice.evals.items import HISTORY_FILE
from ole5_voice.evals.judge import Judge
from ole5_voice.evals.kb_points import RecordingKnowledge, digest
from ole5_voice.evals.run_folder import RunFolder, folder_for
from ole5_voice.evals.run_parts import DATA
from ole5_voice.evals.talker_args import (
    TalkerParts,
    add_common,
    call_settings,
    chat_settings,
    pacing,
    require,
    shown,
)
from ole5_voice.evals.talker_measure import StopRun
from ole5_voice.evals.talker_score import PriceShown, Session, Stopped
from ole5_voice.evals.worktree import refused, run_checkout
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


@dataclass
class _Found:
    plays: list[ActionPlayRecord] = field(default_factory=list)
    stopped: Stopped | None = None
    dropped: int = 0  # the violations of the smoke tests, whose plays are not the run's


def _run(args: argparse.Namespace, parts: ActionParts) -> int:
    """The run, what it built closed whenever it ends, a refusal's included."""
    closing = Closing()
    try:
        return _built(args, parts, closing)
    finally:
        closing.close_now()


def _built(args: argparse.Namespace, parts: ActionParts, closing: Closing) -> int:
    checkout = run_checkout(parts.folder, parts.git)
    folder_of_scenarios = checkout.top / DATA / ACTIONS_DIR
    every = load_scenarios(folder_of_scenarios)
    split = [scenario for scenario in every if scenario.split == args.split]
    smoke = next(scenario for scenario in every if scenario.split == "dev")
    chat, call = chat_settings(args), with_ticket_claims(call_settings(args))
    kb = closing.add(knowledge_of(parts.load_factory, args.knowledge, env_file_of(args)))
    recording = RecordingKnowledge(kb)
    make = AgentFactory(parts.load_factory(args.agent), args.agent)
    agent = checked_agent(make, recording, args.search_tool)
    history = checkout.top / DATA / HISTORY_FILE
    held_out = args.split == "held-out"
    if held_out and parts.held_out_run(history):
        raise refused(
            "the shared history holds a complete held-out run of A, and held-out is read once",
            "record its result; a target missed goes to the plan's Future improvements",
        )
    folder = folder_for(args.out, resume=args.resume, checkout=checkout, git=parts.git)
    done: list[ActionPlayRecord] = []
    sessions: list[Session] = []
    if args.resume:
        done, sessions = folder.results(ActionPlayRecord), folder.sessions(Session)
    smokes = [play for play in done if play.smoke]  # an earlier smoke test's violations
    done = [play for play in done if not play.smoke]
    began = parts.now()
    paced = pacing(
        args,
        closing.add(parts.chat(chat)),
        today=parts.requests_today(history, began.date()),
        before_usd=sum(session.cost_usd for session in sessions),
        parts=parts,
    )
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
    first = Session(started_at=info.started_at, stopped=None, variants=0)
    if not parts.history_accepts(action_line(probe, first, 1, len(split))):
        raise refused(
            "the shared history takes no line of run A's kind yet",
            "name action_history.ActionLine in run_lines.AnyLine, as the integration does",
        )
    keys = {(play.scenario, play.repeat) for play in done}
    todo = [
        (scenario, repeat)
        for repeat in range(1, args.repeats + 1)
        for scenario in split
        if (scenario.id, repeat) not in keys
    ]
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
    found = _Found(dropped=sum(len(play.violations) for play in smokes))
    log.info("run_started", run=info.name, split=info.split, plays=len(todo), done=len(done))
    try:
        asyncio.run(_measure(playing, smoke, todo, found, folder, args, closing))
    except KeyboardInterrupt:
        found.stopped = "interrupted"
        log.warning("run_interrupted", done=len(found.plays), of=len(todo))
    except BaseException as error:
        found.stopped = "error"
        log.error("run_failed", error=type(error).__name__, done=len(found.plays))
        raise
    finally:
        expected = 1 if args.smoke_only else args.repeats * len(split)
        _close(
            info,
            split,
            folder,
            [*done, *found.plays],
            found,
            expected=expected,
            sessions=sessions,
            spend=paced.spend,
            began=began,
            parts=parts,
            history=history,
        )
    return 0 if found.stopped is None else 1


async def _measure(
    playing: ActionPlaying,
    smoke: ActionScenario,
    todo: Sequence[tuple[ActionScenario, int]],
    found: _Found,
    folder: RunFolder,
    args: argparse.Namespace,
    closing: Closing,
) -> None:
    held_out = args.split == "held-out"
    spend = playing.paced.spend
    try:
        record = await playing.play(smoke, 1, name=f"smoke-{smoke.id}")
        if record.violations:  # the hard constraint broken: counted, and kept for --resume
            found.dropped += len(record.violations)
            if not held_out:
                folder.add_result(record.model_copy(update={"smoke": True}))
        if record.failure is not None or record.violations or spend.retries_and_failures():
            found.stopped = "smoke_failed"
            log.error(
                "smoke_failed",
                failure=record.failure,
                violations=len(record.violations),
                requests=spend.requests(),
            )
            return
        log.info("smoke_passed", requests=spend.requests())
        if args.smoke_only:
            found.plays.append(record)
            folder.add_result(record)
            return
        for number, (scenario, repeat) in enumerate(todo, start=1):
            record = await playing.play(scenario, repeat, name=f"{scenario.id}-r{repeat}")
            found.plays.append(record)
            if held_out:
                log.info("play_done", done=number, of=len(todo))
                continue
            folder.add_result(record)
            log.info(
                "play_done",
                done=number,
                of=len(todo),
                scenario=record.scenario,
                repeat=repeat,
                passed=record.passed,
                failure=record.failure,
                violations=len(record.violations),
                stray_characters=record.stray_characters,
                seconds=round(record.seconds, 2),
            )
    except StopRun as stop:
        found.stopped = stop.reason
        log.warning("run_stopped", reason=stop.reason, done=len(found.plays), of=len(todo))
    finally:
        await closing.aclose()  # the chat model and the knowledge base, in the run's own loop


def _close(
    info: ActionRun,
    split: Sequence[ActionScenario],
    folder: RunFolder,
    plays: list[ActionPlayRecord],
    found: _Found,
    *,
    expected: int,
    sessions: list[Session],
    spend: Spend,
    began: datetime,
    parts: ActionParts,
    history: Path,
) -> None:
    """The session, the scorecard and the session's history line, whatever stopped the run."""
    stopped = found.stopped
    complete = stopped is None and len(plays) == expected
    dropped = found.dropped
    if info.split == "held-out" and not complete:  # no result, but its violations: run again
        dropped += sum(len(play.violations) for play in plays)
        plays = []
    session = Session(
        started_at=began,
        stopped=stopped,
        variants=len(found.plays),
        spend=spend.spent(),
        cost_usd=spend.session_usd(),
    )
    folder.add_session(session)
    every = [*sessions, session]
    card = scorecard(
        info, split, plays, complete=complete, stopped=stopped, sessions=every, dropped=dropped
    )
    folder.write_scorecard(card)
    line = action_line(card, session, len(every), len(split))
    parts.append_line(line, history)
    parts.append_line(line, folder.out / HISTORY_FILE)
    if card.held is False:
        log.warning("hard_constraint_broken", violations=card.totals.violations)
    if stopped in ("daily_limit", "cap", "interrupted") and info.split == "dev":
        log.warning("run_resumable", fix="run the same command with --resume to go on")
    log.info("run_finished", complete=complete, plays=len(plays), passed=card.passed)


def main(argv: Sequence[str] | None = None, *, parts: ActionParts | None = None) -> int:
    """`uv run poe eval-actions`: play run A's scenarios over one split. 0 when the run is
    complete, 1 when it is not (a failed smoke test, the cap, the day's limit, an interrupt), 2
    when it is refused before anything is sent; whether it passed is its scorecard's."""
    parser = _parser()
    args = parser.parse_args(argv)
    _require(parser, args)
    configure_logging(loggers=LOGGERS)
    if args.split == "held-out":  # the library's lines would tell each play's path apart
        logging.getLogger("t2_agentic_voice").setLevel(logging.ERROR)
    try:
        return _run(args, ActionParts() if parts is None else parts)
    except T2VoiceError as error:
        log.error("actions_refused", code=error.code, message=error.message)
        return 2


if __name__ == "__main__":
    sys.exit(main())

"""`poe eval-scenarios`: run S (plan 006's registration), the ten scripted calls with the kept
arm, each `--repeats` times (three, as registered), into a folder, `--out`, with the real model
and knowledge base.

As `poe eval-talker`, a run refuses before anything is sent what it cannot measure (the checkout,
the `--out`, the data, the agent, the prices and limits, the cap, the shared history), and also
scenarios that break a rule (`scenarios.problems`). A smoke test comes first, the first scenario
played once, which must end with no failed, retried or refused request; then every scenario
once, then every scenario again, until each has its repeats, so a run stopped early has played
the scenarios evenly. Each play is one call, then checked turn by turn (`scenario_play.py`); its
record is written as it finishes, with a progress line of identifiers and verdicts, never a
text. A run stopped by the key's daily limit, the cap or an interrupt goes on with `--resume`.
Each session, run as runs K's and A's are (session_runner.py), writes the scorecard and appends
its history line (`talker_lines.ScenarioLine`).
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar, Final

from pydantic import BaseModel
from t2_agentic_voice import get_logger
from t2_agentic_voice.evals import run_checkout, run_refused

from ole5_voice.evals.cli import count
from ole5_voice.evals.factories import Closing
from ole5_voice.evals.items import HISTORY_FILE, GoldenSetError
from ole5_voice.evals.judge import JUDGE_REQUESTS, Judge
from ole5_voice.evals.kb_points import KnowledgeData, load_knowledge
from ole5_voice.evals.run_folder import folder_for
from ole5_voice.evals.run_parts import DATA
from ole5_voice.evals.scenario_play import Playing
from ole5_voice.evals.scenario_score import PlayRecord, ScenarioRun, ScenarioScorecard, scorecard
from ole5_voice.evals.scenarios import SCENARIOS_DIR, Scenario, load_scenarios, problems
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
    check_budget,
    require,
    shown,
)
from ole5_voice.evals.talker_lines import scenario_line
from ole5_voice.evals.talker_measure import TALKER_REQUESTS
from ole5_voice.evals.talker_run import agent_of
from ole5_voice.evals.talker_score import PriceShown, Session, Stopped

REPEATS: Final = 3  # each scenario three times (the registration's S)
_DESCRIPTION = "Play run S's scripted calls with the kept arm, each three times, into --out."
_LINE: Final = "talker_lines.ScenarioLine"
log = get_logger(__name__)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="poe eval-scenarios", description=_DESCRIPTION)
    add_common(parser)
    parser.add_argument(
        "--repeats", type=count, default=REPEATS, help=f"plays a scenario ({REPEATS})"
    )
    return parser


def _scenarios(data_dir: Path, data: KnowledgeData) -> tuple[Scenario, ...]:
    try:
        found = load_scenarios(data_dir / SCENARIOS_DIR)
    except GoldenSetError as error:
        raise run_refused(
            f"the scenarios cannot be read ({error})", "fix them; `poe check`"
        ) from None
    if broken := problems(found, list(data.items.values())):
        raise run_refused(
            f"the scenarios break {len(broken)} rule(s), first: {broken[0]}", "fix them"
        )
    data.check_texts([data.items[t.item] for s in found for t in s.turns if t.item])
    return found


def _run(args: argparse.Namespace, parts: TalkerParts) -> int:
    return closed(lambda closing: _built(args, parts, closing))


def _built(args: argparse.Namespace, parts: TalkerParts, closing: Closing) -> int:
    checkout = run_checkout(parts.folder, parts.git)
    data_dir = checkout.top / DATA
    files = sorted((data_dir / SCENARIOS_DIR).glob("*.toml"))
    data = load_knowledge(data_dir, args.points_text, files)
    scenarios = _scenarios(data_dir, data)
    chat, call = chat_settings(args), call_settings(args)
    agent, recording = agent_of(args, parts, closing)
    folder = folder_for(args.out, resume=args.resume, checkout=checkout, git=parts.git)
    info = ScenarioRun(
        name=folder.out.name,
        started_at=parts.now(),
        commit=checkout.commit,
        arm=args.arm,
        model=args.model,
        judge_model=args.judge_model,
        settings=shown(args, chat, call, agent) | {"run.repeats": str(args.repeats)},
        prices={
            m: PriceShown(input_usd=p.input_usd, output_usd=p.output_usd) for m, p in args.price
        },
        cap_usd=args.cap_usd,
        data_digest=data.digest,
        note=args.note,
        repeats=args.repeats,
        smoke_only=args.smoke_only,
    )
    if args.resume:
        info = folder.resumed(info)
    done, sessions = earlier(folder, PlayRecord, resume=args.resume)
    probe = scorecard(info, scenarios, [], complete=False, stopped=None, sessions=[])
    check_history(parts, scenario_line(probe, first_session(info.started_at), 1), "S", _LINE)
    began, paced = paced_chat(args, parts, closing, chat, data_dir / HISTORY_FILE, sessions)
    todo = evenly(scenarios, args.repeats, ((play.scenario, play.repeat) for play in done))
    turns = max(len(scenario.turns) for scenario in scenarios)
    requests = {args.model: TALKER_REQUESTS * turns, args.judge_model: JUDGE_REQUESTS * turns}
    check_budget(args, paced, units=len(todo) + 1, requests=requests, whole_day=False)
    playing = Playing(
        agent=agent,
        paced=paced,
        settings=call,
        knowledge=recording,
        data=data,
        judge=Judge(paced, model=args.judge_model, max_output_tokens=args.judge_max_output_tokens),
        search_tool=args.search_tool,
        timeout_s=args.variant_timeout_s,
        call=parts.call,
        clock=parts.clock,
    )
    if not args.resume:
        folder.begin(info)
    log.info("run_started", run=info.name, plays=len(todo), done=len(done))
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
        expected=1 if args.smoke_only else args.repeats * len(scenarios),
        held_out=False,
        smoke_only=args.smoke_only,
        info=info,
        scenarios=scenarios,
        playing=playing,
    )
    return session.run()


@dataclass(kw_only=True)
class _Session(SessionRun[tuple[Scenario, int], PlayRecord, ScenarioScorecard]):
    """A session of run S (session_runner.py): each scenario's play one call, checked turn by
    turn (scenario_play.py), the smoke test the first scenario played once."""

    event: ClassVar[str] = "play_done"
    info: ScenarioRun
    scenarios: tuple[Scenario, ...]
    playing: Playing

    async def smoke_record(self) -> PlayRecord:
        return await self.playing.play(self.scenarios[0], 1)

    async def record(self, each: tuple[Scenario, int]) -> PlayRecord:
        return await self.playing.play(*each)

    def smoke_check(self, record: PlayRecord) -> tuple[bool, dict[str, object]]:
        return record.failure is not None, {"failure": record.failure}

    def shown(self, each: tuple[Scenario, int], record: PlayRecord) -> dict[str, object]:
        return {
            "scenario": record.scenario,
            "repeat": each[1],
            "passed": record.passed,
            "failure": record.failure,
            "seconds": round(record.seconds, 2),
        }

    def scorecard(
        self,
        records: list[PlayRecord],
        *,
        complete: bool,
        stopped: Stopped | None,
        sessions: list[Session],
    ) -> ScenarioScorecard:
        return scorecard(
            self.info,
            self.scenarios,
            records,
            complete=complete,
            stopped=stopped,
            sessions=sessions,
        )

    def line(self, card: ScenarioScorecard, session: Session, number: int) -> BaseModel:
        return scenario_line(card, session, number)

    def finished(self, card: ScenarioScorecard, records: list[PlayRecord]) -> dict[str, object]:
        return {"plays": len(records), "cost_usd": card.cost_usd}


def main(argv: Sequence[str] | None = None, *, parts: TalkerParts | None = None) -> int:
    """`uv run poe eval-scenarios`: play run S's scenarios. 0 when the run is complete, 1 when
    it is not (a failed smoke test, the cap, the day's limit, an interrupt, a library error once
    it began), 2 when it is refused before anything is sent."""
    parser = _parser()
    args = parser.parse_args(argv)
    found = TalkerParts() if parts is None else parts
    return main_of(parser, args, require, lambda given: _run(given, found), "scenarios_refused")


if __name__ == "__main__":
    sys.exit(main())

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
Each session writes the scorecard and appends its history line (`talker_lines.ScenarioLine`).
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

from t2_agentic_voice import T2VoiceError, configure_logging, get_logger

from ole5_voice import LOGGERS
from ole5_voice.evals.factories import Closing
from ole5_voice.evals.items import HISTORY_FILE, GoldenSetError
from ole5_voice.evals.judge import JUDGE_REQUESTS, Judge
from ole5_voice.evals.kb_points import KnowledgeData, load_knowledge
from ole5_voice.evals.run_folder import RunFolder, folder_for
from ole5_voice.evals.run_parts import DATA
from ole5_voice.evals.scenario_play import Playing
from ole5_voice.evals.scenario_score import PlayRecord, ScenarioRun, scorecard
from ole5_voice.evals.scenarios import SCENARIOS_DIR, Scenario, load_scenarios, problems
from ole5_voice.evals.talker_args import (
    TalkerParts,
    add_common,
    call_settings,
    chat_settings,
    check_budget,
    pacing,
    require,
    shown,
)
from ole5_voice.evals.talker_lines import scenario_line
from ole5_voice.evals.talker_measure import TALKER_REQUESTS, StopRun
from ole5_voice.evals.talker_run import agent_of
from ole5_voice.evals.talker_score import PriceShown, Session, Stopped
from ole5_voice.evals.worktree import refused, run_checkout

REPEATS: Final = 3  # each scenario three times (the registration's S)
_DESCRIPTION = "Play run S's scripted calls with the kept arm, each three times, into --out."
log = get_logger(__name__)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="poe eval-scenarios", description=_DESCRIPTION)
    add_common(parser)
    parser.add_argument(
        "--repeats", type=int, default=REPEATS, help=f"plays a scenario ({REPEATS})"
    )
    return parser


def _require(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    require(parser, args)
    if args.repeats < 1:
        parser.error("--repeats is 1 or more")


@dataclass
class _Found:
    plays: list[PlayRecord] = field(default_factory=list)
    stopped: Stopped | None = None


def _scenarios(data_dir: Path, data: KnowledgeData) -> tuple[Scenario, ...]:
    try:
        found = load_scenarios(data_dir / SCENARIOS_DIR)
    except GoldenSetError as error:
        raise refused(f"the scenarios cannot be read ({error})", "fix them; `poe check`") from None
    if broken := problems(found, list(data.items.values())):
        raise refused(f"the scenarios break {len(broken)} rule(s), first: {broken[0]}", "fix them")
    data.check_texts([data.items[t.item] for s in found for t in s.turns if t.item])
    return found


def _run(args: argparse.Namespace, parts: TalkerParts) -> int:
    """The run, what it built closed whenever it ends, a refusal's included."""
    closing = Closing()
    try:
        return _built(args, parts, closing)
    finally:
        closing.close_now()


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
    done: list[PlayRecord] = []
    sessions: list[Session] = []
    if args.resume:
        info = folder.resumed(info)
        done, sessions = folder.results(PlayRecord), folder.sessions(Session)
    history = checkout.top / DATA / HISTORY_FILE
    probe = scorecard(info, scenarios, [], complete=False, stopped=None, sessions=[])
    if not parts.history_accepts(
        scenario_line(probe, Session(started_at=info.started_at, stopped=None, variants=0), 1)
    ):
        raise refused(
            "the shared history takes no line of run S's kind yet",
            "name talker_lines.ScenarioLine in run_lines.AnyLine, as the integration does",
        )
    began = parts.now()
    paced = pacing(
        args,
        closing.add(parts.chat(chat)),
        today=parts.requests_today(history, began.date()),
        before_usd=sum(session.cost_usd for session in sessions),
        parts=parts,
    )
    keys = {(play.scenario, play.repeat) for play in done}
    todo = [
        (scenario, repeat)
        for repeat in range(1, args.repeats + 1)
        for scenario in scenarios
        if (scenario.id, repeat) not in keys
    ]
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
    found = _Found()
    log.info("run_started", run=info.name, plays=len(todo), done=len(done))
    try:
        asyncio.run(_measure(playing, scenarios[0], todo, found, folder, args.smoke_only, closing))
    except KeyboardInterrupt:
        found.stopped = "interrupted"
        log.warning("run_interrupted", done=len(found.plays), of=len(todo))
    except BaseException as error:
        found.stopped = "error"
        log.error("run_failed", error=type(error).__name__, done=len(found.plays))
        raise
    finally:
        expected = 1 if args.smoke_only else args.repeats * len(scenarios)
        every = done + found.plays
        complete = found.stopped is None and len(every) == expected
        session = Session(
            started_at=began,
            stopped=found.stopped,
            variants=len(found.plays),
            spend=paced.spend.spent(),
            cost_usd=paced.spend.session_usd(),
        )
        folder.add_session(session)
        card = scorecard(
            info,
            scenarios,
            every,
            complete=complete,
            stopped=found.stopped,
            sessions=[*sessions, session],
        )
        folder.write_scorecard(card)
        line = scenario_line(card, session, len(sessions) + 1)
        parts.append_line(line, history)
        parts.append_line(line, folder.out / HISTORY_FILE)
        log.info("run_finished", complete=complete, plays=len(every), cost_usd=card.cost_usd)
    return 0 if found.stopped is None else 1


async def _measure(
    playing: Playing,
    smoke: Scenario,
    todo: Sequence[tuple[Scenario, int]],
    found: _Found,
    folder: RunFolder,
    smoke_only: bool,
    closing: Closing,
) -> None:
    spend = playing.paced.spend
    try:
        record = await playing.play(smoke, 1)
        if record.failure is not None or spend.retries_and_failures():
            found.stopped = "smoke_failed"
            log.error("smoke_failed", failure=record.failure, requests=spend.requests())
            return
        log.info("smoke_passed", requests=spend.requests())
        if smoke_only:
            found.plays.append(record)
            folder.add_result(record)
            return
        for number, (scenario, repeat) in enumerate(todo, start=1):
            record = await playing.play(scenario, repeat)
            found.plays.append(record)
            folder.add_result(record)
            log.info(
                "play_done",
                done=number,
                of=len(todo),
                scenario=record.scenario,
                repeat=repeat,
                passed=record.passed,
                failure=record.failure,
                seconds=round(record.seconds, 2),
            )
    except StopRun as stop:
        found.stopped = stop.reason
        log.warning("run_stopped", reason=stop.reason, done=len(found.plays), of=len(todo))
    finally:
        await closing.aclose()  # the chat model and the knowledge base, in the run's own loop


def main(argv: Sequence[str] | None = None, *, parts: TalkerParts | None = None) -> int:
    """`uv run poe eval-scenarios`: play run S's scenarios. 0 when the run is complete, 1 when
    it is not, 2 when it is refused before anything is sent."""
    parser = _parser()
    args = parser.parse_args(argv)
    _require(parser, args)
    configure_logging(loggers=LOGGERS)
    try:
        return _run(args, TalkerParts() if parts is None else parts)
    except T2VoiceError as error:
        log.error("scenarios_refused", code=error.code, message=error.message)
        return 2


if __name__ == "__main__":
    sys.exit(main())

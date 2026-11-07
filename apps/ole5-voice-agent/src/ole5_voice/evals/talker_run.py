"""`poe eval-talker`: run K (plan 006's registration), one arm over one split of the knowledge
set, every variant once, into a folder, `--out`, with the real model and knowledge base.

Before anything is sent, a run refuses the main checkout and a dirty tree, an `--out` that exists
or that git would track, a knowledge set or a points' snapshot that cannot be read or lacks an
expected point's text, an agent without the `--search-tool` or the languages its calls need, a
model with no price or limits, a cap with no room for one variant, a held-out run whose requests
would not fit the day's limit, and a shared history that cannot hold its line
(`run_folder.history_accepts`). Its settings are pinned on the command line (`talker_args`).

A smoke test comes first, the first dev variant (for a held-out run too), which must pass with
no failed, retried or refused request; then each variant (`talker_measure.py`), its record
written as it finishes (a dev run's `results.jsonl`) with a progress line of identifiers,
verdicts and times, never a text. A held-out run writes no record, its progress lines are counts
only, and one that does not finish keeps no result. A dev run stopped by the key's daily limit,
the cap or an interrupt goes on with `--resume` and the same command line, its finished variants
kept. Each session writes the scorecard (`talker_score.py`) and appends its history line
(`talker_lines.TalkerLine`) to the worktree's `history.jsonl`, copied beside the scorecard.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Final, get_args

from t2_agentic_voice import T2VoiceError, VoiceAgent, configure_logging, get_logger

from ole5_voice import LOGGERS
from ole5_voice.evals.chat_pacing import Spend
from ole5_voice.evals.factories import Closing, env_file_of, knowledge_of
from ole5_voice.evals.factories import agent_of as built_agent
from ole5_voice.evals.items import HISTORY_FILE
from ole5_voice.evals.judge import JUDGE_ATTEMPTS, Judge
from ole5_voice.evals.kb_points import KnowledgeData, RecordingKnowledge, load_knowledge
from ole5_voice.evals.models import Split
from ole5_voice.evals.run_folder import RunFolder, folder_for
from ole5_voice.evals.run_parts import DATA
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
from ole5_voice.evals.talker_data import TAGS
from ole5_voice.evals.talker_lines import talker_line
from ole5_voice.evals.talker_measure import CallLanguage, Measuring, StopRun, Todo, todo_of
from ole5_voice.evals.talker_score import (
    PriceShown,
    Session,
    Stopped,
    TalkerRun,
    VariantRecord,
    scorecard,
)
from ole5_voice.evals.worktree import refused, run_checkout

TALKER_REQUESTS: Final = 3  # the most model requests the talker sends a turn
_DESCRIPTION = "Run the talker over one split of the knowledge set, one arm, into --out."
log = get_logger(__name__)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="poe eval-talker", description=_DESCRIPTION)
    add_common(parser)
    add = parser.add_argument
    add("--split", choices=get_args(Split), help="the split the run covers, all of it")
    add(
        "--call-language",
        choices=get_args(CallLanguage),
        help="each call held in the agent's first language, or in its variant's (Q9's run X)",
    )
    return parser


def _require(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    require(parser, args, "split", "call_language")
    if args.split == "held-out" and (args.resume or args.smoke_only):
        parser.error("a held-out run is one whole session: no --resume or --smoke-only")


@dataclass
class _Found:
    results: list[VariantRecord] = field(default_factory=list)
    stopped: Stopped | None = None


def agent_of(
    args: argparse.Namespace, parts: TalkerParts, closing: Closing
) -> tuple[VoiceAgent, RecordingKnowledge]:
    """The agent the factories build (factories.py), on the knowledge base behind a recorder,
    the base kept in `closing`; refused when either is not what it should be, or the agent has
    no `--search-tool`."""
    kb = closing.add(knowledge_of(parts.load_factory, args.knowledge, env_file_of(args)))
    recording = RecordingKnowledge(kb)
    agent = built_agent(parts.load_factory, args.agent, recording)
    if args.search_tool not in {tool.name for tool in agent.tools}:
        raise refused(f"the agent has no tool {args.search_tool}", "give its knowledge tool's name")
    return agent, recording


def _plan(
    args: argparse.Namespace, data: KnowledgeData, agent: VoiceAgent
) -> tuple[Todo, list[Todo]]:
    """The smoke test's variant and the split's; refused when a call could not be held."""
    items = list(data.items.values())
    dev, todo = todo_of(items, "dev"), todo_of(items, args.split)
    if not dev or not todo:
        raise refused("the knowledge set holds no dev variant, or none of the split", "fix it")
    data.check_texts([each.item for each in (dev[0], *todo)])
    spoken = {language.tag for language in agent.languages}
    if args.call_language == "variant" and (
        lacking := sorted({t.asked.language for t in todo if TAGS[t.asked.language] not in spoken})
    ):
        raise refused(
            f"the agent speaks no language of the {', '.join(lacking)} variants",
            "hold the calls in the agent's first language (--call-language first)",
        )
    return dev[0], todo


def _run(args: argparse.Namespace, parts: TalkerParts) -> int:
    """The run, what it built closed whenever it ends, a refusal's included."""
    closing = Closing()
    try:
        return _built(args, parts, closing)
    finally:
        closing.close_now()


def _built(args: argparse.Namespace, parts: TalkerParts, closing: Closing) -> int:
    checkout = run_checkout(parts.folder, parts.git)
    data = load_knowledge(checkout.top / DATA, args.points_text)
    chat, call = chat_settings(args), call_settings(args)
    agent, recording = agent_of(args, parts, closing)
    smoke, todo = _plan(args, data, agent)
    folder = folder_for(args.out, resume=args.resume, checkout=checkout, git=parts.git)
    info = TalkerRun(
        name=folder.out.name,
        started_at=parts.now(),
        commit=checkout.commit,
        arm=args.arm,
        model=args.model,
        judge_model=args.judge_model,
        split=args.split,
        settings=shown(args, chat, call, agent),
        prices={
            m: PriceShown(input_usd=p.input_usd, output_usd=p.output_usd) for m, p in args.price
        },
        cap_usd=args.cap_usd,
        data_digest=data.digest,
        note=args.note,
        smoke_only=args.smoke_only,
    )
    done: list[VariantRecord] = []
    sessions: list[Session] = []
    if args.resume:
        info = folder.resumed(info)
        done, sessions = folder.results(VariantRecord), folder.sessions(Session)
    history = checkout.top / DATA / HISTORY_FILE
    probe = scorecard(info, [], complete=False, stopped=None, sessions=[])
    if not parts.history_accepts(
        talker_line(probe, Session(started_at=info.started_at, stopped=None, variants=0), 1)
    ):
        raise refused(
            "the shared history takes no line of run K's kind yet",
            "name talker_lines.TalkerLine in run_lines.AnyLine, as the integration does",
        )
    began = parts.now()
    before = sum(session.cost_usd for session in sessions)
    paced = pacing(
        args,
        closing.add(parts.chat(chat)),
        today=parts.requests_today(history, began.date()),
        before_usd=before,
        parts=parts,
    )
    keys = {(record.item, record.variant) for record in done}
    remaining = [each for each in todo if each.key not in keys]
    requests = {args.model: TALKER_REQUESTS, args.judge_model: JUDGE_ATTEMPTS}
    check_budget(
        args, paced, units=len(remaining) + 1, requests=requests, whole_day=args.split == "held-out"
    )
    measuring = Measuring(
        agent=agent,
        paced=paced,
        settings=call,
        knowledge=recording,
        data=data,
        judge=Judge(paced, model=args.judge_model, max_output_tokens=args.judge_max_output_tokens),
        search_tool=args.search_tool,
        call_language=args.call_language,
        timeout_s=args.variant_timeout_s,
        call=parts.call,
        clock=parts.clock,
    )
    if not args.resume:
        folder.begin(info)
    found = _Found()
    log.info(
        "run_started", run=info.name, split=info.split, variants=len(remaining), done=len(done)
    )
    try:
        asyncio.run(_measure(measuring, smoke, remaining, found, folder, args, closing))
    except KeyboardInterrupt:
        found.stopped = "interrupted"
        log.warning("run_interrupted", done=len(found.results), of=len(remaining))
    except BaseException as error:
        found.stopped = "error"
        log.error("run_failed", error=type(error).__name__, done=len(found.results))
        raise
    finally:
        expected = 1 if args.smoke_only else len(todo)
        _close(
            info,
            folder,
            done + found.results,
            found.stopped,
            expected,
            sessions,
            paced.spend,
            began,
            parts,
            history,
        )
    return 0 if found.stopped is None else 1


async def _measure(
    measuring: Measuring,
    smoke: Todo,
    todo: Sequence[Todo],
    found: _Found,
    folder: RunFolder,
    args: argparse.Namespace,
    closing: Closing,
) -> None:
    held_out = args.split == "held-out"
    spend = measuring.paced.spend
    try:
        record = await measuring.variant(smoke, "dev")
        if record.failure is not None or spend.retries_and_failures():
            found.stopped = "smoke_failed"
            log.error("smoke_failed", failure=record.failure, requests=spend.requests())
            return
        log.info("smoke_passed", requests=spend.requests())
        if args.smoke_only:
            found.results.append(record)
            folder.add_result(record)
            return
        for number, each in enumerate(todo, start=1):
            record = await measuring.variant(each, args.split)
            found.results.append(record)
            if held_out:
                log.info("variant_done", done=number, of=len(todo))
                continue
            folder.add_result(record)
            log.info(
                "variant_done",
                done=number,
                of=len(todo),
                item=record.item,
                variant=record.variant,
                failure=record.failure,
                verdict=record.judged.verdict if record.judged else None,
                searches=len(record.searches),
                own_hit=record.own_hit,
                language_right=record.language_right,
                first_clause_s=record.turn.first_clause_s if record.turn else None,
                seconds=round(record.seconds, 2),
            )
    except StopRun as stop:
        found.stopped = stop.reason
        log.warning("run_stopped", reason=stop.reason, done=len(found.results), of=len(todo))
    finally:
        await closing.aclose()  # the chat model and the knowledge base, in the run's own loop


def _close(
    info: TalkerRun,
    folder: RunFolder,
    records: list[VariantRecord],
    stopped: Stopped | None,
    expected: int,
    sessions: list[Session],
    spend: Spend,
    began: datetime,
    parts: TalkerParts,
    history: Path,
) -> None:
    """The session, the scorecard and the session's history line, whatever stopped the run."""
    complete = stopped is None and len(records) == expected
    if info.split == "held-out" and not complete:
        records = []  # a held-out run that did not finish keeps no result: it is run again whole
    session = Session(
        started_at=began,
        stopped=stopped,
        variants=len(records),
        spend=spend.spent(),
        cost_usd=spend.session_usd(),
    )
    folder.add_session(session)
    every = [*sessions, session]
    card = scorecard(info, records, complete=complete, stopped=stopped, sessions=every)
    folder.write_scorecard(card)
    line = talker_line(card, session, len(every))
    parts.append_line(line, history)
    parts.append_line(line, folder.out / HISTORY_FILE)
    if stopped in ("daily_limit", "cap", "interrupted") and info.split == "dev":
        log.warning("run_resumable", fix="run the same command with --resume to go on")
    log.info("run_finished", complete=complete, variants=len(records), cost_usd=card.cost_usd)


def main(argv: Sequence[str] | None = None, *, parts: TalkerParts | None = None) -> int:
    """`uv run poe eval-talker`: run one arm of K over one split of the knowledge set. 0 when
    the run is complete, 1 when it is not (a failed smoke test, the cap, the day's limit, an
    interrupt), 2 when it is refused before anything is sent."""
    parser = _parser()
    args = parser.parse_args(argv)
    _require(parser, args)
    configure_logging(loggers=LOGGERS)
    try:
        return _run(args, TalkerParts() if parts is None else parts)
    except T2VoiceError as error:
        log.error("talker_refused", code=error.code, message=error.message)
        return 2


if __name__ == "__main__":
    sys.exit(main())

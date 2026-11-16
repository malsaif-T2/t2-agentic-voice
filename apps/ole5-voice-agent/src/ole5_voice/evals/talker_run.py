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
only, the library's lines but its errors held back, and one that does not finish keeps no
result. A dev run stopped by the key's daily limit, the cap or an interrupt goes on with
`--resume` and the same command line, its finished variants kept. Each session, run as runs
S's and A's are (session_runner.py), writes the scorecard (`talker_score.py`) and appends its
history line (`talker_lines.TalkerLine`) to the worktree's `history.jsonl`, copied beside the
scorecard.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final, get_args

from pydantic import BaseModel
from t2_agentic_voice import VoiceAgent, get_logger
from t2_agentic_voice.evals import run_checkout, run_refused

from ole5_voice.evals.factories import Closing, knowledge_of
from ole5_voice.evals.factories import agent_of as built_agent
from ole5_voice.evals.items import HISTORY_FILE
from ole5_voice.evals.judge import JUDGE_REQUESTS, Judge
from ole5_voice.evals.kb_points import KnowledgeData, RecordingKnowledge, load_knowledge
from ole5_voice.evals.models import Split
from ole5_voice.evals.run_folder import folder_for
from ole5_voice.evals.run_parts import DATA
from ole5_voice.evals.run_settings import env_file_of
from ole5_voice.evals.session_runner import (
    SessionRun,
    check_history,
    closed,
    earlier,
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
from ole5_voice.evals.talker_data import TAGS
from ole5_voice.evals.talker_lines import talker_line
from ole5_voice.evals.talker_measure import (
    TALKER_REQUESTS,
    CallLanguage,
    Measuring,
    Todo,
    todo_of,
)
from ole5_voice.evals.talker_score import (
    PriceShown,
    Session,
    Stopped,
    TalkerRun,
    TalkerScorecard,
    VariantRecord,
    scorecard,
)

_DESCRIPTION = "Run the talker over one split of the knowledge set, one arm, into --out."
_LINE: Final = "talker_lines.TalkerLine"
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
        raise run_refused(
            f"the agent has no tool {args.search_tool}", "give its knowledge tool's name"
        )
    return agent, recording


def _plan(
    args: argparse.Namespace, data: KnowledgeData, agent: VoiceAgent
) -> tuple[Todo, list[Todo]]:
    """The smoke test's variant and the split's; refused when a call could not be held."""
    items = list(data.items.values())
    dev, todo = todo_of(items, "dev"), todo_of(items, args.split)
    if not dev or not todo:
        raise run_refused("the knowledge set holds no dev variant, or none of the split", "fix it")
    data.check_texts([each.item for each in (dev[0], *todo)])
    spoken = {language.tag for language in agent.languages}
    if args.call_language == "variant" and (
        lacking := sorted({t.asked.language for t in todo if TAGS[t.asked.language] not in spoken})
    ):
        raise run_refused(
            f"the agent speaks no language of the {', '.join(lacking)} variants",
            "hold the calls in the agent's first language (--call-language first)",
        )
    return dev[0], todo


def _run(args: argparse.Namespace, parts: TalkerParts) -> int:
    return closed(lambda closing: _built(args, parts, closing))


def _built(args: argparse.Namespace, parts: TalkerParts, closing: Closing) -> int:
    checkout = run_checkout(parts.folder, parts.git)
    data_dir = checkout.top / DATA
    data = load_knowledge(data_dir, args.points_text)
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
    if args.resume:
        info = folder.resumed(info)
    done, sessions = earlier(folder, VariantRecord, resume=args.resume)
    probe = scorecard(info, [], complete=False, stopped=None, sessions=[])
    check_history(parts, talker_line(probe, first_session(info.started_at), 1), "K", _LINE)
    began, paced = paced_chat(args, parts, closing, chat, data_dir / HISTORY_FILE, sessions)
    keys = {(record.item, record.variant) for record in done}
    remaining = [each for each in todo if each.key not in keys]
    requests = {args.model: TALKER_REQUESTS, args.judge_model: JUDGE_REQUESTS}
    held_out = args.split == "held-out"
    check_budget(args, paced, units=len(remaining) + 1, requests=requests, whole_day=held_out)
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
    log.info(
        "run_started", run=info.name, split=info.split, variants=len(remaining), done=len(done)
    )
    session = _Session(
        folder=folder,
        data=data_dir,
        parts=parts,
        closing=closing,
        paced=paced,
        began=began,
        sessions=sessions,
        done=done,
        todo=remaining,
        expected=1 if args.smoke_only else len(todo),
        held_out=held_out,
        smoke_only=args.smoke_only,
        info=info,
        measuring=measuring,
        smoke=smoke,
    )
    return session.run()


@dataclass(kw_only=True)
class _Session(SessionRun[Todo, VariantRecord, TalkerScorecard]):
    """A session of run K (session_runner.py): each variant measured once (talker_measure.py),
    the smoke test the first dev variant's call."""

    info: TalkerRun
    measuring: Measuring
    smoke: Todo

    async def smoke_record(self) -> VariantRecord:
        return await self.measuring.variant(self.smoke, "dev")

    async def record(self, each: Todo) -> VariantRecord:
        return await self.measuring.variant(each, self.info.split)

    def smoke_check(self, record: VariantRecord) -> tuple[bool, dict[str, object]]:
        return record.failure is not None, {"failure": record.failure}

    def shown(self, each: Todo, record: VariantRecord) -> dict[str, object]:
        turn = record.turn
        return {
            "item": record.item,
            "variant": record.variant,
            "failure": record.failure,
            "verdict": record.judged.verdict if record.judged else None,
            "searches": len(record.searches),
            "own_hit": record.own_hit,
            "language_right": record.language_right,
            "first_clause_s": turn.first_clause_s if turn else None,
            "own_first_clause_s": turn.own_first_clause_s if turn else None,
            "seconds": round(record.seconds, 2),
        }

    def scorecard(
        self,
        records: list[VariantRecord],
        *,
        complete: bool,
        stopped: Stopped | None,
        sessions: list[Session],
    ) -> TalkerScorecard:
        return scorecard(self.info, records, complete=complete, stopped=stopped, sessions=sessions)

    def line(self, card: TalkerScorecard, session: Session, number: int) -> BaseModel:
        return talker_line(card, session, number)

    def finished(self, card: TalkerScorecard, records: list[VariantRecord]) -> dict[str, object]:
        return {"variants": len(records), "cost_usd": card.cost_usd}


def main(argv: Sequence[str] | None = None, *, parts: TalkerParts | None = None) -> int:
    """`uv run poe eval-talker`: run one arm of K over one split of the knowledge set. 0 when
    the run is complete, 1 when it is not (a failed smoke test, the cap, the day's limit, an
    interrupt, a library error once it began), 2 when it is refused before anything is sent."""
    parser = _parser()
    args = parser.parse_args(argv)
    found = TalkerParts() if parts is None else parts
    return main_of(parser, args, _require, lambda given: _run(given, found), "talker_refused")


if __name__ == "__main__":
    sys.exit(main())

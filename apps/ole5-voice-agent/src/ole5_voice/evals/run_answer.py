"""How `poe eval` (run.py) answers a run's variants and closes it: `answer_all`, the smoke
test, then every variant in order, the arm's baseline answers unsent, the run ending early at
the cap; and `close_run`, the scorecard and, for a run that spent, its history line.
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping
from pathlib import Path

from t2_agentic_voice import get_logger

from ole5_voice.evals import history
from ole5_voice.evals.answerers import RunAnswerer
from ole5_voice.evals.groq_answerer import Budget, CapReachedError
from ole5_voice.evals.models import Variant
from ole5_voice.evals.run_parts import DATA, Parts, Plan, Progress
from ole5_voice.evals.runs import Answer, RunInfo
from ole5_voice.evals.worktree import Checkout

log = get_logger(__name__)


async def answer_all(
    plan: Plan,
    answerer: RunAnswerer,
    progress: Progress,
    args: argparse.Namespace,
    copied: Mapping[Variant, Answer],
) -> None:
    """The smoke test, then every variant, in order, the arm's baseline answers unsent; the run
    ends early at the cap."""
    try:
        smoke = await answerer.answer(plan.smoke.variant, plan.smoke.request)
        if smoke.failure or any(r.outcome != "ok" or r.attempt > 1 for r in smoke.requests):
            outcomes = [r.outcome for r in smoke.requests]
            log.error("smoke_failed", failure=smoke.failure, outcomes=outcomes)
            return
        progress.smoke_passed = True
        # The language the provider reported, a code or a name: how R7's smoke step reads the
        # form Groq gives when no language is sent (TD-011). A label, never a transcript.
        log.info("smoke_passed", requests=len(smoke.requests), language=smoke.language)
        if args.smoke_only:
            progress.add(plan.smoke.result(smoke, plan.matcher, args.split, True))
            return
        for todo in plan.todo:
            answer = copied.get(todo.variant)
            if answer is None:
                answer = await answerer.answer(todo.variant, todo.request)
            progress.add(todo.result(answer, plan.matcher, args.split, not args.windows_ms))
    except CapReachedError:
        progress.capped = True
        log.warning("cap_reached", done=len(progress.results), of=progress.total)
    finally:
        await answerer.aclose()


def close_run(
    info: RunInfo,
    progress: Progress,
    budget: Budget,
    spends: bool,
    out: Path,
    checkout: Checkout,
    parts: Parts,
) -> int:
    """The scorecard and, for a run that spent, its history line; 0 when the run is complete."""
    complete = progress.smoke_passed and not (progress.capped or progress.interrupted)
    complete = complete and len(progress.results) == progress.total
    # A held-out run that did not finish keeps no result: it is run again whole.
    kept = progress.results if complete or info.split == "dev" else []
    card = parts.write_scorecard(info, kept, complete=complete, out=out)
    if spends:  # every request sent, the smoke test's and a capped variant's included
        line = history.line_of(
            card,
            items=len({r.item for r in kept}),
            billed_seconds=budget.billed_seconds,
            cost_usd=budget.cost_usd,
        )
        history.record_line(parts.append_line, line, checkout.top / DATA, out)
    failures = sum(r.answer.failure is not None for r in kept)
    log.info("run_finished", complete=complete, variants=len(kept), failures=failures)
    log.info("run_spent", requests=budget.requests, billed_s=budget.billed_seconds, out=str(out))
    return 0 if complete else 1

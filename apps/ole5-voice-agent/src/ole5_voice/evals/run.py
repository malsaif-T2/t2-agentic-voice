"""`poe eval`: run an answerer over one split of the golden set into a new folder, `--out`, as
evaluation.md's "Running" says.

Before anything is sent, a run refuses the main checkout and a dirty tree, an `--out` that
exists or that git would track (`worktree.py`), and audio that is not the file its manifest
hashed. Its settings load with `Settings.from_env` (`--env-file`), the command line's on top
(`run_settings.py`): a `groq` run names its model and timeout, and its base URL is `--base-url`
or the SDK's own, whatever the environment holds, so no `T2V_` variable changes a registered
arm; `--show-settings` shows each resolved, a secret only as set or not set. A smoke test of one
dev variant comes first and must pass with no failed, retried or refused request. Then each
variant is answered, and its result written as it finishes (a dev run's `results.jsonl`), with
a progress line of identifiers, verdicts and timings, never a transcript. The scorecard is
written by `scorecard.py` and, for a run that calls a provider, its history line is appended
to the worktree's `history.jsonl` and copied beside the scorecard. A held-out run writes no
per-variant output, its lines hold counts only, it is never traced, and one that does not finish
keeps no result. A run's name is its `--out` folder's name.
"""

from __future__ import annotations

import argparse
import asyncio
import math
import sys
from collections.abc import Sequence
from pathlib import Path

from t2_agentic_voice import (
    ConfigurationError,
    Settings,
    T2VoiceError,
    configure_logging,
    get_logger,
)

from ole5_voice.evals import history
from ole5_voice.evals.answerers import (
    ANSWERERS,
    Budget,
    CapReachedError,
    Policy,
    RunAnswerer,
    make_answerer,
)
from ole5_voice.evals.items import HISTORY_FILE
from ole5_voice.evals.run_parts import (
    DATA,
    Choice,
    Parts,
    Plan,
    Progress,
    audio_roots,
    clip_answers,
    is_name,
    load_plan,
)
from ole5_voice.evals.run_settings import GROQ_BASE_URL, MODELS, load_settings, show, shown
from ole5_voice.evals.runs import RunInfo, holds_placeholder
from ole5_voice.evals.windows import measurer
from ole5_voice.evals.worktree import Checkout, check_out, inspect, refused

RESULTS_FILE = "results.jsonl"  # a dev run's results, one line each as it finishes
_DESCRIPTION = "Run an answerer over the golden set, writing its results and scorecard into --out."
_HINT_HELP = "the language sent: the item's label's (ar, or en for English), or none (auto)"
_AUDIO_HELP = "the folder of an audio root the manifests name, once per root"
_OUT_HELP = "a new folder, outside the worktree, that git ignores; its name is the run's"
_WINDOWS_HELP = "send only these leading windows of each talk-over clip, unjudged"
_CLIPS_HELP = "a windows run's source of clip answers: the model's first dev scorecard"

log = get_logger(__name__)


def _count(text: str) -> int:
    if (value := int(text)) < 1:
        raise argparse.ArgumentTypeError("must be 1 or more")
    return value


def _amount(text: str) -> float:
    if not math.isfinite(value := float(text)) or value < 0:
        raise argparse.ArgumentTypeError("must be a finite number, 0 or more")
    return value


def _seconds(text: str) -> float:
    if not math.isfinite(value := float(text)) or value <= 0:
        raise argparse.ArgumentTypeError("must be a finite number of seconds above 0")
    return value


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="poe eval", description=_DESCRIPTION)
    add = parser.add_argument
    add("--answerer", choices=ANSWERERS, help="reference (sends nothing) or groq (Whisper)")
    add("--split", choices=("dev", "held-out"), help="the split the run covers, all of it")
    add("--model", choices=MODELS, help="stt.model for this run (groq needs it)")
    add("--timeout-s", type=_seconds, help="stt.timeout_s for this run (groq needs it)")
    add("--base-url", help=f"groq.base_url for this run ({GROQ_BASE_URL})")
    add("--language-hint", choices=("label", "auto"), default="label", help=_HINT_HELP)
    add("--env-file", type=Path, help="the .env file the settings load from (never printed)")
    add("--var-dir", type=Path, help="the settings' var_dir")
    add("--audio", action="append", default=[], metavar="ROOT=FOLDER", help=_AUDIO_HELP)
    add("--out", type=Path, help=_OUT_HELP)
    add("--max-rpm", type=_count, default=20, help="requests a minute, at most (20)")
    add("--max-attempts", type=_count, default=4, help="attempts of each request (4)")
    add("--variant-timeout-s", type=_amount, default=120.0, help="each variant's limit (120)")
    add("--price-per-hour", type=_amount, help="USD an hour of billed audio (groq needs it)")
    add("--cap-usd", type=_amount, help="the most the run may spend (groq needs it)")
    add("--windows-ms", type=_count, nargs="+", default=[], help=_WINDOWS_HELP)
    add("--clips-from", type=Path, help=_CLIPS_HELP)
    add("--questions", type=Path, help="a dev screen file, one item/variant a line: only these")
    add("--tracing-endpoint", help="trace the run to this OTLP endpoint (dev only)")
    add("--note", help="why the run is made")
    add("--show-settings", action="store_true", help="show each setting and path, send nothing")
    add("--smoke-only", action="store_true", help="run the smoke test alone")
    return parser


def _require(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    """The flags a run needs together; `--show-settings` needs none."""
    if args.show_settings:
        return
    named = ("answerer", "split", "out", "note")
    missing = [f"--{name}" for name in named if not getattr(args, name)]
    if args.answerer == "groq":
        pinned = {"--model": args.model, "--timeout-s": args.timeout_s}
        pinned |= {"--price-per-hour": args.price_per_hour, "--cap-usd": args.cap_usd}
        missing += [flag for flag, value in pinned.items() if value is None]
    if missing:
        parser.error(f"a run needs {', '.join(missing)}")
    if holds_placeholder(args.note):
        parser.error("--note holds an install placeholder, which the docs check refuses")
    if args.split == "held-out" and (args.questions or args.smoke_only or args.tracing_endpoint):
        parser.error(
            "a held-out run covers its whole split, untraced: no --questions, "
            "--smoke-only or --tracing-endpoint"
        )
    if args.variant_timeout_s <= 0:
        parser.error("--variant-timeout-s is more than 0")
    if args.smoke_only and args.windows_ms:
        parser.error("--smoke-only sends the smoke test's clip, and no windows")
    if args.clips_from and not args.windows_ms:
        parser.error("--clips-from serves a windows run (--windows-ms)")


async def _answer_all(
    plan: Plan, answerer: RunAnswerer, progress: Progress, args: argparse.Namespace
) -> None:
    """The smoke test, then every variant, in order; the run ends early at the cap."""
    try:
        smoke = await answerer.answer(plan.smoke.variant, plan.smoke.request)
        if smoke.failure or any(r.outcome != "ok" or r.attempt > 1 for r in smoke.requests):
            outcomes = [r.outcome for r in smoke.requests]
            log.error("smoke_failed", failure=smoke.failure, outcomes=outcomes)
            return
        progress.smoke_passed = True
        log.info("smoke_passed", requests=len(smoke.requests))
        if args.smoke_only:
            progress.add(plan.smoke.result(smoke, plan.matcher, args.split, True))
            return
        for todo in plan.todo:
            answer = await answerer.answer(todo.variant, todo.request)
            progress.add(todo.result(answer, plan.matcher, args.split, not args.windows_ms))
    except CapReachedError:
        progress.capped = True
        log.warning("cap_reached", done=len(progress.results), of=progress.total)
    finally:
        await answerer.aclose()


def _run(args: argparse.Namespace, settings: Settings, parts: Parts) -> int:
    # The settings go into the committed history, as the note does (its check: `_parser`).
    if placed := [
        name for name, value in shown(settings, args).items() if holds_placeholder(value)
    ]:
        raise ConfigurationError(
            f"{placed[0]} holds an install placeholder, which the docs check refuses in the "
            "history. FIX: give the setting without one.",
            details={"setting": placed[0]},
        )
    checkout = inspect(parts.folder, parts.git)
    if (problem := checkout.refusal()) is not None:
        raise problem
    out = check_out(args.out, checkout, parts.git)
    if not is_name(out.name):
        raise refused(
            "the --out folder's name, the run's, is not lowercase letters, digits, '.', '_' or '-'",
            "name the folder like r1-large-v3",
        )
    spends = args.answerer == "groq"
    choice = Choice(
        split=args.split,
        windows_ms=tuple(args.windows_ms),
        questions=args.questions,
        hint=args.language_hint,
        roots=audio_roots(args.audio),
        needs_audio=spends,
    )
    plan = load_plan(checkout.top / DATA, choice, parts)
    model = settings.stt.model
    reuse = clip_answers(args.clips_from, plan.todo, commit=checkout.commit, model=model)
    budget = Budget(price_per_hour_usd=args.price_per_hour or 0.0, cap_usd=args.cap_usd)
    policy = Policy(args.max_attempts, args.max_rpm, args.variant_timeout_s)
    tracer = parts.tracing(settings) if args.tracing_endpoint else None
    try:
        answerer = make_answerer(
            args.answerer,
            settings,
            stt=parts.speech_to_text(settings) if spends else None,
            policy=policy,
            budget=budget,
            measure=measurer(parts.normalize, plan.matcher.is_right),
            reuse=reuse,
            tracing=tracer,
            run_name=out.name,
            clock=parts.clock,
            sleep=parts.sleep,
        )
        info = RunInfo(
            name=out.name,
            started_at=parts.now(),
            commit=checkout.commit,
            answerer=answerer.name,
            model=settings.stt.model if answerer.spends else None,
            split=args.split,
            settings=shown(settings, args),
            price_per_hour_usd=budget.price_per_hour_usd,
            data_digest=plan.digest,
            note=args.note,
            windows_ms=tuple(args.windows_ms),
            traced=tracer is not None,
        )
        out.mkdir(parents=True)
        held_out = args.split == "held-out"
        progress = Progress(
            total=1 if args.smoke_only else len(plan.todo),
            results_file=None if held_out else out / RESULTS_FILE,
            clock=parts.clock,
            began=parts.clock(),
        )
        log.info("run_started", run=info.name, split=info.split, variants=progress.total)
        try:
            asyncio.run(_answer_all(plan, answerer, progress, args))
        except KeyboardInterrupt:
            progress.interrupted = True
            log.warning("run_interrupted", done=len(progress.results), of=progress.total)
        return _close(info, progress, budget, answerer.spends, out, checkout, parts)
    finally:
        if tracer is not None:
            tracer.shutdown()
            log.info("tracing_closed", dropped_spans=tracer.dropped_spans)


def _close(
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
        parts.append_line(line, checkout.top / DATA / HISTORY_FILE)
        parts.append_line(line, out / HISTORY_FILE)
    failures = sum(r.answer.failure is not None for r in kept)
    log.info("run_finished", complete=complete, variants=len(kept), failures=failures)
    log.info("run_spent", requests=budget.requests, billed_s=budget.billed_seconds, out=str(out))
    return 0 if complete else 1


def main(argv: Sequence[str] | None = None, *, parts: Parts | None = None) -> int:
    """`uv run poe eval`: run an answerer over one split of the golden set into a new folder.
    0 when the run is complete, 1 when it is not (a failed smoke test, the cap, an interrupt),
    2 when it is refused before anything is sent."""
    parser = _parser()
    args = parser.parse_args(argv)
    _require(parser, args)
    parts = Parts() if parts is None else parts
    configure_logging()  # the library's defaults, until the settings name the level and format
    try:
        settings = load_settings(args)
        configure_logging(settings.log_level, settings.log_format)
        if args.show_settings:
            show(args, settings, parts)
            return 0
        return _run(args, settings, parts)
    except T2VoiceError as error:
        log.error("eval_refused", code=error.code, message=error.message)
        return 2


if __name__ == "__main__":
    sys.exit(main())

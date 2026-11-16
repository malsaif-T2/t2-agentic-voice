"""`poe eval`: run an answerer over one split of the golden set into a new folder, `--out`, as
evaluation.md's "Running" says.

Before anything is sent, a run refuses the main checkout and a dirty tree, an `--out` that exists
or that git would track (`worktree.py`), audio that is not the file its manifest hashed, and a
provider's run whose least cost (each request once, billed as it bills; a windows run's aside)
would pass `--cap-usd`, its dry estimate logged first (`stt_arms.py`; `--estimate-only` stops
there). Each speech-to-text provider is an answerer of its name: `groq`, or one beside it (D-100).
Its settings load with `VoiceSettings.from_env` (`--env-file`, or the working folder's `.env`),
the command line's on top (`run_settings.py`), `stt.provider` the answerer's: a `groq` run names
its model and timeout, its base URL `--base-url` or the SDK's own, whatever the environment
holds, so no `T2V_` variable changes a registered arm; `--show-settings` shows each resolved, a
secret only as set or not set. Run W's arms are its options too (`run_arms.answer_options`): the
Whisper prompt the agent `--prompt-agent` names would ship, and every variant sent as Arabic with
`--language-hint ar` or as English with `en`; run H's H2 arm is `--language-from`, with
`--language-base` (`language_arms.py`). A smoke test of one dev variant comes first and must
pass with no failed, retried or refused request. Then each variant is answered, its result
written as it finishes (a dev run's `results.jsonl`), with a progress line of identifiers,
verdicts and timings, never a transcript. The scorecard is `scorecard.py`'s; a run that calls a
provider appends its history line to the worktree's `history.jsonl`, a copy beside the card.
A held-out run writes no per-variant output, its lines hold counts only, it is never traced, and
one that does not finish keeps no result. A run's name is its `--out` folder's name.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import get_args

from t2_agentic_voice import (
    ConfigurationError,
    T2VoiceError,
    VoiceSettings,
    configure_logging,
    get_logger,
)

from ole5_voice import LOGGERS
from ole5_voice.evals import history
from ole5_voice.evals.answerers import ANSWERERS, RunAnswerer, make_answerer
from ole5_voice.evals.cli import amount, count, require, seconds
from ole5_voice.evals.groq_answerer import Budget, CapReachedError, Policy
from ole5_voice.evals.language_arms import flag_problem, language_arm
from ole5_voice.evals.models import NAME_RULE, Split, Variant, is_name
from ole5_voice.evals.run_arms import AnswerOptions, answer_options
from ole5_voice.evals.run_parts import (
    DATA,
    Choice,
    Parts,
    Plan,
    Progress,
    audio_roots,
    clip_answers,
    load_plan,
)
from ole5_voice.evals.run_settings import GROQ_BASE_URL, MODELS, load_settings, show, shown
from ole5_voice.evals.runs import Answer, RunInfo, holds_placeholder
from ole5_voice.evals.stt_arms import ARMS, arm_problem, arm_settings, check_cost, recorded_model
from ole5_voice.evals.windows import measurer
from ole5_voice.evals.worktree import Checkout, check_out, refused, run_checkout

RESULTS_FILE = "results.jsonl"  # a dev run's results, one line each as it finishes
_DESCRIPTION = "Run an answerer over the golden set, writing its results and scorecard into --out."
_HINT_HELP = (
    "the language sent: the item's label's (ar, or en for English), none (auto), or ar or en "
    "for every variant, as an Arabic or an English call sends it (arms X and C); with "
    "--language-from, the call's language"
)
_FROM_HELP = "an H1 pass of poe eval-languages: each variant in the language its rule named"
_BASE_HELP = "with --language-from on dev: the call language's baseline; only changes are sent"
_PROMPT_HELP = (
    "the agent's factory, ole5_voice.<module>:<name> (ole5_voice.agent:talker_agent): send the "
    "Whisper prompt of its declared vocabulary (arm W1)"
)
_AUDIO_HELP = "the folder of an audio root the manifests name, once per root"
_OUT_HELP = "a new folder, outside the worktree, that git ignores; its name is the run's"
_WINDOWS_HELP = "send only these leading windows of each talk-over clip, unjudged"
_CLIPS_HELP = "a windows run's source of clip answers: the model's first dev scorecard"

log = get_logger(__name__)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="poe eval", description=_DESCRIPTION)
    add = parser.add_argument
    policy = Policy()  # the run policy's defaults, which the flags below take
    add("--answerer", choices=ANSWERERS, help="reference (sends nothing), or a provider")
    add("--split", choices=get_args(Split), help="the split the run covers, all of it")
    add("--model", choices=MODELS, help="stt.model for this run (groq needs it)")
    add("--timeout-s", type=seconds, help="stt.timeout_s for this run (a provider needs it)")
    add("--base-url", help=f"groq.base_url for this run ({GROQ_BASE_URL})")
    add("--language-hint", choices=("label", "auto", "ar", "en"), default="label", help=_HINT_HELP)
    add("--prompt-agent", help=_PROMPT_HELP)
    add("--language-from", type=Path, help=_FROM_HELP)
    add("--language-base", type=Path, help=_BASE_HELP)
    add("--env-file", type=Path, help="the .env file the settings load from (never printed)")
    add("--var-dir", type=Path, help="the settings' var_dir")
    add("--audio", action="append", default=[], metavar="ROOT=FOLDER", help=_AUDIO_HELP)
    add("--out", type=Path, help=_OUT_HELP)
    rpm, attempts, limit = policy.max_rpm, policy.max_attempts, policy.variant_timeout_s
    add("--max-rpm", type=count, default=rpm, help=f"requests a minute, at most ({rpm})")
    add(
        "--max-attempts",
        type=count,
        default=attempts,
        help=f"attempts of each request ({attempts})",
    )
    add(
        "--variant-timeout-s",
        type=seconds,
        default=limit,
        help=f"each variant's limit ({limit:g})",
    )
    add("--price-per-hour", type=amount, help="USD an hour of billed audio (a provider needs it)")
    add("--cap-usd", type=amount, help="the most the run may spend (a provider needs it)")
    add("--windows-ms", type=count, nargs="+", default=[], help=_WINDOWS_HELP)
    add("--clips-from", type=Path, help=_CLIPS_HELP)
    add("--questions", type=Path, help="a dev screen file, one item/variant a line: only these")
    add("--tracing-endpoint", help="trace the run to this OTLP endpoint (dev only)")
    add("--note", help="why the run is made")
    add("--show-settings", action="store_true", help="show each setting and path, send nothing")
    add("--smoke-only", action="store_true", help="run the smoke test alone")
    add("--estimate-only", action="store_true", help="log the dry estimate alone, send nothing")
    return parser


def _require(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    """The flags a run needs together; `--show-settings` needs none."""
    if args.show_settings:
        return
    named = ["answerer", "split", "out", "note"]
    if args.answerer in ARMS:
        named += ["model"] * (args.answerer == "groq") + ["timeout_s", "price_per_hour", "cap_usd"]
    require(parser, args, named)
    if args.split == "held-out" and (args.questions or args.smoke_only or args.tracing_endpoint):
        parser.error(
            "a held-out run covers its whole split, untraced: no --questions, "
            "--smoke-only or --tracing-endpoint"
        )
    if args.smoke_only and args.windows_ms:
        parser.error("--smoke-only sends the smoke test's clip, and no windows")
    if args.clips_from and not args.windows_ms:
        parser.error("--clips-from serves a windows run (--windows-ms)")
    if args.prompt_agent and args.language_hint == "auto":
        parser.error("--prompt-agent builds a prompt for the language sent: not with auto")
    if (problem := flag_problem(args) or arm_problem(args)) is not None:
        parser.error(problem)


async def _answer_all(
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


def _run(
    args: argparse.Namespace, settings: VoiceSettings, parts: Parts, options: AnswerOptions
) -> int:
    # The settings go into the committed history, as the note does (its check: `_parser`).
    recorded = shown(settings, args, prompt=options.shown)
    if placed := [name for name, value in recorded.items() if holds_placeholder(value)]:
        raise ConfigurationError(
            f"{placed[0]} holds an install placeholder, which the docs check refuses in the "
            "history. FIX: give the setting without one.",
            details={"setting": placed[0]},
        )
    checkout = run_checkout(parts.folder, parts.git)
    out = check_out(args.out, checkout, parts.git)
    if not is_name(out.name):
        raise refused(
            f"the --out folder's name, the run's, is not a name, which is {NAME_RULE}",
            "name the folder like r1-large-v3",
        )
    spends = args.answerer in ARMS
    choice = Choice(
        split=args.split,
        windows_ms=tuple(args.windows_ms),
        questions=args.questions,
        hint="label" if args.language_hint in ("ar", "en") else args.language_hint,  # the policy's
        roots=audio_roots(args.audio),
        needs_audio=spends,
    )
    plan = load_plan(checkout.top / DATA, choice, parts)
    model = recorded_model(settings, args.answerer)
    arm = language_arm(args, plan, commit=checkout.commit, model=model, prompt=options.shown)
    plan, recorded = arm.plan, recorded | dict(arm.recorded)
    reuse = clip_answers(args.clips_from, plan.todo, commit=checkout.commit, model=model)
    budget = Budget(price_per_hour_usd=args.price_per_hour or 0.0, cap_usd=args.cap_usd)
    if spends and not args.windows_ms:  # the cap, before anything is sent
        todo = [] if args.smoke_only else [t for t in plan.todo if t.variant not in arm.copied]
        sent = [plan.smoke.request, *(t.request for t in todo)]
        if check_cost(settings, sent, args) == "estimated":
            return 0
    policy = Policy(
        args.max_attempts,
        args.max_rpm,
        args.variant_timeout_s,
        language=options.language,
        prompts=options.prompts,
    )
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
            model=model if answerer.spends else None,
            split=args.split,
            settings=recorded,
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
            asyncio.run(_answer_all(plan, answerer, progress, args, arm.copied))
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
        history.record_line(parts.append_line, line, checkout.top / DATA, out)
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
    # The library's defaults, until the settings name the level and format.
    configure_logging(loggers=LOGGERS)
    try:
        settings = arm_settings(load_settings(args), args.answerer or "")
        logs = settings.logging
        configure_logging(logs.level, logs.format, loggers=LOGGERS, content=logs.content)
        options = answer_options(args)
        if args.show_settings:
            show(args, settings, parts, prompt=options.shown)
            return 0
        return _run(args, settings, parts, options)
    except T2VoiceError as error:
        log.error("eval_refused", code=error.code, message=error.message)
        return 2


if __name__ == "__main__":
    sys.exit(main())

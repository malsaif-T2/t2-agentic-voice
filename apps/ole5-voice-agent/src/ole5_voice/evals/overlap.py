"""`poe overlap`: the golden set's overlap clips replayed over a reply (plan 005's registration,
the arm O), into a new folder, `--out`, as evaluation.md's "Running" says.

Each clip of the split's overlap set, with the reply it is played over and its call's language
(overlap_plan.py), is answered by `reference`, each verdict its kind's and each stop 0 ms, which
reads no audio and sends nothing (the harness checking itself inside `poe check`), or by
`pipeline`, the replay through the `evals` facade's `AudioCall` with the real speech-to-text,
paced at `--stt-rpm` Whisper requests a minute and held under `--cap-usd` (overlap_run.py); then
judged and scored against the registration's targets (overlap_score.py, overlap_card.py).

As `poe eot`, a run refuses the main checkout and a dirty tree, an `--out` that exists or that
git would track, and audio that is not the file its manifest hashed, all before any clip is fed.
Its settings load as `poe eval`'s (the environment and `--env-file`, with `--model`,
`--timeout-s` and `--base-url` on top), then each `--set` of its command line, with
`interruptions.mode` `two_step`; a run of the replay refuses an `stt.live_language` other than
`session`, since the item's label is the call's language. A dev run writes each result as it
finishes (`results.jsonl`) and a progress line of identifiers and verdicts, never a transcript;
a held-out run writes the aggregates only, and its lines are counts. The scorecard is written
whole at the end, every part's transcript, `no_speech_prob`, length and times kept in a dev
run's, so a revised rule is scored again offline; a run of the replay appends its history line
(`run_lines.OverlapLine`), and a `reference` run appends none.
"""

from __future__ import annotations

import argparse
import asyncio
import math
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final, get_args

from t2_agentic_voice import (
    ConfigurationError,
    T2VoiceError,
    VoiceSettings,
    configure_logging,
    evals,
    get_logger,
)
from t2_agentic_voice.groq import GroqSTT
from t2_agentic_voice.ports import SpeechToText

from ole5_voice import LOGGERS
from ole5_voice.evals import history, run_settings
from ole5_voice.evals.import_calls import load_replies
from ole5_voice.evals.items import SCRIPT_FILE, GoldenSetError, read_toml
from ole5_voice.evals.models import NAME_RULE, Split, is_name
from ole5_voice.evals.overlap_card import AppendLine, OverlapRun, close_run
from ole5_voice.evals.overlap_plan import overlaps_of, read_lab_replies, setting, with_set
from ole5_voice.evals.overlap_run import (
    AT_S,
    MAX_ATTEMPTS,
    REPLY_MARGIN_S,
    RESULTS_FILE,
    TAIL_S,
    CapReachedError,
    Measuring,
    Overlap,
    Progress,
    Replayer,
    ReplySpeech,
    reference,
)
from ole5_voice.evals.pacers import MinutePacer
from ole5_voice.evals.run_parts import DATA, Choice, Parts, audio_roots, load_plan
from ole5_voice.evals.runs import holds_placeholder
from ole5_voice.evals.takes import Script
from ole5_voice.evals.worktree import check_out, refused, run_checkout

ANSWERERS: Final = ("reference", "pipeline")
STT_RPM: Final = 10  # Whisper requests a minute, at most: half the published 20 (plan 003's T)
_DESCRIPTION = "Replay the golden set's overlap clips over a reply, into a new folder --out."
log = get_logger(__name__)


@dataclass(frozen=True)
class OverlapParts:
    """What an overlap run is built from, each replaceable by a test's fake: the run's `Parts`
    (its checkout, the golden set's loaders, the clocks), the speech-to-text adapter, the replay
    and the history."""

    plan: Parts = field(default_factory=Parts)
    speech_to_text: Callable[[VoiceSettings], SpeechToText] = GroqSTT.from_settings
    audio_call: Callable[..., Replayer] = evals.AudioCall
    append_line: AppendLine = history.append_line


def _amount(text: str) -> float:
    if not math.isfinite(value := float(text)) or value < 0:
        raise argparse.ArgumentTypeError("must be a finite number, 0 or more")
    return value


def _count(text: str) -> int:
    if (value := int(text)) < 1:
        raise argparse.ArgumentTypeError("must be 1 or more")
    return value


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="poe overlap", description=_DESCRIPTION)
    add = parser.add_argument
    add("--answerer", choices=ANSWERERS, help="reference (each verdict its kind's) or pipeline")
    add("--split", choices=get_args(Split), help="the split the run covers, all of it")
    add("--set", type=setting, action="append", default=[], metavar="GROUP.NAME=VALUE")
    add("--model", choices=run_settings.MODELS, help="stt.model for this run")
    add("--timeout-s", type=_amount, help="stt.timeout_s for this run")
    add("--base-url", help=f"groq.base_url for this run ({run_settings.GROQ_BASE_URL})")
    add("--env-file", type=Path, help="the .env file the settings load from (never printed)")
    add("--var-dir", type=Path, help="the settings' var_dir")
    add("--audio", action="append", default=[], metavar="ROOT=FOLDER", help="an audio root")
    add("--replies", type=Path, help="the folder of the lab's replies.json")
    add("--price-per-hour", type=_amount, help="USD an hour of Whisper's billed audio")
    add("--cap-usd", type=_amount, help="the most the run may spend")
    add("--stt-rpm", type=_count, default=STT_RPM, help=f"Whisper requests a minute ({STT_RPM})")
    add("--out", type=Path, help="a new folder, outside the worktree, that git ignores")
    add("--note", help="why the run is made")
    parser.set_defaults(tracing_endpoint=None)  # an overlap run is untraced
    return parser


def _require(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    named = ["answerer", "split", "out", "note"]
    if args.answerer == "pipeline":
        named += ["model", "timeout_s", "price_per_hour", "cap_usd"]
    missing = [f"--{name.replace('_', '-')}" for name in named if getattr(args, name) is None]
    if missing:
        parser.error(f"a run needs {', '.join(missing)}")
    if holds_placeholder(args.note):
        parser.error("--note holds an install placeholder, which the docs check refuses")


def shown(settings: VoiceSettings, args: argparse.Namespace) -> dict[str, str]:
    """Every setting, as `poe eval` records them, with the overlap run's own."""
    namespace = argparse.Namespace(
        **vars(args),
        language_hint="label",
        max_rpm=args.stt_rpm,
        max_attempts=MAX_ATTEMPTS,
        variant_timeout_s=0,
        windows_ms=[],
        smoke_only=False,
    )
    library = {
        k: v for k, v in run_settings.shown(settings, namespace).items() if not k.startswith("run.")
    }
    run = {
        "run.at_s": str(AT_S),
        "run.tail_s": str(TAIL_S),
        "run.reply_margin_s": str(REPLY_MARGIN_S),
        "run.stt_rpm": str(args.stt_rpm),
        "run.max_attempts": str(MAX_ATTEMPTS),
        "run.cap_usd": "none" if args.cap_usd is None else str(args.cap_usd),
        "run.replies": "given" if args.replies is not None else "none",
    }
    return library | run


async def _replayed(
    measuring: Measuring, todo: Sequence[Overlap], progress: Progress, side: Split
) -> None:
    """Each clip through the replay, in order, until the last or the cap."""
    try:
        await measuring.replayer.start()
        for each in todo:
            progress.add(await measuring.variant(each, side))
    except CapReachedError:
        progress.stopped = "cap"
        log.warning("cap_reached", done=len(progress.results), of=len(todo))
    finally:
        await measuring.aclose()


def _run(args: argparse.Namespace, parts: OverlapParts) -> int:
    pipeline = args.answerer == "pipeline"
    settings = with_set(run_settings.load_settings(args), args.set)
    if pipeline and settings.stt.live_language != "session":
        raise ConfigurationError(
            "An overlap run holds each call in its item's language. FIX: set "
            "stt.live_language session.",
            details={"setting": "stt.live_language"},
        )
    checkout = run_checkout(parts.plan.folder, parts.plan.git)
    out = check_out(args.out, checkout, parts.plan.git)
    if not is_name(out.name):
        raise refused(
            f"the --out folder's name, the run's, is not a name, which is {NAME_RULE}",
            "name the folder like o1-dev",
        )
    data = checkout.top / DATA
    choice = Choice(split=args.split, roots=audio_roots(args.audio), needs_audio=pipeline)
    plan = load_plan(data, choice, parts.plan)
    try:
        lines = {line.id: line for line in read_toml(data / SCRIPT_FILE, Script).lines}
        called = load_replies(data)
    except GoldenSetError:
        raise refused(
            "the golden set's script or replies do not load", "run `poe golden`"
        ) from None
    lab = (read_lab_replies(args.replies) if args.replies else {}) if pipeline else None
    todo = overlaps_of(plan.todo, lines, lab, called)
    if not todo:
        raise refused("the split holds no overlap clip the owner has checked", "check --split")
    info = OverlapRun(
        name=out.name,
        started_at=parts.plan.now(),
        commit=checkout.commit,
        answerer=args.answerer,
        split=args.split,
        settings=shown(settings, args),
        data_digest=plan.digest,
        at_s=AT_S,
        tail_s=TAIL_S,
        stt_rpm=args.stt_rpm,
        price_per_hour_usd=args.price_per_hour,
        cap_usd=args.cap_usd,
        note=args.note,
    )
    out.mkdir(parents=True)
    held_out = args.split == "held-out"
    progress = Progress(len(todo), None if held_out else out / RESULTS_FILE)
    log.info("run_started", run=info.name, split=info.split, variants=len(todo))
    if not pipeline:
        for each in todo:
            progress.add(each.result(args.split, reference(each)))
        return close_run(info, progress, len(todo), (0, 0.0), out, data, parts.append_line)
    stt, speech = parts.speech_to_text(settings), ReplySpeech()
    measuring = Measuring(
        replayer=parts.audio_call(settings=settings, stt=stt, tts=speech),
        stt=stt,
        speech=speech,
        pacer=MinutePacer(args.stt_rpm, parts.plan.clock, parts.plan.sleep),
        price_per_hour_usd=args.price_per_hour,
        cap_usd=args.cap_usd,
        sleep=parts.plan.sleep,
    )
    try:
        asyncio.run(_replayed(measuring, todo, progress, args.split))
    except KeyboardInterrupt:
        progress.stopped = "interrupted"
        log.warning("run_interrupted", done=len(progress.results), of=len(todo))
    spent = (measuring.requests, measuring.billed_seconds)
    return close_run(info, progress, len(todo), spent, out, data, parts.append_line)


def main(argv: Sequence[str] | None = None, *, parts: OverlapParts | None = None) -> int:
    """`uv run poe overlap`: the overlap clips of one split, replayed over a reply. 0 when the
    run is complete, 1 when it is not (the cap, an interrupt), 2 when it is refused before any
    clip is fed."""
    parser = _parser()
    args = parser.parse_args(argv)
    _require(parser, args)
    configure_logging(loggers=LOGGERS)
    try:
        return _run(args, OverlapParts() if parts is None else parts)
    except T2VoiceError as error:
        log.error("overlap_refused", code=error.code, message=error.message)
        return 2


if __name__ == "__main__":
    sys.exit(main())

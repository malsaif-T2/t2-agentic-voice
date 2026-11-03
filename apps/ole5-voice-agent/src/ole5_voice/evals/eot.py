"""`poe eot`: where the turns end on the golden set, offline and with no spend (plan 003's
registration, E), into a new folder, `--out`, as evaluation.md's "Running" says.

The paused requests of the split are judged against the owner's mark (`eot_score.py`); with
`--secondary`, a dev run of the pipeline also judges every other dev variant with speech against
Silero's own last stop (the agent's proxy, reported apart). Two answerers give the turn ends:
`reference`, each labelled end as the turn end, which reads no audio and scores 0 cut-offs and
0 ms (the harness checking itself), and `pipeline`, the file-fed pipeline through the `evals`
facade's `turn_ends`, each clip a fresh call at real-time pace with `LEAD_S` of silence before
it and `TAIL_S` after it, the same for every variant, and a speech-to-text that answers at once.

As `poe eval`, a run refuses the main checkout and a dirty tree, an `--out` that exists or that
git would track, and audio that is not the file its manifest hashed, all before any clip is fed;
a dev run writes each result as it finishes (`results.jsonl`) and a progress line of identifiers
and verdicts; a held-out run writes the paused requests' aggregates only, and its lines are
counts. The scorecard is written whole at the end, and a run of the pipeline appends its history
line (`run_lines.EotLine`), spending nothing; a `reference` run appends none.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import AsyncIterator, Callable, Sequence
from pathlib import Path
from typing import Final, get_args

from t2_agentic_voice import T2VoiceError, VoiceSettings, configure_logging, evals, get_logger
from t2_agentic_voice.ports import AudioClip

from ole5_voice import LOGGERS
from ole5_voice.evals import history, run_settings
from ole5_voice.evals.audio import read_wav
from ole5_voice.evals.eot_score import (
    Decision,
    EotResult,
    EotRun,
    EotScorecard,
    EotSet,
    judge,
    proxy_end,
    set_card,
)
from ole5_voice.evals.items import HISTORY_FILE
from ole5_voice.evals.models import NAME_RULE, Split, is_name
from ole5_voice.evals.run_lines import AnyLine, EotCount, EotLine
from ole5_voice.evals.run_parts import DATA, Choice, Parts, Todo, audio_roots, load_plan
from ole5_voice.evals.runs import SCORECARD_FILE, holds_placeholder
from ole5_voice.evals.worktree import check_out, refused, run_checkout

ANSWERERS: Final = ("reference", "pipeline")
LEAD_S: Final = 1.0  # digital silence before each clip (the registration's E)
TAIL_S: Final = 4.5  # and after it: past the 4 s miss window and Smart Turn's 3 s fallback
RESULTS_FILE: Final = "results.jsonl"
PAUSED_KIND: Final = "paused_request"
# The secondary set's kinds: every other kind of item with speech (the registration's E).
SECONDARY_KINDS: Final = frozenset(
    {
        "request",
        "short_request",
        "stop_word",
        "repeat_request",
        "listening_sound",
        "confirmation",
        "ticket_number",
    }
)
_DESCRIPTION = "Measure where the turns end on the golden set, offline, into a new folder --out."
log = get_logger(__name__)
TurnEnds = Callable[..., AsyncIterator[tuple[evals.TurnEnd, ...]]]
AppendLine = Callable[[AnyLine, Path], None]  # `history.append_line`, or a test's


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="poe eot", description=_DESCRIPTION)
    add = parser.add_argument
    add("--answerer", choices=ANSWERERS, help="reference (the labelled ends) or pipeline")
    add("--split", choices=get_args(Split), help="the split the run covers, all of it")
    add("--secondary", action="store_true", help="also the dev variants with no mark (pipeline)")
    add("--env-file", type=Path, help="the .env file the settings load from (never printed)")
    add("--var-dir", type=Path, help="the settings' var_dir")
    add("--audio", action="append", default=[], metavar="ROOT=FOLDER", help="an audio root")
    add("--out", type=Path, help="a new folder, outside the worktree, that git ignores")
    add("--note", help="why the run is made")
    return parser


def _require(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    missing = [
        f"--{name}" for name in ("answerer", "split", "out", "note") if not getattr(args, name)
    ]
    if missing:
        parser.error(f"a run needs {', '.join(missing)}")
    if holds_placeholder(args.note):
        parser.error("--note holds an install placeholder, which the docs check refuses")
    if args.secondary and (args.answerer != "pipeline" or args.split != "dev"):
        parser.error("--secondary is a dev run of the pipeline: its true ends are Silero's own")


def _settings(args: argparse.Namespace) -> VoiceSettings:
    """The settings, as `poe eval` loads them: the environment and `--env-file` (or the working
    folder's `.env`), as `env=dev`, with `--var-dir` on top."""
    env_file = args.env_file
    if env_file is None and run_settings.DOTENV is not None and run_settings.DOTENV.is_file():
        env_file = run_settings.DOTENV
    loaded = VoiceSettings.from_env(env_file=env_file, env="dev")
    if args.var_dir is None:
        return loaded
    storage = loaded.storage.model_copy(update={"var_dir": args.var_dir})
    return loaded.model_copy(update={"storage": storage})


def shown(settings: VoiceSettings, args: argparse.Namespace) -> dict[str, str]:
    """What a run's turn ends depend on, by dotted name: every `turns` setting, and the run's
    padding and sets."""
    turns = {
        f"turns.{name}": str(value).lower() if isinstance(value, bool) else str(value)
        for name, value in settings.turns.model_dump().items()
    }
    run = {"run.lead_s": str(LEAD_S), "run.tail_s": str(TAIL_S)}
    return {"env": settings.env, **turns, **run, "run.secondary": str(args.secondary).lower()}


def _true_end(todo: Todo) -> float:
    marks = todo.variant.turn_ends_ms
    if not marks:
        raise refused("a paused request has no turn end marked", "mark it in the recorder")
    return float(marks[-1])


def _clip(todo: Todo) -> AudioClip:
    """A variant's audio, its segments joined in order (16 kHz mono PCM16, as checked)."""
    pcm16 = b"".join(read_wav(path).pcm16 for path in todo.request.segments)
    return AudioClip(pcm16=pcm16)


def _result(todo: Todo, side: Split, which: EotSet, ends: Sequence[Decision]) -> EotResult:
    item, variant = todo.item, todo.variant
    labelled = which == "paused"
    true_end = _true_end(todo) if labelled else proxy_end(ends)
    return EotResult(
        item=item.id,
        variant=variant.id,
        split=side,
        kind=item.kind,
        language=item.language,
        device=variant.device,
        set=which,
        ends=tuple(ends),
        judged=judge(ends, true_end, labelled=labelled),
    )


class _Progress:
    """The results so far, each written and logged as it comes (counts only when held out)."""

    def __init__(self, total: int, results_file: Path | None) -> None:
        self.total, self.results_file = total, results_file
        self.results: list[EotResult] = []
        self.interrupted = False

    def add(self, result: EotResult) -> None:
        self.results.append(result)
        done = len(self.results)
        if self.results_file is None:
            log.info("progress", done=done, of=self.total)
            return
        with self.results_file.open("a", encoding="utf-8", newline="\n") as file:
            file.write(result.model_dump_json() + "\n")
        judged = result.judged
        log.info(
            "variant_done",
            done=done,
            of=self.total,
            item=result.item,
            variant=result.variant,
            set=result.set,
            verdict=judged.verdict,
            delay_ms=None if judged.delay_ms is None else round(judged.delay_ms),
        )


async def _fed(
    todo: Sequence[tuple[Todo, EotSet]],
    progress: _Progress,
    settings: VoiceSettings,
    turn_ends: TurnEnds,
    side: Split,
) -> None:
    """Each variant through the pipeline, as a fresh call, in order."""
    clips = [_clip(each) for each, _ in todo]
    found = turn_ends(clips, settings=settings, lead_s=LEAD_S, tail_s=TAIL_S)
    try:
        index = 0
        async for ends in found:
            each, which = todo[index]
            index += 1
            decisions = [Decision(speech_stop_ms=e.speech_stop_ms, end_ms=e.end_ms) for e in ends]
            progress.add(_result(each, side, which, decisions))
    finally:
        close = getattr(found, "aclose", None)
        if close is not None:
            await close()


def _run(
    args: argparse.Namespace, parts: Parts, turn_ends: TurnEnds, append_line: AppendLine
) -> int:
    settings = _settings(args)
    checkout = run_checkout(parts.folder, parts.git)
    out = check_out(args.out, checkout, parts.git)
    if not is_name(out.name):
        raise refused(
            f"the --out folder's name, the run's, is not a name, which is {NAME_RULE}",
            "name the folder like e1-dev",
        )
    pipeline = args.answerer == "pipeline"
    choice = Choice(split=args.split, roots=audio_roots(args.audio), needs_audio=pipeline)
    plan = load_plan(checkout.top / DATA, choice, parts)
    paused = [t for t in plan.todo if t.item.kind == PAUSED_KIND]
    others = [t for t in plan.todo if t.item.kind in SECONDARY_KINDS] if args.secondary else []
    sets: tuple[EotSet, EotSet] = ("paused", "secondary")
    todo = [(t, sets[0]) for t in paused] + [(t, sets[1]) for t in others]
    if not paused:
        raise refused("the split holds no paused request the owner has checked", "check --split")
    true_ends = [_true_end(each) for each in paused]
    info = EotRun(
        name=out.name,
        started_at=parts.now(),
        commit=checkout.commit,
        answerer=args.answerer,
        split=args.split,
        settings=shown(settings, args),
        data_digest=plan.digest,
        lead_s=LEAD_S,
        tail_s=TAIL_S,
        note=args.note,
    )
    held_out = args.split == "held-out"
    out.mkdir(parents=True)
    progress = _Progress(len(todo), None if held_out else out / RESULTS_FILE)
    log.info("run_started", run=info.name, split=info.split, variants=len(todo))
    if not pipeline:
        for each, end in zip(paused, true_ends, strict=True):
            labelled = [Decision(speech_stop_ms=end, end_ms=end)]
            progress.add(_result(each, args.split, "paused", labelled))
    else:
        try:
            asyncio.run(_fed(todo, progress, settings, turn_ends, args.split))
        except KeyboardInterrupt:
            progress.interrupted = True
            log.warning("run_interrupted", done=len(progress.results), of=len(todo))
    return _close(info, progress, len(todo), args.secondary, out, checkout.top, append_line)


def _close(
    info: EotRun,
    progress: _Progress,
    total: int,
    secondary: bool,
    out: Path,
    top: Path,
    append_line: AppendLine,
) -> int:
    """The scorecard, and for a run of the pipeline its history line; 0 when complete."""
    complete = not progress.interrupted and len(progress.results) == total
    held_out = info.split == "held-out"
    kept = progress.results if complete or not held_out else []
    paused = [r for r in kept if r.set == "paused"]
    others = [r for r in kept if r.set == "secondary"]
    card = EotScorecard(
        run=info,
        complete=complete,
        paused=set_card(paused, held_out=held_out),
        secondary=set_card(others, held_out=False) if secondary else None,
        variants=() if held_out else tuple(kept),
    )
    partial = out / f".{SCORECARD_FILE}.partial"
    partial.write_bytes((card.model_dump_json(indent=2) + "\n").encode("utf-8"))
    partial.replace(out / SCORECARD_FILE)
    if info.answerer == "pipeline":
        line = line_of(card)
        append_line(line, top / DATA / HISTORY_FILE)
        append_line(line, out / HISTORY_FILE)
    totals = card.paused.totals
    log.info(
        "run_finished",
        complete=complete,
        variants=totals.variants,
        cut_offs=totals.cut_offs,
        misses=totals.misses,
        delay_median_ms=totals.delay_median_ms,
    )
    return 0 if complete else 1


def line_of(card: EotScorecard) -> EotLine:
    """The history line of an end-of-turn run's scorecard."""
    run, totals = card.run, card.paused.totals

    def count(m: object) -> EotCount:
        return EotCount.model_validate(m, from_attributes=True)

    return EotLine(
        time=run.started_at,
        commit=run.commit,
        run=run.name,
        answerer=run.answerer,
        settings=run.settings,
        split=run.split,
        items=totals.items,
        variants=totals.variants,
        cut_offs=totals.cut_offs,
        misses=totals.misses,
        delay_median_ms=totals.delay_median_ms,
        delay_p90_ms=totals.delay_p90_ms,
        secondary=None if card.secondary is None else count(card.secondary.totals),
        breakdowns={
            stratum: {value: count(m) for value, m in values.items()}
            for stratum, values in card.paused.breakdowns.items()
            if stratum != "item"
        },
        scorecard=SCORECARD_FILE,
        data_digest=run.data_digest,
        note=run.note,
        complete=card.complete,
    )


def main(
    argv: Sequence[str] | None = None,
    *,
    parts: Parts | None = None,
    turn_ends: TurnEnds = evals.turn_ends,
    append_line: AppendLine = history.append_line,
) -> int:
    """`uv run poe eot`: where the turns end on one split. 0 when the run is complete, 1 when it
    is not (an interrupt), 2 when it is refused before any clip is fed."""
    parser = _parser()
    args = parser.parse_args(argv)
    _require(parser, args)
    configure_logging(loggers=LOGGERS)
    try:
        return _run(args, Parts() if parts is None else parts, turn_ends, append_line)
    except T2VoiceError as error:
        log.error("eot_refused", code=error.code, message=error.message)
        return 2


if __name__ == "__main__":
    sys.exit(main())

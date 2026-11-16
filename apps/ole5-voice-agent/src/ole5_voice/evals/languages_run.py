"""`poe eval-languages`: plan 007's run H, its H1, each turn's language on the golden set,
offline and with no spend, into a new folder, `--out`; and `--read`, condition 4 of its keep
rule read across a commit's passes.

A pass feeds every checked variant of its split through the file-fed pipeline, each a fresh call
at real-time pace with `eot.LEAD_S` of silence before it and `eot.TAIL_S` after it, held in
Arabic with Ole5's two languages (`ECHO_AGENT`), through the `evals` facade's `turn_languages`:
`--classifier off` under `stt.live_language = "session"`; `silero` or `ecapa` under
`classified`, with the classifier the `classifiers` facade builds from the settings, its files
in `--classifier-dir` (or `stt.classifier_dir`), loaded before any clip is fed. The rule's
numbers are the registered ones (Q20: `stt.classifier_from_s` 2.0, `stt.classifier_min_share`
0.7 and `stt.classifier_threads` 2), and a pass under others is refused. One call runs at a
time, so no turn finds the classifier busy with another call's.

As `poe eot`, a pass refuses the main checkout and a dirty tree, an `--out` that exists or that
git would track, a name that is no name, audio that is not the file its manifest hashed and a
paused request with no mark, all before any clip is fed, and a classifier whose files are
missing or changed at its load, before too. A dev pass writes each variant's turns as it
finishes (`TURNS_FILE`) with a progress line of identifiers and counts, never anything said; a
held-out pass logs counts only and keeps its turns whole once complete, for run H's held-out
H2 runs and condition 4 to read, never printed or shown by variant. The scorecard
(languages_score.py) is written whole at the end, with the process's peak memory where the
platform tells it (`peak_mb`), and the pass's history line is appended to the worktree's history
and copied beside the scorecard, spending nothing; `--smoke-only` feeds the run's first dev
variant alone and appends no line. Every pass of run H runs at one commit, each alone, its line
kept aside until the last has run (plan 007's "Run H").

`--read RUN ...` reads the complete passes of one commit, split and data, exactly two of them
off, and logs condition 4 for each classifier pass (languages_reading.read_passes), writing
nothing.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import AsyncIterator, Callable, Sequence
from pathlib import Path
from typing import get_args

from t2_agentic_voice import (
    T2VoiceError,
    VoiceSettings,
    configure_logging,
    evals,
    get_logger,
)
from t2_agentic_voice.ports import LanguageClassifier

from ole5_voice import LOGGERS
from ole5_voice.agent import ECHO_AGENT
from ole5_voice.evals import history
from ole5_voice.evals.cli import require
from ole5_voice.evals.eot import LEAD_S, TAIL_S
from ole5_voice.evals.languages_card import PAUSED_KIND, TURNS_FILE, ClassifierName, LanguagesRun
from ole5_voice.evals.languages_pass import (
    AppendLine,
    Progress,
    close_pass,
    read_condition_4,
    result_of,
)
from ole5_voice.evals.languages_setup import (
    CODES,
    HELD_IN,
    classifier_of,
    peak_mb,
    settings_of,
    shown,
)
from ole5_voice.evals.models import NAME_RULE, Split, is_name
from ole5_voice.evals.run_parts import (
    DATA,
    Choice,
    Parts,
    Todo,
    audio_roots,
    clip_of,
    load_plan,
    marked_end,
)
from ole5_voice.evals.worktree import check_out, refused, run_checkout

_DESCRIPTION = "Measure each turn's language on the golden set, offline, into a new folder --out."
log = get_logger(__name__)
TurnLanguages = Callable[..., AsyncIterator[tuple[evals.LanguageTurn, ...]]]
MakeClassifier = Callable[[VoiceSettings], LanguageClassifier]
Peak = Callable[[], float | None]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="poe eval-languages", description=_DESCRIPTION)
    add = parser.add_argument
    add("--split", choices=get_args(Split), help="the split the pass covers, all of it")
    add("--classifier", choices=get_args(ClassifierName), help="off (session), silero or ecapa")
    add("--classifier-dir", type=Path, help="the classifier's model files (stt.classifier_dir)")
    add("--env-file", type=Path, help="the .env file the settings load from (never printed)")
    add("--var-dir", type=Path, help="the settings' var_dir")
    add("--audio", action="append", default=[], metavar="ROOT=FOLDER", help="an audio root")
    add("--out", type=Path, help="a new folder, outside the worktree, that git ignores")
    add("--note", help="why the pass is made")
    add("--smoke-only", action="store_true", help="feed the first dev variant alone")
    add("--read", nargs="+", type=Path, metavar="RUN", help="read passes' folders: condition 4")
    return parser


def _require(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    if args.read:
        if any(getattr(args, n) for n in ("split", "classifier", "out", "note", "smoke_only")):
            parser.error("--read takes the passes alone")
        return
    require(parser, args, ("split", "classifier", "out", "note"), noun="pass")
    if args.smoke_only and args.split != "dev":
        parser.error("--smoke-only is a dev run: its variant is the first dev one")


async def _loaded(classifier: LanguageClassifier) -> None:
    """The classifier loaded with Ole5's codes, or closed and refused."""
    try:
        await classifier.load(CODES)
    except BaseException:
        await classifier.aclose()
        raise


async def _fed(
    todo: Sequence[Todo],
    progress: Progress,
    settings: VoiceSettings,
    classifier: LanguageClassifier | None,
    turn_languages: TurnLanguages,
    side: Split,
) -> None:
    """Each variant through the pipeline, as a fresh call, in order; the classifier closed at
    the end."""
    clips = [clip_of(each) for each in todo]
    found = turn_languages(
        clips,
        languages=ECHO_AGENT.languages,
        settings=settings,
        classifier=classifier,
        lead_s=LEAD_S,
        tail_s=TAIL_S,
    )
    try:
        index = 0
        async for turns in found:
            progress.add(result_of(todo[index], side, turns))
            index += 1
    finally:
        close = getattr(found, "aclose", None)
        if close is not None:
            await close()
        if classifier is not None:
            await classifier.aclose()


def _run(
    args: argparse.Namespace,
    parts: Parts,
    turn_languages: TurnLanguages,
    make_classifier: MakeClassifier,
    append_line: AppendLine,
    peak: Peak,
) -> int:
    settings = settings_of(args)
    checkout = run_checkout(parts.folder, parts.git)
    out = check_out(args.out, checkout, parts.git)
    if not is_name(out.name):
        raise refused(
            f"the --out folder's name, the run's, is not a name, which is {NAME_RULE}",
            "name the folder like lid1-dev-silero",
        )
    choice = Choice(split=args.split, roots=audio_roots(args.audio), needs_audio=True)
    plan = load_plan(checkout.top / DATA, choice, parts)
    todo = [plan.smoke] if args.smoke_only else list(plan.todo)
    for each in todo:
        if each.item.kind == PAUSED_KIND:
            marked_end(each)
    info = LanguagesRun(
        name=out.name,
        started_at=parts.now(),
        commit=checkout.commit,
        split=args.split,
        classifier=args.classifier,
        settings=shown(settings, args),
        data_digest=plan.digest,
        lead_s=LEAD_S,
        tail_s=TAIL_S,
        from_s=settings.stt.classifier_from_s,
        min_share=settings.stt.classifier_min_share,
        threads=settings.stt.classifier_threads,
        held_in=HELD_IN,
        note=args.note,
    )
    classifier = None if args.classifier == "off" else make_classifier(settings)
    if classifier is not None:
        asyncio.run(_loaded(classifier))
    held_out = args.split == "held-out"
    out.mkdir(parents=True)
    progress = Progress(len(todo), None if held_out else out / TURNS_FILE)
    log.info("run_started", run=info.name, split=info.split, variants=len(todo))
    try:
        asyncio.run(_fed(todo, progress, settings, classifier, turn_languages, args.split))
    except KeyboardInterrupt:
        progress.interrupted = True
        log.warning("run_interrupted", done=len(progress.results), of=len(todo))
    info = info.model_copy(update={"peak_mb": peak()})
    return close_pass(info, progress, len(todo), args.smoke_only, out, checkout.top, append_line)


def main(
    argv: Sequence[str] | None = None,
    *,
    parts: Parts | None = None,
    turn_languages: TurnLanguages = evals.turn_languages,
    make_classifier: MakeClassifier = classifier_of,
    append_line: AppendLine = history.append_line,
    peak: Peak = peak_mb,
) -> int:
    """`uv run poe eval-languages`: one pass of run H's H1, or `--read` of its passes. 0 when
    the pass is complete or the passes were read, 1 when the pass is not (an interrupt), 2 when
    it is refused before any clip is fed."""
    parser = _parser()
    args = parser.parse_args(argv)
    _require(parser, args)
    configure_logging(loggers=LOGGERS)
    try:
        if args.read:
            return read_condition_4(args.read)
        parts = Parts() if parts is None else parts
        return _run(args, parts, turn_languages, make_classifier, append_line, peak)
    except T2VoiceError as error:
        log.error("eval_languages_refused", code=error.code, message=error.message)
        return 2


if __name__ == "__main__":
    sys.exit(main())

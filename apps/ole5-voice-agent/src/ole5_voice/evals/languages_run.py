"""`poe eval-languages`: run H's H1, each turn's language on the golden set, offline and with no
spend, or through a speech-to-text provider's own language, which spends, into a new folder,
`--out`; and `--read`, condition 4 of its keep rule read across a commit's passes.

A pass feeds every checked variant of its split through the file-fed pipeline, each a fresh call
at real-time pace with `eot.LEAD_S` of silence before it and `eot.TAIL_S` after it, held in
Arabic with Ole5's two languages (`ECHO_AGENT`), through the `evals` facade's `turn_languages`:
`--classifier off` under `stt.live_language = "session"`; `silero` or `ecapa` under
`classified`, with the classifier the `classifiers` facade builds from the settings, its files
in `--classifier-dir` (or `stt.classifier_dir`), loaded before any clip is fed; `detected` under
`detected`, no classifier, each turn recording whether it also goes naming no language; `groq`,
`elevenlabs` or `soniox` under `classified`, through that provider's own language
(provider_language.py, D-100), each classified turn's first seconds sent to it with no language
named. A provider's pass needs `--price-per-hour` and `--cap-usd`, logs its dry estimate (the
most it can send and cost) before any clip is fed and is refused past the cap; `--estimate-only`
stops there, building no adapter, so it needs no key, and making no folder. The rule's
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
platform tells it (`peak_mb`), and, for a provider's pass, its price and what it sent at the
most, and the pass's history line is appended to the worktree's history and copied beside the
scorecard; `--smoke-only` feeds the run's first dev
variant alone and appends no line. Every pass of run H runs at one commit, each alone, its line
kept aside until the last has run (plan 007's "Run H").

`--read RUN ...` reads the complete passes of one commit, split and data, exactly two of them
off, and logs condition 4 for each classifier pass (languages_reading.read_passes), writing
nothing. `--scribe-arm ARM`, in place of `--classifier`, is a pass of one of run H's Scribe arms
(D-115; scribe_arm_run.py), which spends; `detected`'s takes its gate, `--language-from`.
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
from t2_agentic_voice.evals import check_out, run_checkout, run_refused
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
from ole5_voice.evals.provider_language import (
    PROVIDERS,
    ProviderLanguage,
    check_pass_cost,
    provider_language,
)
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
from ole5_voice.evals.runs import cost_usd
from ole5_voice.evals.scribe_arm_run import MakeStt, arm_flags, make_scribe, require_arm, run_arm
from ole5_voice.evals.stt_arms import ARMS

_DESCRIPTION = "Measure each turn's language on the golden set, offline, into a new folder --out."
log = get_logger(__name__)
TurnLanguages = Callable[..., AsyncIterator[tuple[evals.LanguageTurn, ...]]]
MakeClassifier = Callable[[VoiceSettings], LanguageClassifier]
MakeProvider = Callable[[VoiceSettings], ProviderLanguage]
_PRICED = ("price_per_hour", "cap_usd")
Peak = Callable[[], float | None]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="poe eval-languages", description=_DESCRIPTION)
    add = parser.add_argument
    add("--split", choices=get_args(Split), help="the split the pass covers, all of it")
    add(
        "--classifier",
        choices=get_args(ClassifierName),
        help="off (session), silero, ecapa or detected; or groq, elevenlabs or soniox, which spend",
    )
    add("--classifier-dir", type=Path, help="the classifier's model files (stt.classifier_dir)")
    add("--env-file", type=Path, help="the .env file the settings load from (never printed)")
    add("--var-dir", type=Path, help="the settings' var_dir")
    add("--audio", action="append", default=[], metavar="ROOT=FOLDER", help="an audio root")
    add("--out", type=Path, help="a new folder, outside the worktree, that git ignores")
    add("--note", help="why the pass is made")
    add("--smoke-only", action="store_true", help="feed the first dev variant alone")
    add("--price-per-hour", type=float, help="a provider's price per hour of audio, in USD")
    add("--cap-usd", type=float, help="the most a provider's pass may cost, in USD")
    add("--estimate-only", action="store_true", help="log a provider's estimate, send nothing")
    add("--read", nargs="+", type=Path, metavar="RUN", help="read passes' folders: condition 4")
    arm_flags(parser)  # --scribe-arm and --language-from
    return parser


def _require(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    if args.scribe_arm or args.language_from:
        return require_arm(parser, args)
    if args.read:
        if any(getattr(args, n) for n in ("split", "classifier", "out", "note", "smoke_only")):
            parser.error("--read takes the passes alone")
        return
    provider = args.classifier in PROVIDERS
    priced = _PRICED if provider else ()
    require(parser, args, ("split", "classifier", "out", "note", *priced), noun="pass")
    if not provider and (args.estimate_only or any(getattr(args, n) is not None for n in _PRICED)):
        parser.error("--price-per-hour, --cap-usd and --estimate-only serve a provider's pass")
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
    make_provider: MakeProvider,
    append_line: AppendLine,
    peak: Peak,
) -> int:
    settings = settings_of(args)
    checkout = run_checkout(parts.folder, parts.git)
    out = check_out(args.out, checkout, parts.git)
    if not is_name(out.name):
        raise run_refused(
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
    provider: ProviderLanguage | None = None
    if args.classifier in PROVIDERS:
        estimate = check_pass_cost(
            ARMS[args.classifier],
            [clip_of(each).seconds for each in todo],
            from_s=settings.stt.classifier_from_s,
            tail_s=TAIL_S,
            price_per_hour_usd=args.price_per_hour,
            cap_usd=args.cap_usd,
            estimate_only=args.estimate_only,
        )
        if estimate == "estimated":
            return 0
        provider = make_provider(settings)
    unclassified = args.classifier in ("off", "detected")
    built = provider or (None if unclassified else make_classifier(settings))
    classifier: LanguageClassifier | None = built
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
    spent: dict[str, float | None] = {"peak_mb": peak()}
    if provider is not None:
        price, billed = args.price_per_hour, provider.billed_seconds
        spent |= {"price_per_hour_usd": price, "billed_seconds": billed}
        spent |= {"cost_usd": cost_usd(billed, price)}
    info = info.model_copy(update=spent)
    return close_pass(info, progress, len(todo), args.smoke_only, out, checkout.top, append_line)


def main(
    argv: Sequence[str] | None = None,
    *,
    parts: Parts | None = None,
    turn_languages: TurnLanguages = evals.turn_languages,
    make_classifier: MakeClassifier = classifier_of,
    make_provider: MakeProvider = provider_language,
    append_line: AppendLine = history.append_line,
    peak: Peak = peak_mb,
    make_stt: MakeStt = make_scribe,
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
        if args.scribe_arm:
            return run_arm(args, parts, make_stt)
        return _run(args, parts, turn_languages, make_classifier, make_provider, append_line, peak)
    except T2VoiceError as error:
        log.error("eval_languages_refused", code=error.code, message=error.message)
        return 2


if __name__ == "__main__":
    sys.exit(main())

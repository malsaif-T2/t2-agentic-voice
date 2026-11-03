"""`poe eval-timing`: the time of each step of an echo call on the golden set's dev paused
requests (plan 003's registration, T), into a new folder, `--out`; it spends, so a run is T1 or
T2 and no held-out run is made.

As `poe eval`, a run refuses the main checkout and a dirty tree, an `--out` that exists or that
git would track, and audio that is not the file its manifest hashed, before anything is sent;
it pins its model, timeout, prices and cap on the command line, and its base URL is `--base-url`
or the SDK's own (`run_settings.load_settings`); the call is untraced, with `tts.trim_silence`
off and `stt.live_language` `session`, each refused otherwise. It declares the fixed phrases
(`PhraseCache.declare`), then runs a smoke test, the first variant, which must pass with no
failed or retried call; then each variant as a fresh call (`timing_run.py`), each result written
as it finishes (`results.jsonl`) with a progress line of identifiers and times, never a text.
Its scorecard is written whole at the end, and its history line (`run_lines.TimingLine`)
appended to the worktree's `history.jsonl` and copied beside the scorecard, every request it
sent counted.
"""

from __future__ import annotations

import argparse
import asyncio
import math
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

from t2_agentic_voice import (
    ConfigurationError,
    ProviderError,
    T2VoiceError,
    VoiceSettings,
    configure_logging,
    evals,
    get_logger,
)
from t2_agentic_voice.events import ModelUsage
from t2_agentic_voice.groq import GroqSTT, GroqTTS
from t2_agentic_voice.ports import SpeechToText, TextToSpeech
from t2_agentic_voice.stores import PhraseCache

from ole5_voice import LOGGERS
from ole5_voice.evals import history, run_settings
from ole5_voice.evals.eot import LEAD_S, PAUSED_KIND, TAIL_S
from ole5_voice.evals.items import HISTORY_FILE
from ole5_voice.evals.models import NAME_RULE, is_name
from ole5_voice.evals.pacers import MinutePacer
from ole5_voice.evals.run_lines import AnyLine, TimingLine
from ole5_voice.evals.run_parts import DATA, Choice, Parts, Todo, audio_roots, load_plan
from ole5_voice.evals.runs import SCORECARD_FILE, holds_placeholder
from ole5_voice.evals.timing_run import (
    AGENT,
    TAGS,
    CapReachedError,
    EchoTimings,
    Measuring,
    Phrases,
    Prices,
)
from ole5_voice.evals.timing_score import (
    STEPS,
    Stopped,
    TimingResult,
    TimingRun,
    TimingScorecard,
    by_language,
    metrics,
    summed,
)
from ole5_voice.evals.worktree import check_out, refused, run_checkout

STT_RPM: Final = 10  # Whisper requests a minute, at most (the registration's T)
TTS_RPM: Final = 5  # requests a minute to each Orpheus model, at most
RESULTS_FILE: Final = "results.jsonl"
_DESCRIPTION = "Time each step of an echo call on the golden set's dev paused requests."
log = get_logger(__name__)
AppendLine = Callable[[AnyLine, Path], None]


def _phrase_cache(settings: VoiceSettings, tts: TextToSpeech) -> Phrases:
    """The phrase cache the runtime would build, kept in the agent's own folder."""
    folder = settings.storage.var_dir / AGENT.name / "phrases"
    return PhraseCache.from_settings(settings, tts, folder=folder)


@dataclass(frozen=True)
class TimingParts:
    """What a timing run is built from, each replaceable by a test's fake: the run's `Parts`
    (its checkout, the golden set's loaders, the clocks), the speech adapters, the phrase
    cache, the measurement and the history."""

    plan: Parts = field(default_factory=Parts)
    speech_to_text: Callable[[VoiceSettings], SpeechToText] = GroqSTT.from_settings
    text_to_speech: Callable[[VoiceSettings], TextToSpeech] = GroqTTS.from_settings
    phrases: Callable[[VoiceSettings, TextToSpeech], Phrases] = _phrase_cache
    echo_timings: EchoTimings = evals.echo_timings
    append_line: AppendLine = history.append_line


def _amount(text: str) -> float:
    if not math.isfinite(value := float(text)) or value < 0:
        raise argparse.ArgumentTypeError("must be a finite number, 0 or more")
    return value


def _count(text: str) -> int:
    if (value := int(text)) < 1:
        raise argparse.ArgumentTypeError("must be 1 or more")
    return value


def _price(text: str) -> tuple[str, float]:
    model, equals, amount = text.partition("=")
    if not equals or not model:
        raise argparse.ArgumentTypeError("give a price as MODEL=USD, per million characters")
    return model, _amount(amount)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="poe eval-timing", description=_DESCRIPTION)
    add = parser.add_argument
    add("--split", choices=("dev",), help="dev: a timing run spends, and no held-out run does")
    add("--model", choices=run_settings.MODELS, help="stt.model for this run")
    add("--timeout-s", type=_amount, help="stt.timeout_s for this run")
    add("--base-url", help=f"groq.base_url for this run ({run_settings.GROQ_BASE_URL})")
    add("--env-file", type=Path, help="the .env file the settings load from (never printed)")
    add("--var-dir", type=Path, help="the settings' var_dir, which holds the phrase cache")
    add("--audio", action="append", default=[], metavar="ROOT=FOLDER", help="an audio root")
    add("--out", type=Path, help="a new folder, outside the worktree, that git ignores")
    add("--price-per-hour", type=_amount, help="USD an hour of Whisper's billed audio")
    add(
        "--tts-price",
        type=_price,
        action="append",
        default=[],
        metavar="MODEL=USD",
        help="USD per million characters of an Orpheus model, once per model",
    )
    add("--cap-usd", type=_amount, help="the most the run may spend")
    add("--stt-rpm", type=_count, default=STT_RPM, help=f"Whisper requests a minute ({STT_RPM})")
    add("--tts-rpm", type=_count, default=TTS_RPM, help=f"each Orpheus model's ({TTS_RPM})")
    add("--smoke-only", action="store_true", help="run the smoke test alone")
    add("--note", help="why the run is made")
    parser.set_defaults(tracing_endpoint=None)  # a timing run is untraced
    return parser


def _require(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    named = ("split", "model", "timeout_s", "out", "price_per_hour", "cap_usd", "note")
    missing = [f"--{name.replace('_', '-')}" for name in named if getattr(args, name) is None]
    if missing:
        parser.error(f"a run needs {', '.join(missing)}")
    if holds_placeholder(args.note):
        parser.error("--note holds an install placeholder, which the docs check refuses")


def _checked(settings: VoiceSettings, args: argparse.Namespace) -> dict[str, float]:
    """The settings a timing run measures under, refused otherwise, and each Orpheus model's
    price."""
    if settings.tts.trim_silence or settings.stt.live_language != "session":
        raise ConfigurationError(
            "A timing run measures the audio as it comes, sending Whisper the session's "
            "language. FIX: set tts.trim_silence false and stt.live_language session.",
            details={"setting": "tts.trim_silence, stt.live_language"},
        )
    prices = dict(args.tts_price)
    models = sorted({settings.tts.languages[language.tag].model for language in AGENT.languages})
    if unpriced := [model for model in models if model not in prices]:
        raise refused(
            f"--tts-price names no price for {', '.join(unpriced)}",
            "give --tts-price MODEL=USD for each Orpheus model the run speaks",
        )
    return {model: prices[model] for model in models}


def _shown(settings: VoiceSettings, args: argparse.Namespace) -> dict[str, str]:
    """Every setting, as `poe eval` records them, with the timing run's own."""
    namespace = argparse.Namespace(
        **vars(args),
        language_hint="label",
        max_rpm=args.stt_rpm,
        max_attempts=1,
        variant_timeout_s=0,
        windows_ms=[],
    )
    library = {
        k: v for k, v in run_settings.shown(settings, namespace).items() if not k.startswith("run.")
    }
    run = {
        "run.lead_s": str(LEAD_S),
        "run.tail_s": str(TAIL_S),
        "run.stt_rpm": str(args.stt_rpm),
        "run.tts_rpm": str(args.tts_rpm),
        "run.cap_usd": str(args.cap_usd),
        "run.smoke_only": str(args.smoke_only).lower(),
    }
    return library | run


@dataclass
class _Found:
    results: list[TimingResult] = field(default_factory=list)
    smoke: TimingResult | None = None
    smoke_usage: tuple[ModelUsage, ...] = ()
    stopped: Stopped | None = None


async def _measure(
    measuring: Measuring, todo: Sequence[Todo], found: _Found, out: Path, smoke_only: bool
) -> None:
    try:
        await measuring.declare()
        smoke = found.smoke = await measuring.variant(todo[0])
        found.smoke_usage = summed(measuring.usages)  # the run's first calls
        if smoke.failure is not None or smoke.attempts > 1:
            found.stopped = "smoke_failed"
            log.error("smoke_failed", failure=smoke.failure, attempts=smoke.attempts)
            return
        log.info("smoke_passed", requests=sum(u.requests for u in measuring.usages))
        for each in () if smoke_only else todo:
            result = await measuring.variant(each)
            found.results.append(result)
            with (out / RESULTS_FILE).open("a", encoding="utf-8", newline="\n") as file:
                file.write(result.model_dump_json() + "\n")
            steps = result.steps
            log.info(
                "variant_done",
                done=len(found.results),
                of=len(todo),
                item=result.item,
                variant=result.variant,
                attempts=result.attempts,
                cut=result.cut,
                failure=result.failure,
                first_audio_ms=None if steps is None else steps.first_audio,
                heard_words_ms=None if steps is None else steps.heard_words,
            )
    except CapReachedError:
        found.stopped = "cap"
        log.warning("cap_reached", done=len(found.results), of=len(todo))
    except ProviderError as error:  # the phrase cache's, before the first variant
        found.stopped = "phrases_failed"
        log.error("phrases_failed", kind=error.kind)
    finally:
        await measuring.aclose()


def _run(args: argparse.Namespace, parts: TimingParts) -> int:
    settings = run_settings.load_settings(args)
    tts_prices = _checked(settings, args)
    plan_parts = parts.plan
    checkout = run_checkout(plan_parts.folder, plan_parts.git)
    out = check_out(args.out, checkout, plan_parts.git)
    if not is_name(out.name):
        raise refused(
            f"the --out folder's name, the run's, is not a name, which is {NAME_RULE}",
            "name the folder like t1",
        )
    choice = Choice(split="dev", roots=audio_roots(args.audio), needs_audio=True)
    plan = load_plan(checkout.top / DATA, choice, plan_parts)
    todo = [t for t in plan.todo if t.item.kind == PAUSED_KIND and t.item.language in TAGS]
    if not todo or any(not t.variant.turn_ends_ms for t in todo):
        raise refused(
            "the dev split holds no paused request, or one with no turn end marked",
            "mark each in the recorder, and check the committed split",
        )
    info = TimingRun(
        name=out.name,
        started_at=plan_parts.now(),
        commit=checkout.commit,
        split="dev",
        settings=_shown(settings, args),
        data_digest=plan.digest,
        lead_s=LEAD_S,
        tail_s=TAIL_S,
        stt_rpm=args.stt_rpm,
        tts_rpm=args.tts_rpm,
        price_per_hour_usd=args.price_per_hour,
        tts_price_per_million_usd=tts_prices,
        cap_usd=args.cap_usd,
        note=args.note,
    )
    clock, sleep = plan_parts.clock, plan_parts.sleep
    pacers: dict[str, MinutePacer] = {settings.stt.model: MinutePacer(args.stt_rpm, clock, sleep)}
    pacers |= {model: MinutePacer(args.tts_rpm, clock, sleep) for model in tts_prices}
    prices = Prices(settings.stt.model, args.price_per_hour, tts_prices, args.cap_usd)
    tts = parts.text_to_speech(settings)
    measuring = Measuring(
        settings=settings,
        stt=parts.speech_to_text(settings),
        tts=tts,
        phrases=parts.phrases(settings, tts),
        echo_timings=parts.echo_timings,
        pacers=pacers,
        prices=prices,
        sleep=sleep,
    )
    out.mkdir(parents=True)
    found = _Found()
    log.info("run_started", run=info.name, variants=len(todo))
    try:
        asyncio.run(_measure(measuring, todo, found, out, args.smoke_only))
    except KeyboardInterrupt:
        found.stopped = "interrupted"
        log.warning("run_interrupted", done=len(found.results), of=len(todo))
    expected = 0 if args.smoke_only else len(todo)
    complete = found.stopped is None and len(found.results) == expected
    card = TimingScorecard(
        run=info,
        complete=complete,
        stopped=found.stopped,
        phrase_requests=measuring.phrase_requests,
        smoke=found.smoke_usage,
        totals=metrics(found.results),
        languages=by_language(found.results),
        spend=summed(measuring.usages),
        cost_usd=prices.of(measuring.usages),
        variants=tuple(found.results),
    )
    partial = out / f".{SCORECARD_FILE}.partial"
    partial.write_bytes((card.model_dump_json(indent=2) + "\n").encode("utf-8"))
    partial.replace(out / SCORECARD_FILE)
    line = line_of(card)
    parts.append_line(line, checkout.top / DATA / HISTORY_FILE)
    parts.append_line(line, out / HISTORY_FILE)
    log.info("run_finished", complete=complete, variants=len(found.results), cost_usd=card.cost_usd)
    return 0 if complete else 1


def line_of(card: TimingScorecard) -> TimingLine:
    """The history line of a timing run's scorecard: every request it sent, and each step's
    median over its timed turns."""
    run = card.run
    stt = [usage for usage in card.spend if usage.model.startswith("whisper")]
    return TimingLine(
        time=run.started_at,
        commit=run.commit,
        run=run.name,
        settings=run.settings,
        split=run.split,
        variants=card.totals.variants,
        cut_variants=card.totals.cut_variants,
        failures=card.totals.failures,
        phrase_requests=card.phrase_requests,
        requests={usage.model: usage.requests for usage in card.spend},
        characters={usage.model: usage.characters for usage in card.spend if usage.characters},
        billed_seconds=sum(usage.billed_s for usage in stt),
        price_per_hour_usd=run.price_per_hour_usd,
        tts_price_per_million_usd=run.tts_price_per_million_usd,
        cost_usd=card.cost_usd,
        medians_ms={step: card.totals.steps[step].median_ms for step in STEPS},
        scorecard=SCORECARD_FILE,
        data_digest=run.data_digest,
        note=run.note,
        complete=card.complete,
    )


def main(argv: Sequence[str] | None = None, *, parts: TimingParts | None = None) -> int:
    """`uv run poe eval-timing`: time each step of an echo call over the dev paused requests.
    0 when the run is complete, 1 when it is not (a failed smoke test, the cap, an interrupt),
    2 when it is refused before anything is sent."""
    parser = _parser()
    args = parser.parse_args(argv)
    _require(parser, args)
    configure_logging(loggers=LOGGERS)
    try:
        return _run(args, TimingParts() if parts is None else parts)
    except T2VoiceError as error:
        log.error("timing_refused", code=error.code, message=error.message)
        return 2


if __name__ == "__main__":
    sys.exit(main())

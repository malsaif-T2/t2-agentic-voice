"""`poe uncertain`: run U, the uncertain middle (plan 006's registration), on a stored overlap
run, into a new folder, `--out`, as evaluation.md's "Running" says.

It reads one complete dev overlap run's scorecard (`--overlaps`: plan 005's O1 or O2), judges
each of its overlaps again under the session's rule at this commit from the transcripts it
stored, replaying its recordings (`--audio`) with nothing sent (uncertain_rejudge.py), takes the
overlaps whose verdict is then a short output or too few words (uncertain_score.py), and asks
the model arm about each (uncertain_run.py), scoring it against that verdict, U0. A held-out
overlap run's scorecard holds aggregates only, no overlap's words (evaluation.md, "Splits"), so
it is refused: U's held-out pass has no stored data to read.

As `poe overlap`, a run refuses the main checkout and a dirty tree and an `--out` that exists or
that git would track; its settings load as `poe eval`'s (the environment and `--env-file`, the
base URL `--base-url` or the SDK's own, untraced), then the model's from its flags and each
`--set`; and it refuses, before anything is sent, a run whose budget, every overlap and the smoke
test at their most, would pass `--cap-usd`, or whose requests would pass `--day-requests`. It
asks the smoke test first, the first overlap, which must answer one of the two words on its
first attempt; then each overlap, its result written as it finishes (`results.jsonl`) with a
progress line of identifiers and verdicts, never the words. Its scorecard is written whole at
the end, and its history line, an overlap line (`uncertain_card.line_of`), appended to the
worktree's `history.jsonl` and copied beside the scorecard, every request counted.
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

from t2_agentic_voice import T2VoiceError, VoiceSettings, configure_logging, evals, get_logger
from t2_agentic_voice.groq import GroqChat
from t2_agentic_voice.ports import ChatModel

from ole5_voice import LOGGERS
from ole5_voice.evals import history, run_settings
from ole5_voice.evals.audio import sha256_file
from ole5_voice.evals.files import read_model
from ole5_voice.evals.models import NAME_RULE, is_name
from ole5_voice.evals.overlap_card import AppendLine, OverlapScorecard
from ole5_voice.evals.overlap_plan import setting, with_set
from ole5_voice.evals.pacers import MinutePacer
from ole5_voice.evals.run_parts import DATA, Choice, Parts, audio_roots, load_plan
from ole5_voice.evals.runs import SCORECARD_FILE, holds_placeholder
from ole5_voice.evals.uncertain_card import UncertainRun, close_run
from ole5_voice.evals.uncertain_rejudge import ReplayerFactory, rejudged
from ole5_voice.evals.uncertain_run import Asking, Found, Prices, asked, request_of
from ole5_voice.evals.uncertain_score import uncertain_overlaps
from ole5_voice.evals.worktree import check_out, refused, run_checkout

RPM: Final = 20  # chat requests a minute, at most (the agent's: under the key's limit)
MAX_ATTEMPTS: Final = 3
ITEM_TIMEOUT_S: Final = 30.0
_DESCRIPTION = "Run U: a model's verdict on the stored overlaps the rule left uncertain."
log = get_logger(__name__)


@dataclass(frozen=True)
class UncertainParts:
    """What a run is built from, each replaceable by a test's fake: the run's `Parts` (its
    checkout, the golden set's loaders, the clocks), the replay, the chat model and the
    history."""

    plan: Parts = field(default_factory=Parts)
    audio_call: ReplayerFactory = evals.AudioCall
    chat_model: Callable[[VoiceSettings], ChatModel] = GroqChat.from_settings
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
    parser = argparse.ArgumentParser(prog="poe uncertain", description=_DESCRIPTION)
    add = parser.add_argument
    add("--overlaps", type=Path, help="a dev overlap run's scorecard, or its --out folder")
    add("--audio", action="append", default=[], metavar="ROOT=FOLDER", help="an audio root")
    add("--model", help="llm.model: the arm's chat model")
    add("--reasoning-effort", choices=("low", "medium", "high"), help="llm.reasoning_effort")
    add("--max-output-tokens", type=_count, help="llm.max_output_tokens")
    add("--timeout-s", type=_amount, help="llm.timeout_s")
    add("--temperature", type=_amount, default=0.0, help="the requests' temperature (0)")
    add("--base-url", help=f"groq.base_url for this run ({run_settings.GROQ_BASE_URL})")
    add("--env-file", type=Path, help="the .env file the settings load from (never printed)")
    add("--var-dir", type=Path, help="the settings' var_dir")
    add("--set", type=setting, action="append", default=[], metavar="GROUP.NAME=VALUE")
    add("--price-input", type=_amount, help="USD per million tokens read")
    add("--price-cached", type=_amount, help="USD per million cached tokens (the input's)")
    add("--price-output", type=_amount, help="USD per million tokens written")
    add("--cap-usd", type=_amount, help="the most the run may spend")
    add("--rpm", type=_count, default=RPM, help=f"chat requests a minute, at most ({RPM})")
    add("--day-requests", type=_count, help="the requests the key may still send today")
    add("--max-attempts", type=_count, default=MAX_ATTEMPTS, help=f"each's ({MAX_ATTEMPTS})")
    add("--item-timeout-s", type=_amount, default=ITEM_TIMEOUT_S, help="each request's limit")
    add("--out", type=Path, help="a new folder, outside the worktree, that git ignores")
    add("--note", help="why the run is made")
    add("--smoke-only", action="store_true", help="ask the smoke test alone")
    return parser


def _require(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    named = ["overlaps", "model", "reasoning_effort", "max_output_tokens", "timeout_s"]
    named += ["price_input", "price_output", "cap_usd", "day_requests", "out", "note"]
    missing = [f"--{name.replace('_', '-')}" for name in named if getattr(args, name) is None]
    if missing:
        parser.error(f"a run needs {', '.join(missing)}")
    if holds_placeholder(args.note):
        parser.error("--note holds an install placeholder, which the docs check refuses")


def _settings(args: argparse.Namespace) -> VoiceSettings:
    """The settings `poe eval` loads, untraced, with the model's from the flags and each
    `--set` on top."""
    loading = argparse.Namespace(
        env_file=args.env_file,
        tracing_endpoint=None,
        base_url=args.base_url,
        model=None,
        timeout_s=None,
        var_dir=args.var_dir,
    )
    pinned = [
        ("llm.model", args.model),
        ("llm.reasoning_effort", args.reasoning_effort),
        ("llm.max_output_tokens", args.max_output_tokens),
        ("llm.timeout_s", args.timeout_s),
    ]
    return with_set(run_settings.load_settings(loading), [*pinned, *args.set])


def shown(settings: VoiceSettings, args: argparse.Namespace) -> dict[str, str]:
    """Every setting, as `poe eval` records them, with the run's own."""
    namespace = argparse.Namespace(
        language_hint="none",
        max_rpm=args.rpm,
        max_attempts=args.max_attempts,
        variant_timeout_s=args.item_timeout_s,
        cap_usd=args.cap_usd,
        windows_ms=[],
        smoke_only=args.smoke_only,
    )
    library = run_settings.shown(settings, namespace)
    run = {
        "run.temperature": str(args.temperature),
        "run.rpm": str(args.rpm),
        "run.day_requests": str(args.day_requests),
        "run.max_attempts": str(args.max_attempts),
        "run.item_timeout_s": str(args.item_timeout_s),
        "run.cap_usd": str(args.cap_usd),
        "run.smoke_only": str(args.smoke_only).lower(),
    }
    return {k: v for k, v in library.items() if not k.startswith("run.")} | run


def _source(path: Path) -> tuple[OverlapScorecard, Path]:
    """The stored overlap run, and its scorecard file; refused unless a complete dev run."""
    file = path / SCORECARD_FILE if path.is_dir() else path
    card = read_model(file, OverlapScorecard, lambda problem: ValueError(problem))
    if card.run.split != "dev" or not card.complete:
        raise refused(
            "--overlaps is not a complete dev overlap run: a held-out run's scorecard holds no "
            "overlap's words",
            "give the scorecard of a complete dev run of `poe overlap`, such as O1's",
        )
    return card, file


def _run(args: argparse.Namespace, parts: UncertainParts) -> int:
    settings = _settings(args)
    plan = parts.plan
    checkout = run_checkout(plan.folder, plan.git)
    out = check_out(args.out, checkout, plan.git)
    if not is_name(out.name):
        raise refused(
            f"the --out folder's name, the run's, is not a name, which is {NAME_RULE}",
            "name the folder like u1-o1",
        )
    try:
        card, file = _source(args.overlaps)
    except ValueError:
        raise refused(
            "--overlaps is not an overlap run's scorecard", "give a dev run's scorecard.json"
        ) from None
    choice = Choice(split="dev", roots=audio_roots(args.audio), needs_audio=True)
    recorded = {each.variant.id: each for each in load_plan(checkout.top / DATA, choice, plan).todo}
    again = asyncio.run(rejudged(card, recorded, parts.audio_call, settings))
    overlaps = uncertain_overlaps(card.model_copy(update={"variants": tuple(again.results)}))
    if not overlaps:
        raise refused("--overlaps holds no overlap the rule left uncertain", "give O1's or O2's")
    todo = [(each, request_of(each, settings, args.temperature)) for each in overlaps]
    cached = args.price_input if args.price_cached is None else args.price_cached
    prices = Prices(input_usd=args.price_input, cached_usd=cached, output_usd=args.price_output)
    sent = [todo[0], *(() if args.smoke_only else todo)]  # the smoke test's, then each
    if (most := sum(prices.budget(request) for _, request in sent)) > args.cap_usd:
        raise refused(
            f"the run's budget, ${most:.4f} at most, passes --cap-usd",
            "raise --cap-usd, or check the prices and --max-output-tokens",
        )
    if len(sent) > args.day_requests:
        raise refused(
            f"the run sends {len(sent)} requests at least, more than --day-requests",
            "run it on a day with room, or give the requests the key may still send",
        )
    info = UncertainRun(
        name=out.name,
        started_at=plan.now(),
        commit=checkout.commit,
        source=card.run.name,
        source_commit=card.run.commit,
        data_digest=sha256_file(file),
        rejudged=len(card.variants),
        unmatched=again.unmatched,
        model=settings.llm.model,
        settings=shown(settings, args),
        price_input_usd=args.price_input,
        price_output_usd=args.price_output,
        price_cached_usd=cached,
        cap_usd=args.cap_usd,
        rpm=args.rpm,
        day_requests=args.day_requests,
        note=args.note,
    )
    asking = Asking(
        model=parts.chat_model(settings),
        pacer=MinutePacer(args.rpm, plan.clock, plan.sleep),
        prices=prices,
        cap_usd=args.cap_usd,
        day_requests=args.day_requests,
        max_attempts=args.max_attempts,
        item_timeout_s=args.item_timeout_s,
        clock=plan.clock,
        sleep=plan.sleep,
    )
    out.mkdir(parents=True)
    found = Found()
    log.info("run_started", run=info.name, source=info.source, overlaps=len(todo))
    try:
        asyncio.run(asked(asking, todo, found, out, args.smoke_only))
    except KeyboardInterrupt:
        found.stopped = "interrupted"
        log.warning("run_interrupted", done=len(found.results), of=len(todo))
    expected = 0 if args.smoke_only else len(todo)
    complete = found.stopped is None and len(found.results) == expected
    return close_run(info, found, complete, asking, out, checkout.top / DATA, parts.append_line)


def main(argv: Sequence[str] | None = None, *, parts: UncertainParts | None = None) -> int:
    """`uv run poe uncertain`: run U on a stored overlap run. 0 when the run is complete, 1 when
    it is not (a failed smoke test, the cap, the day's limit, a request still rate-limited, an
    interrupt), 2 when it is refused before anything is sent."""
    parser = _parser()
    args = parser.parse_args(argv)
    _require(parser, args)
    configure_logging(loggers=LOGGERS)
    try:
        return _run(args, UncertainParts() if parts is None else parts)
    except T2VoiceError as error:
        log.error("uncertain_refused", code=error.code, message=error.message)
        return 2


if __name__ == "__main__":
    sys.exit(main())

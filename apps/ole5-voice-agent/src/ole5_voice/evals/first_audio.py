"""`poe first-audio`: run T, the time to first audio (plan 006's registration), into a new
folder, `--out`, as evaluation.md's "Running" says: the recorded requests (`n01` to `n28`, the
knowledge set's `RECORDED`) of one split replayed, each as a fresh call of the agent with the
real speech-to-text, chat model, knowledge and voice (first_audio_run.py), and scored by path
(first_audio_score.py, first_audio_card.py).

**The arms** are the command line's: `--trim-silence off` (T0) or `on` (T1), `--no-tools`
(Tn: no reply searches), and `--clause-cache on` (run I's I1, plan 007: `tts.cache_clauses` on,
the clause cache new in the run's folder, `<out>/clauses`, over the replay's counting voice,
first_audio_cache.py; a dev run only). **The agent and its knowledge base** come from
factories, as runs K's and S's do (factories.py): `--agent`, given the knowledge base, gives a
`VoiceAgent` with instructions (the talker's: Ole5's `ole5_voice.agent:talker_agent`), and
`--knowledge`, given the run's env file, its knowledge base (Ole5's
`ole5_voice.knowledge_base:knowledge_base`); with `--no-tools` the agent's factory is given None,
as Ole5's then gives its talker with no tool, and no knowledge base is built. Each is closed when
the run ends, a refusal's included.

As `poe eval-timing`, a run refuses the main checkout and a dirty tree, an `--out` that exists or
that git would track, and audio that is not the file its manifest hashed; its settings load as
`poe eval`'s, the speech and chat models', `tts.trim_silence` and `tts.cache_clauses` from their
flags and each `--set` on top, untraced; it names a price for every model it calls, and refuses
a run whose budget, every recording and the smoke test at their most, would pass `--cap-usd`,
all before anything is sent. It declares the agent's fixed phrases, then plays the smoke test,
the first dev recording, which must answer one turn, its reply heard, with no failure on its
first call, after which the clause cache, when the run has one, is emptied, so the first
recording measured starts cold; then each recording, a dev run's result written as it finishes
(`results.jsonl`) with a progress line of identifiers and times, never a text, and its replies'
openings kept for the owner's listen (`poe first-audio-listen`); a held-out run's lines are
counts, the library's lines but its errors held back, and its scorecard aggregates only. The
scorecard is written whole at the end, whatever ended the run once it started (an error's
`stopped` is `error`), and its history line appended to the worktree's `history.jsonl` and copied
beside it, every request counted.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Final, get_args

from t2_agentic_voice import (
    ProviderError,
    get_logger,
)

from ole5_voice.evals import run_settings
from ole5_voice.evals.cli import EFFORTS, amount, count, missing, model_price, require, seconds
from ole5_voice.evals.factories import Closing
from ole5_voice.evals.first_audio_cache import CLAUSES_DIR
from ole5_voice.evals.first_audio_card import AudioRun, Stopped, close_run
from ole5_voice.evals.first_audio_run import (
    LEAD_S,
    REPLIES_DIR,
    CapReachedError,
    DayLimitError,
    Measuring,
    speaks,
    tail_of,
)
from ole5_voice.evals.first_audio_score import AudioResult
from ole5_voice.evals.first_audio_setup import (
    NEEDED,
    FirstAudioParts,
    agent_of,
    prices_of,
    recorded,
    seconds_of,
    settings_of,
    shown,
    voice_of,
)
from ole5_voice.evals.models import NAME_RULE, Split, is_name
from ole5_voice.evals.overlap_plan import setting
from ole5_voice.evals.pacers import MinutePacer
from ole5_voice.evals.run_parts import DATA, Todo
from ole5_voice.evals.session_runner import closed, main_of, measured
from ole5_voice.evals.timing_run import TAGS
from ole5_voice.evals.worktree import check_out, refused, run_checkout

STT_RPM: Final = 10  # Whisper requests a minute: half the published 20 (plan 003's T)
TTS_RPM: Final = 5  # requests a minute to each voice (the golden set's timing runs')
LLM_RPM: Final = 20  # chat requests a minute (the agent's: under the key's limit)
RESULTS_FILE: Final = "results.jsonl"
_DESCRIPTION = "Run T: the time to first audio of the agent's replies to the recorded requests."
log = get_logger(__name__)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="poe first-audio", description=_DESCRIPTION)
    add = parser.add_argument
    add("--split", choices=get_args(Split), help="the split the run covers, all of it")
    add("--agent", help="the agent's factory, ole5_voice.<module>:<name>, given the base")
    add("--knowledge", help="the knowledge base's factory, given --env-file (not with Tn)")
    add("--no-tools", action="store_true", help="the agent given no knowledge base (Tn)")
    add("--trim-silence", choices=("on", "off"), help="tts.trim_silence: on (T1) or off (T0)")
    add("--clause-cache", choices=("on", "off"), default="off", help="tts.cache_clauses (I1)")
    add("--model", choices=run_settings.MODELS, help="stt.model")
    add("--timeout-s", type=seconds, help="stt.timeout_s")
    add("--llm-model", help="llm.model")
    add("--llm-reasoning-effort", choices=EFFORTS, help="llm.reasoning_effort")
    add("--llm-max-output-tokens", type=count, help="llm.max_output_tokens")
    add("--llm-timeout-s", type=seconds, help="llm.timeout_s")
    add("--llm-input-tokens", type=count, help="the most one model request reads, budgeted")
    add("--base-url", help=f"groq.base_url for this run ({run_settings.GROQ_BASE_URL})")
    add("--env-file", type=Path, help="the .env file the settings load from (never printed)")
    add("--var-dir", type=Path, help="the settings' var_dir, which holds the phrase cache")
    add("--audio", action="append", default=[], metavar="ROOT=FOLDER", help="an audio root")
    add("--set", type=setting, action="append", default=[], metavar="GROUP.NAME=VALUE")
    add("--price-per-hour", type=amount, help="USD an hour of Whisper's billed audio")
    add("--tts-price", type=model_price, action="append", default=[], metavar="MODEL=USD")
    add("--llm-price-input", type=amount, help="USD per million tokens the chat model reads")
    add("--llm-price-cached", type=amount, help="USD per million cached tokens (the input's)")
    add("--llm-price-output", type=amount, help="USD per million tokens it writes")
    add("--cap-usd", type=amount, help="the most the run may spend")
    add("--stt-rpm", type=count, default=STT_RPM, help=f"Whisper requests a minute ({STT_RPM})")
    add("--tts-rpm", type=count, default=TTS_RPM, help=f"each voice's ({TTS_RPM})")
    add("--llm-rpm", type=count, default=LLM_RPM, help=f"the chat model's ({LLM_RPM})")
    add("--out", type=Path, help="a new folder, outside the worktree, that git ignores")
    add("--note", help="why the run is made")
    add("--smoke-only", action="store_true", help="run the smoke test alone")
    return parser


def _require(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    require(parser, args, NEEDED)
    if args.no_tools and args.knowledge is not None:
        parser.error("--no-tools builds no knowledge base: no --knowledge")
    if not args.no_tools and missing(args.knowledge):
        parser.error("a run needs --knowledge, or --no-tools for Tn")


async def _measure(
    measuring: Measuring,
    smoke: Todo,
    todo: Sequence[Todo],
    found: list[AudioResult],
    args: argparse.Namespace,
    out: Path,
) -> Stopped | None:
    """The phrases, the smoke test, then each recording, until the last, the cap or a model's
    day; why it stopped early, if it did."""
    held_out = args.split == "held-out"
    try:
        try:  # the progress lines the replay says at its start, then the phrase cache
            await measuring.replay.start()
            await measuring.declare()
        except ProviderError as error:
            log.error("phrases_failed", kind=error.kind)
            return "phrases_failed"
        tried = await measuring.variant(smoke, "dev")
        heard = None if tried.timed is None else tried.timed.ttfa_ms  # its reply's audio came
        if tried.failure is not None or heard is None or tried.attempts > 1:
            log.error("smoke_failed", failure=tried.failure, turns=len(tried.turns))
            return "smoke_failed"
        log.info("smoke_passed", ttfa_ms=heard)
        await measuring.replay.clear()  # the clause cache, if any, cold for the first measured
        for each in () if args.smoke_only else todo:
            result = await measuring.variant(each, args.split)
            found.append(result)
            if held_out:
                log.info("progress", done=len(found), of=len(todo))
                continue
            with (out / RESULTS_FILE).open("a", encoding="utf-8", newline="\n") as file:
                file.write(result.model_dump_json() + "\n")
            timed = result.timed
            log.info(
                "variant_done",
                done=len(found),
                of=len(todo),
                item=result.item,
                variant=result.variant,
                attempts=result.attempts,
                cut=result.cut,
                failure=result.failure,
                searched=None if timed is None else timed.searched,
                ttfa_ms=None if timed is None or timed.ttfa_ms is None else round(timed.ttfa_ms),
            )
    except CapReachedError:
        log.warning("cap_reached", done=len(found), of=len(todo))
        return "cap"
    except DayLimitError:
        log.warning("day_limit_reached", done=len(found), of=len(todo))
        return "day_limit"
    finally:
        await measuring.aclose()
    return None


def _run(args: argparse.Namespace, parts: FirstAudioParts) -> int:
    return closed(lambda closing: _built(args, parts, closing))


def _built(args: argparse.Namespace, parts: FirstAudioParts, closing: Closing) -> int:
    settings = settings_of(args)
    if settings.tts.cache_clauses and args.split == "held-out":
        raise refused(
            "the clause cache (--clause-cache on) runs on dev only: run I runs no held-out",
            "give --split dev, or leave the clause cache off",
        )
    plan = parts.plan
    checkout = run_checkout(plan.folder, plan.git)
    out = check_out(args.out, checkout, plan.git)
    if not is_name(out.name):
        raise refused(
            f"the --out folder's name, the run's, is not a name, which is {NAME_RULE}",
            "name the folder like t1",
        )
    data = checkout.top / DATA
    digest, todo = recorded(data, args.split, args, plan)
    dev = todo if args.split == "dev" else recorded(data, "dev", args, plan)[1]
    if not todo or not dev:
        raise refused(
            "the split holds no recorded request the owner has checked, or dev none for the "
            "smoke test",
            "check --split and the committed split",
        )
    agent = agent_of(args, parts.load_factory, closing)
    languages = {t.item.language for t in [*todo, dev[0]]}
    if unspoken := sorted({TAGS[each] for each in languages if not speaks(agent, each)}):
        raise refused(f"the agent speaks no {', '.join(unspoken)}", "give the Ole5 agent")
    voices = sorted({settings.tts.languages[language.tag].model for language in agent.languages})
    prices = prices_of(args, settings, voices)
    played = [dev[0], *(() if args.smoke_only else todo)]
    most = sum(prices.budget(seconds_of(t), voice_of(settings, agent, t)) for t in played)
    if most > args.cap_usd:
        raise refused(
            f"the run's budget, ${most:.2f} at most, passes --cap-usd",
            "raise --cap-usd, or check the prices and --llm-input-tokens",
        )
    stt = closing.add(parts.speech_to_text(settings))
    tts = closing.add(parts.text_to_speech(settings))
    llm, tail_s = closing.add(parts.chat_model(settings)), tail_of(settings, agent)
    phrases = parts.phrases(settings, tts, agent)
    clauses = out / CLAUSES_DIR if settings.tts.cache_clauses else None
    replay = parts.replay(
        agent=agent, settings=settings, stt=stt, tts=tts, llm=llm, phrases=phrases, clauses=clauses
    )
    info = AudioRun(
        name=out.name,
        started_at=plan.now(),
        commit=checkout.commit,
        split=args.split,
        agent=args.agent,
        tools=not args.no_tools,
        clause_cache=clauses is not None,
        settings=shown(settings, args, tail_s),
        data_digest=digest,
        lead_s=LEAD_S,
        tail_s=tail_s,
        price_per_hour_usd=args.price_per_hour,
        tts_price_per_million_usd=dict(prices.per_million_chars_usd),
        chat_price_per_million_usd={
            "input": prices.chat_input_usd,
            "cached": prices.chat_cached_usd,
            "output": prices.chat_output_usd,
        },
        cap_usd=args.cap_usd,
        note=args.note,
    )
    clock, sleep = plan.clock, plan.sleep
    pacers: dict[str, MinutePacer] = {settings.stt.model: MinutePacer(args.stt_rpm, clock, sleep)}
    pacers |= {model: MinutePacer(args.tts_rpm, clock, sleep) for model in voices}
    pacers |= {settings.llm.model: MinutePacer(args.llm_rpm, clock, sleep)}
    held_out = args.split == "held-out"
    measuring = Measuring(
        agent=agent,
        settings=settings,
        replay=replay,
        phrases=phrases,
        pacers=pacers,
        prices=prices,
        sleep=sleep,
        replies=None if held_out else out / REPLIES_DIR,
        tail_s=tail_s,
        adapters=(closing,),  # the speech, voice, chat and knowledge adapters
    )
    out.mkdir(parents=True)
    found: list[AudioResult] = []
    log.info("run_started", run=info.name, split=info.split, variants=len(todo))
    stopped: Stopped | None = "error"  # until the measuring returns why it stopped
    total = 0 if args.smoke_only else len(todo)
    try:  # requests were spent: the card and line written whatever ends it
        running = _measure(measuring, dev[0], todo, found, args, out)
        stopped = measured(running, done=lambda: len(found), of=len(todo))
    finally:
        ended = close_run(info, found, stopped, total, measuring, out, data, parts.append_line)
    return ended


def main(argv: Sequence[str] | None = None, *, parts: FirstAudioParts | None = None) -> int:
    """`uv run poe first-audio`: run T over one split's recorded requests. 0 when the run is
    complete, 1 when it is not (the phrase cache, a failed smoke test, the cap, a model's day,
    an interrupt, a library error once it started), 2 when it is refused before anything is
    sent."""
    found = FirstAudioParts() if parts is None else parts
    return main_of(_parser(), argv, _require, lambda args: _run(args, found), "first_audio_refused")


if __name__ == "__main__":
    sys.exit(main())

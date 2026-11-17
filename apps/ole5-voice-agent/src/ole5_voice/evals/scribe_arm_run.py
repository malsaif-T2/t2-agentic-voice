"""A pass of one of run H's Scribe arms (D-115, D-117): `poe eval-languages --scribe-arm ARM`,
with `--split dev`, `--out`, `--note`, `--price-per-hour` and `--cap-usd`, and `--estimate-only`,
`--smoke-only`, `--audio`, `--env-file` and `--var-dir` as a pass takes them (languages_run.py;
the arms are scribe_arms.py's, the scorecard scribe_arm_card.py's). `detected` and `single` also
take `--language-from`, their gate's offline detected pass (scribe_arm_gate.py), alone. It spends.

The settings load as a pass's do (`run_settings.env_settings`), `stt.provider` set to elevenlabs
on top, so the adapter is the library's Scribe v3 (`Providers.speech_to_text`). A request naming
a language carries that language's prompt, as a live call builds it (`stt.send_prompt`; Ole5's
vocabulary, then `words.vocabulary`, then the language's command words, the `languages`
facade's `whisper_prompt`), which Scribe takes as keyterms. The pass records the provider, its
model, `stt.timeout_s`, `stt.send_prompt`, `stt.switch_min_probability`, the `elevenlabs` group
(a key only as set or not), the arm, the price and the gate of `detected` or `single` (`shown`).

Before any clip is sent, the pass refuses what every pass refuses (the main checkout, a dirty
tree, an `--out` that exists or that git would track, a name that is no name, audio that is not
its manifest's) and a gate it cannot read, then logs its dry estimate (`run_estimate`: each
variant's whole clip once per request of the arm, billed by its seconds, and the cost) and is
refused past `--cap-usd`;
`--estimate-only` stops there, building no adapter, so it needs no key, and making no folder.

The requests go one at a time, each timed from its send to its answer on the run's clock, a
failure kept by its kind and never asked again. ElevenLabs limits speech-to-text by requests at
once, not by requests a minute (its help centre, read 2026-11-17), so none is paced. Each
variant's answers are written as a line of `ARM_TURNS_FILE` as it finishes, with a progress line
of identifiers and counts, never a word heard; the scorecard is written whole at the end. An arm's
pass appends no line to the run history.
"""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Final, Literal

from t2_agentic_voice import ProviderError, Providers, VoiceSettings, get_logger
from t2_agentic_voice.evals import RunClock, check_out, run_checkout, run_refused
from t2_agentic_voice.languages import whisper_prompt
from t2_agentic_voice.ports import AudioClip, SpeechToText

from ole5_voice.agent import VOCABULARY
from ole5_voice.evals import run_settings
from ole5_voice.evals.cli import require
from ole5_voice.evals.models import NAME_RULE, is_name
from ole5_voice.evals.run_parts import DATA, Choice, Parts, Todo, audio_roots, clip_of, load_plan
from ole5_voice.evals.runs import cost_usd
from ole5_voice.evals.scribe_arm_card import ArmRun, scorecard_of, write_arm_pass
from ole5_voice.evals.scribe_arm_gate import Gate, detect_gate
from ole5_voice.evals.scribe_arms import (
    ARM_NAMES,
    ARM_TURNS_FILE,
    CALL_CODES,
    GATED,
    ArmAnswer,
    ArmName,
    ArmResult,
    Ask,
    distinct_asks,
)
from ole5_voice.evals.stt_arms import recorded_model

PROVIDER: Final = "elevenlabs"
log = get_logger(__name__)
MakeStt = Callable[[VoiceSettings], SpeechToText]


def arm_flags(parser: argparse.ArgumentParser) -> None:
    """`poe eval-languages`' flags of an arm's pass."""
    add = parser.add_argument
    add("--scribe-arm", choices=ARM_NAMES, help="a pass of one of run H's Scribe arms (spends)")
    add("--language-from", type=Path, help="the gate of detected and single: a detected pass")


def require_arm(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    """Refused by `poe eval-languages`' parser (exit 2): an arm's pass lacking a flag it needs,
    with a classifier's flag or `--read`, or of the held-out split; `--language-from` other than
    with `--scribe-arm detected` or `single`, which need it."""
    if (args.scribe_arm in GATED) != (args.language_from is not None):
        parser.error("--language-from, the gate, serves --scribe-arm detected or single alone")
    require(parser, args, ("split", "out", "note", "price_per_hour", "cap_usd"), noun="pass")
    if args.read or args.classifier or args.classifier_dir:
        parser.error(
            "--scribe-arm is a pass of its own: no --classifier, --classifier-dir or --read"
        )
    if args.split != "dev":
        parser.error("a Scribe arm's pass keeps every variant's words: --split dev only")


def arm_settings(args: argparse.Namespace) -> VoiceSettings:
    """The pass's settings (the module's docstring)."""
    loaded = run_settings.env_settings(args)
    stt = loaded.stt.model_copy(update={"provider": PROVIDER})
    return loaded.model_copy(update={"stt": stt})


def arm_prompts(settings: VoiceSettings) -> dict[str, str]:
    """Each call language's prompt, as a live call builds it; none with `stt.send_prompt` off."""
    if not settings.stt.send_prompt:
        return {}
    terms = (*VOCABULARY.terms, *settings.words.vocabulary)
    found = {code: whisper_prompt(terms, code).text for code in CALL_CODES}
    return {code: text for code, text in found.items() if text}


def shown(settings: VoiceSettings, args: argparse.Namespace, gate: str) -> dict[str, str]:
    """What the pass's answers depend on, by dotted name (the module's docstring); `gate`, that
    of `detected` or `single` (`Gate.shown`), or none."""
    stt = settings.stt
    return {
        "env": settings.env,
        "stt.provider": stt.provider,
        "stt.model": recorded_model(settings, PROVIDER),
        "stt.timeout_s": str(stt.timeout_s),
        "stt.send_prompt": str(stt.send_prompt).lower(),
        "stt.switch_min_probability": str(stt.switch_min_probability),
        "words.vocabulary": str(len(settings.words.vocabulary)),
        **run_settings.group_shown(settings, PROVIDER),
        "run.scribe_arm": args.scribe_arm,
        "run.price_per_hour": str(args.price_per_hour),
        "run.smoke_only": str(args.smoke_only).lower(),
        "run.language_from": gate,
    }


def check_arm_cost(
    arm: ArmName,
    seconds: Sequence[float],
    detects: Sequence[bool | None],
    *,
    price_per_hour_usd: float,
    cap_usd: float,
    estimate_only: bool,
) -> Literal["estimated", "within"]:
    """Log the pass's dry estimate of the variants of `seconds`, each gated by `detects` (None:
    no gate), then refuse it past `cap_usd` (the module's docstring); `estimated` for
    `--estimate-only`, so nothing is sent; else `within`."""
    asked = [len(distinct_asks(arm, detects=each is not False)) for each in detects]
    billed = sum(s * n for s, n in zip(seconds, asked, strict=True))
    usd = cost_usd(billed, price_per_hour_usd)
    log.info(
        "run_estimate",
        provider=PROVIDER,
        arm=arm,
        variants=len(seconds),
        requests=sum(asked),
        billed_s=round(billed, 1),
        usd=round(usd, 4),
        cap_usd=cap_usd,
    )
    if usd > cap_usd:
        raise run_refused(
            f"the pass's cost, ${usd:.4f}, passes --cap-usd",
            "raise --cap-usd, or check --price-per-hour",
        )
    return "estimated" if estimate_only else "within"


async def answer_of(
    stt: SpeechToText, clip: AudioClip, ask: Ask, prompts: Mapping[str, str], clock: RunClock
) -> ArmAnswer:
    """One request shaped `ask` of `clip`, timed; its failure kept by its kind."""
    sent = AudioClip(pcm16=clip.pcm16, sample_rate=clip.sample_rate, other_languages=ask.others)
    prompt = None if ask.prompt is None else prompts.get(ask.prompt)
    started = clock()
    try:
        heard = await stt.transcribe(sent, language=ask.named, prompt=prompt)
    except ProviderError as error:
        took = clock() - started
        return ArmAnswer(ask=ask, seconds=took, billed_seconds=clip.seconds, failure=error.kind)
    took = clock() - started
    billed = clip.seconds if heard.billed_seconds is None else heard.billed_seconds
    return ArmAnswer(
        ask=ask,
        text=heard.text,
        language=heard.language,
        heard=heard.heard_language,
        probability=heard.language_probability,
        seconds=took,
        billed_seconds=billed,
    )


async def _sent(
    arm: ArmName,
    todo: Sequence[Todo],
    gate: Gate | None,
    stt: SpeechToText,
    prompts: Mapping[str, str],
    clock: RunClock,
    turns_file: Path,
    results: list[ArmResult],
) -> None:
    """Each variant's requests, one at a time, shaped by the `gate` under `detected` or
    `single`, its answers kept as it finishes; the adapter closed at the end."""
    try:
        for each in todo:
            clip, detects = clip_of(each), None if gate is None else gate.of(each)
            shaped = distinct_asks(arm, detects=detects is not False)
            answers = [await answer_of(stt, clip, ask, prompts, clock) for ask in shaped]
            item, variant = each.item, each.variant
            result = ArmResult(
                item=item.id,
                variant=variant.id,
                kind=item.kind,
                language=item.language,
                device=variant.device,
                reference=variant.reference,
                answers=tuple(answers),
                detects=detects,
            )
            results.append(result)
            with turns_file.open("a", encoding="utf-8", newline="\n") as file:
                file.write(result.model_dump_json() + "\n")
            failed = sum(answer.failure is not None for answer in answers)
            log.info(
                "variant_done", done=len(results), of=len(todo), variant=variant.id, failed=failed
            )
    finally:
        await stt.aclose()


def run_arm(args: argparse.Namespace, parts: Parts, make_stt: MakeStt) -> int:
    """One arm's pass (the module's docstring): 0 when complete, 1 when interrupted; a refusal
    before any clip is sent is raised."""
    arm: ArmName = args.scribe_arm
    settings = arm_settings(args)
    checkout = run_checkout(parts.folder, parts.git)
    out = check_out(args.out, checkout, parts.git)
    if not is_name(out.name):
        raise run_refused(
            f"the --out folder's name, the run's, is not a name, which is {NAME_RULE}",
            "name the folder like sa-dev-hinted",
        )
    choice = Choice(split=args.split, roots=audio_roots(args.audio), needs_audio=True)
    plan = load_plan(checkout.top / DATA, choice, parts)
    todo = [plan.smoke] if args.smoke_only else list(plan.todo)
    gate = None
    if arm in GATED:
        where = {"split": args.split, "commit": checkout.commit, "digest": plan.digest}
        gate = detect_gate(args.language_from, todo, **where)
    price = args.price_per_hour
    seconds = [clip_of(each).seconds for each in todo]
    found = check_arm_cost(
        arm,
        seconds,
        [None if gate is None else gate.of(each) for each in todo],
        price_per_hour_usd=price,
        cap_usd=args.cap_usd,
        estimate_only=args.estimate_only,
    )
    if found == "estimated":
        return 0
    stt, started = make_stt(settings), parts.now()
    out.mkdir(parents=True)
    results: list[ArmResult] = []
    log.info("run_started", run=out.name, arm=arm, variants=len(todo))
    try:
        prompts = arm_prompts(settings)
        turns = out / ARM_TURNS_FILE
        asyncio.run(_sent(arm, todo, gate, stt, prompts, parts.clock, turns, results))
    except KeyboardInterrupt:
        log.warning("run_interrupted", done=len(results), of=len(todo))
    complete = len(results) == len(todo)
    answers = [answer for result in results for answer in result.answers]
    billed = sum(answer.billed_seconds for answer in answers)
    run = ArmRun(
        name=out.name,
        started_at=started,
        commit=checkout.commit,
        split=args.split,
        arm=arm,
        settings=shown(settings, args, "none" if gate is None else gate.shown(todo)),
        data_digest=plan.digest,
        min_probability=settings.stt.switch_min_probability,
        note=args.note,
        price_per_hour_usd=price,
        requests=len(answers),
        billed_seconds=billed,
        cost_usd=cost_usd(billed, price),
    )
    card = scorecard_of(run, results, complete=complete)
    write_arm_pass(out, card)
    both = card.both
    log.info(
        "run_finished",
        complete=complete,
        turns=both.turns,
        failed=both.failed,
        right=both.moves.right,
        wrong=both.moves.wrong,
        missed=both.moves.missed,
    )
    return 0 if complete else 1


def make_scribe(settings: VoiceSettings) -> SpeechToText:
    """The library's adapter of `stt.provider`, built with no IO."""
    return Providers.speech_to_text(settings)

"""Run H's H2 arms (plan 007's "Run H") as `poe eval`'s options (`run.py`): Whisper on
each variant in the language an H1 pass's rule named for it.

- **`--language-from PASS`**, a pass of `poe eval-languages` (languages_run.py) at this commit,
  on the run's split and data, with a classifier: each variant is sent whole, in the language
  the pass's rule (`evals.chosen`, the library's) named for its first turn in a call held in
  the language `--language-hint` names: `label`, the ordinary call (English items in an
  English call, the rest in an Arabic one), `ar` or `en`. A variant whose turns got different
  languages is counted and recorded; a variant with no turn goes in the call's language.
- **`--language-base RUN`**, with it on dev: the baseline of that call language (a `poe eval`
  run of the same model, prompt, commit and data, with that `--language-hint` and no arm of its
  own). Only the variants whose language the rule changed are sent; every other variant's
  answer is the baseline's, unsent (Whisper's noise on dev was d = 0 twice, D-024 and D-066), so
  `poe eval-compare BASE RUN --allow-setting run.language_from` reads the arm against it. A
  held-out arm takes no base: it sends every variant.

- **A detected pass** (`--classifier detected`) with `--language-base` on dev: detect_arm.py's
  arm, only the variants whose first turn also goes naming no language sent, naming none, each
  answer read with the library's rule against the baseline's.

The arm is recorded as `run.language_from`: the pass, its classifier, the call language, how
many variants the rule changed and how many got different languages, and the base. Each refusal
comes before anything is sent and names no variant.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Final

from t2_agentic_voice import get_logger
from t2_agentic_voice.evals import run_refused

from ole5_voice.evals import scorecard
from ole5_voice.evals.detect_arm import detected_plan
from ole5_voice.evals.languages_card import (
    CallLanguage,
    LanguageResult,
    LanguagesScorecard,
    call_code,
)
from ole5_voice.evals.languages_score import choices, first_language, load_pass
from ole5_voice.evals.models import Variant
from ole5_voice.evals.run_parts import Plan
from ole5_voice.evals.runs import Answer, Scorecard
from ole5_voice.evals.scorecard import EvalDataError

SETTING: Final = "run.language_from"  # how a run records the arm
log = get_logger(__name__)


def flag_problem(args: argparse.Namespace) -> str | None:
    """What `poe eval`'s parser refuses of the arm's flags, or None."""
    if args.language_base and not args.language_from:
        return "--language-base serves --language-from"
    if not args.language_from:
        return None
    if args.language_hint == "auto":
        return "--language-from needs --language-hint, which names the call's language"
    if args.windows_ms or args.questions:
        return "--language-from sends whole variants of a whole split: no --windows-ms, --questions"
    if args.language_base and args.split == "held-out":
        return "a held-out arm sends every variant: no --language-base"
    return None


@dataclass(frozen=True)
class LanguageArm:
    """What the arm makes of a run's plan: its plan, each request in the language the pass
    named; the answers the baseline gives for the variants not sent; what the run records
    (none without an arm); and, for a detected pass, how a sent variant's answer is read."""

    plan: Plan
    copied: Mapping[Variant, Answer] = field(default_factory=dict)
    recorded: Mapping[str, str] = field(default_factory=dict)
    merge: Callable[[Variant, Answer], Answer] | None = None


def language_arm(
    args: argparse.Namespace, plan: Plan, *, commit: str, model: str, prompt: str
) -> LanguageArm:
    """The arm `--language-from` and `--language-base` choose over `plan`, for a run at
    `commit` of `model` with the prompt it records as `prompt`; the plan as it is without one.
    The run's refusal, before anything is sent, for a pass or a base it cannot read."""
    if args.language_from is None:
        return LanguageArm(plan=plan)
    call: CallLanguage = args.language_hint
    found, results = language_pass(args.language_from, args.split, commit, plan.digest)
    by_variant = {(r.item, r.variant): r for r in results}
    if any((t.item.id, t.variant.id) not in by_variant for t in plan.todo):
        raise run_refused(
            "the --language-from pass did not feed every variant of the run",
            "give a complete pass of the run's split, at this commit",
        )
    if found.run.classifier == "detected":
        return _detected(args, plan, by_variant, found.run.name, commit, model, prompt)
    run, todo, changed, mixed = found.run, [], set(), 0
    for each in plan.todo:
        heard = by_variant[(each.item.id, each.variant.id)]
        language = first_language(heard, run, call)
        if language != call_code(call, each.item.language):
            changed.add(each.variant)
        mixed += len({c.language for c in choices(heard, run, call)}) > 1
        todo.append(replace(each, request=each.request.model_copy(update={"language": language})))
    copied: dict[Variant, Answer] = {}
    sent = "every variant sent"
    if args.language_base is not None:
        base = _base(args.language_base, args, commit=commit, model=model, prompt=prompt, plan=plan)
        answers = {r.variant: r.answer for r in base.variants}
        copied = {t.variant: answers[t.variant.id] for t in plan.todo if t.variant not in changed}
        sent = f"the rest from {base.run.name}"
    shown = (
        f"{run.name} ({run.classifier}), call {call}, {len(changed)} of {len(todo)} variants "
        f"changed, {mixed} whose turns differ, {sent}"
    )
    log.info("language_arm", run=run.name, call=call, changed=len(changed), mixed=mixed)
    return LanguageArm(replace(plan, todo=tuple(todo)), copied, {SETTING: shown})


def _detected(
    args: argparse.Namespace,
    plan: Plan,
    heard: Mapping[tuple[str, str], LanguageResult],
    name: str,
    commit: str,
    model: str,
    prompt: str,
) -> LanguageArm:
    """The arm of a detected pass (detect_arm.py), on dev against the call language's base."""
    if args.language_base is None:
        raise run_refused(
            "a detected pass's arm reads each answer against the call language's baseline",
            "give --language-base",
        )
    base = _base(args.language_base, args, commit=commit, model=model, prompt=prompt, plan=plan)
    answers = {r.variant: r.answer for r in base.variants}
    by_variant = {t.variant: answers[t.variant.id] for t in plan.todo}
    sent, arm = detected_plan(plan, heard, args.language_hint, by_variant)
    copied = {v: a for v, a in by_variant.items() if v not in arm.named}
    call = args.language_hint
    shown = (
        f"{name} (detected), call {call}, {len(arm.named)} of {len(plan.todo)} variants sent "
        f"naming no language, the rest from {base.run.name}"
    )
    log.info("language_arm", run=name, call=call, detecting=len(arm.named))
    return LanguageArm(sent, copied, {SETTING: shown}, arm.merge)


def language_pass(
    path: Path, split: str, commit: str, digest: str
) -> tuple[LanguagesScorecard, tuple[LanguageResult, ...]]:
    """The H1 pass an arm reads (`--language-from`; also the Scribe `detected` arm's gate,
    scribe_arm_gate.py), or the run's refusal."""
    try:
        found, results = load_pass(path)
    except EvalDataError as error:
        raise run_refused(f"--language-from {error.message}", "give an H1 pass's folder") from None
    problems = (
        (not found.complete, "is not complete"),
        (found.run.commit != commit, "is not at this commit"),
        (found.run.split != split, "is not of the run's split"),
        (found.run.data_digest != digest, "is not on the run's data"),
        (found.run.classifier == "off", "classifies nothing (an off pass)"),
        (found.run.classifier == "detected" and split != "dev", "is detected: dev only, yet"),
    )
    for wrong, says in problems:
        if wrong:
            raise run_refused(
                f"the --language-from pass {says}", "give a complete pass of H1, at this commit"
            )
    return found, results


def _base(
    path: Path, args: argparse.Namespace, *, commit: str, model: str, prompt: str, plan: Plan
) -> Scorecard:
    """The baseline of the arm's call language, or the run's refusal."""
    try:
        base: Scorecard | None = scorecard.load_scorecard(path)
    except EvalDataError:
        base = None
    if base is None:
        raise run_refused("--language-base is not a scorecard", "give the baseline run's folder")
    settings = base.run.settings
    same = (
        base.run.split == args.split
        and base.run.commit == commit
        and base.run.model == model
        and base.run.data_digest == plan.digest
        and settings.get("run.language_hint") == args.language_hint
        and settings.get("run.prompt", "none") == prompt
        and SETTING not in settings
        and base.complete
    )
    if not same:
        raise run_refused(
            "--language-base is not a baseline of this call language and prompt: a complete "
            "run of the same model, commit and data, with no arm of its own",
            "give the baseline run of this --language-hint",
        )
    known = {r.variant for r in base.variants}
    if any(t.variant.id not in known for t in plan.todo):
        raise run_refused(
            "--language-base does not hold every variant", "give a whole dev baseline"
        )
    return base

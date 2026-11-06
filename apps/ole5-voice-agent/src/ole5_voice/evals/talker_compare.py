"""`poe eval-talker-compare A B`: dev run B of K judged against run A (evaluation.md, "Judging a
change"; the registration's K), on stdout as Markdown.

A variant passes when the judge's verdict is its item kind's passing one (`judge.PASSING`).
Variant by variant: fixed (failing in A, passing in B), broken and the net; by item, each item's
net over its variants counts it better, worse or unchanged, and the two-sided sign test over the
items gives p (`compare.by_item`); the same by language and by kind is the stratum guard. The
noise, as registered: the variants whose verdict differs between the two runs (two runs of one
arm), and the smallest change one run can detect. A variant either run did not score (a
failure, or in one run only) is left out of both and listed. Refused: a held-out run (held-out is
read once, with the kept arm, as aggregates: its scorecard is the report), two runs whose
commits, data or splits differ or whose settings differ beyond the arms' own (`VARIED`), and a
run the owner's check marked for the owner to judge (`judge_check.marked`).
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path
from typing import Final

from t2_agentic_voice import T2VoiceError, configure_logging, evals, get_logger

from ole5_voice import LOGGERS
from ole5_voice.evals.compare import (
    ALPHA,
    ByItem,
    Change,
    ComparisonError,
    SignTest,
    by_item,
    smallest_change,
)
from ole5_voice.evals.judge_check import load_card, marked
from ole5_voice.evals.talker_score import TalkerScorecard, VariantRecord

# The settings two arms' runs may differ in: the arm and its model, the cap and the smoke-only
# switch, and every setting kept by model (its price and its limits).
VARIED: Final = ("llm.model", "run.arm", "run.cap_usd", "run.smoke_only")
VARIED_BY_MODEL: Final = ("run.price.", "run.rpm.", "run.tpm.", "run.rpd.")
_DESCRIPTION = "Compare two dev runs of K: fixed, broken and net, the sign test by item, the noise."
log = get_logger(__name__)


def loaded(path: Path) -> TalkerScorecard:
    """A dev run's scorecard, refused when the owner's check marked it for the owner."""
    card = load_card(path)
    folder = path if path.is_dir() else path.parent
    if marked(folder):
        raise ComparisonError(
            f"run {card.run.name}'s verdicts are marked for the owner to judge (more than 3 "
            "disagreements in the judge's check): the owner judges its answers first"
        )
    return card


def check_pair(a: TalkerScorecard, b: TalkerScorecard) -> None:
    """ComparisonError when A and B cannot be judged against each other."""
    if "held-out" in (a.run.split, b.run.split):
        raise ComparisonError(
            "held-out is read once, with the kept arm, as aggregates: its scorecard is the report"
        )
    found = [
        f"their {what} differ"
        for what, first, second in (
            ("commits", a.run.commit, b.run.commit),
            ("data digests", a.run.data_digest, b.run.data_digest),
        )
        if first != second
    ]
    if names := differing(a, b):
        found.append(f"their settings differ ({', '.join(names)})")
    if found:
        raise ComparisonError("the runs cannot be compared: " + "; ".join(found))


def differing(a: TalkerScorecard, b: TalkerScorecard) -> list[str]:
    """The settings A and B record differently, beyond those the arms may vary."""
    first, second = a.run.settings, b.run.settings
    return [
        name
        for name in sorted(first.keys() | second.keys())
        if first.get(name) != second.get(name)
        and name not in VARIED
        and not name.startswith(VARIED_BY_MODEL)
    ]


def paired(
    a: Iterable[VariantRecord], b: Iterable[VariantRecord]
) -> tuple[list[tuple[VariantRecord, VariantRecord]], list[str]]:
    """The variants both runs scored, as pairs, and those left out, as `item/variant: why`."""
    in_a = {(r.item, r.variant): r for r in a}
    in_b = {(r.item, r.variant): r for r in b}
    pairs, left_out = [], []
    for key in sorted(in_a.keys() | in_b.keys()):
        first, second = in_a.get(key), in_b.get(key)
        name = "/".join(key)
        if first is None or second is None:
            left_out.append(f"{name}: in {'A' if second is None else 'B'} only")
        elif first.passed is None or second.passed is None:
            failures = [
                f"{r.failure} in {s}" for s, r in (("A", first), ("B", second)) if r.failure
            ]
            left_out.append(f"{name}: {'; '.join(failures)}")
        else:
            pairs.append((first, second))
    return pairs, left_out


def changes(pairs: Sequence[tuple[VariantRecord, VariantRecord]]) -> list[Change]:
    """Each pair's change, its kind kept in `device` for the stratum guard."""
    return [
        Change(
            first.item,
            first.variant,
            first.language,
            first.kind,
            int(bool(second.passed)) - int(bool(first.passed)),
        )
        for first, second in pairs
    ]


def noisy(pairs: Sequence[tuple[VariantRecord, VariantRecord]]) -> list[str]:
    """The variants whose verdict differs between the two runs."""
    return [
        f"{first.item}/{first.variant}"
        for first, second in pairs
        if first.judged is not None
        and second.judged is not None
        and first.judged.verdict != second.judged.verdict
    ]


def report(a: TalkerScorecard, b: TalkerScorecard, *, sign_test: SignTest) -> str:
    """The Markdown report of B judged against A."""
    check_pair(a, b)
    pairs, left_out = paired(a.variants, b.variants)
    found = changes(pairs)
    whole = by_item(found, sign_test)
    changed = whole.better + whole.worse
    smallest = smallest_change(changed, whole.items, sign_test)
    unstable = noisy(pairs)
    lines = [
        f"# Run {b.run.name} ({b.run.arm}, {b.run.model}) against {a.run.name} "
        f"({a.run.arm}, {a.run.model})\n",
        f"Both at commit {a.run.commit}, on the same data. Every number describes one speaker, "
        "the owner (D-006).\n",
        "## Variant by variant\n",
        f"Compared {len(found)} variant(s) of {whole.items} item(s): {_counts(found)}",
        "Fixed: " + _names(found, 1),
        "Broken: " + _names(found, -1),
        f"Left out of both runs: {len(left_out)}.",
        *(f"- {why}" for why in left_out),
        "\n## The sign test by item\n",
        _verdict(whole),
        "\n## The noise\n",
        f"Variants whose verdict differs: {len(unstable)} of {len(pairs)}"
        + (f" ({', '.join(unstable)})." if unstable else "."),
        f"If A and B are one arm's two runs, {changed} item(s) changed, so the smallest change "
        "one run can detect is "
        + ("more than this set holds." if smallest is None else f"{smallest} item(s)."),
        "\n## The stratum guard\n",
        "| Stratum | Value | Items | Better | Worse | p |",
        "| --- | --- | --- | --- | --- | --- |",
        *_guard(found, sign_test),
        "",
    ]
    return "\n".join(lines) + "\n"


def _guard(found: Sequence[Change], sign_test: SignTest) -> list[str]:
    strata: dict[str, Callable[[Change], str]] = {
        "language": lambda change: change.language,
        "kind": lambda change: change.device,
    }
    rows = []
    for stratum, key in strata.items():
        for value in sorted({key(change) for change in found}):
            r = by_item([change for change in found if key(change) == value], sign_test)
            rows.append(f"| {stratum} | {value} | {r.items} | {r.better} | {r.worse} | {r.p:.4f} |")
    return rows


def _counts(found: Sequence[Change]) -> str:
    fixed = sum(change.delta > 0 for change in found)
    broken = sum(change.delta < 0 for change in found)
    same = len(found) - fixed - broken
    return f"fixed {fixed}, broken {broken}, net {fixed - broken:+d}; unchanged {same}."


def _names(found: Sequence[Change], delta: int) -> str:
    names = [f"{change.item}/{change.variant}" for change in found if change.delta == delta]
    return ", ".join(names) if names else "none"


def _verdict(result: ByItem) -> str:
    beyond = "beyond the noise" if result.p < ALPHA else "within the noise"
    return (
        f"Items better {result.better}, worse {result.worse}, unchanged "
        f"{result.items - result.better - result.worse}: p = {result.p:.4f}, {beyond} "
        f"(p < {ALPHA} is beyond it)."
    )


def main(argv: Sequence[str] | None = None, *, sign_test: SignTest = evals.sign_test) -> int:
    """`uv run poe eval-talker-compare A B`: compare two dev runs of K."""
    parser = argparse.ArgumentParser(prog="poe eval-talker-compare", description=_DESCRIPTION)
    parser.add_argument("baseline", type=Path, help="run A: its --out folder or its scorecard")
    parser.add_argument("candidate", type=Path, help="run B, judged against A")
    args = parser.parse_args(argv)
    configure_logging(loggers=LOGGERS)
    try:
        text = report(loaded(args.baseline), loaded(args.candidate), sign_test=sign_test)
    except T2VoiceError as error:
        log.error("comparison_not_made", code=error.code, message=error.message)
        return 1
    sys.stdout.write(text)  # the command's product, Markdown on stdout, not a log line
    return 0


if __name__ == "__main__":
    sys.exit(main())

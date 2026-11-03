"""`poe eval-compare A B`: run B judged against run A, the baseline (evaluation.md, "Judging a
change"), as the plan's registration reads its runs.

Variant by variant: fixed (wrong in A, right in B), broken (right in A, wrong in B) and the net.
By item: each item's net over its variants counts it better, worse or unchanged, and the
two-sided sign test over the items gives p (below 0.05 is beyond the noise); the same by
language and by device is the stratum guard, which marks a stratum too small to guard when even
every changed item on one side could not reach p < 0.05. For two runs of the same code (the
noise), the smallest change one run can detect. The `--focus` items are shown apart, and the
verdict is still every item's. A variant either run did not judge (an infrastructure failure, or
in one run only) is left out of both and listed. Held-out runs are compared by aggregates only,
a stratum value only where both hold it over the same number of items (`HELD_OUT_MIN_ITEMS` or
more) with no failure, and two held-out runs that cover different variants are refused. Two runs
whose recorded commits, data digests or splits differ are refused, the difference named, and so
are two whose settings differ, a setting one run records and the other lacks included
(a run before plan 003's step 7 records only the keys it used), unless the setting is one every
registered comparison may vary (`VARIED`) or the command names it with `--allow-setting NAME`,
the exception a registered comparison makes (R7 against R5 varies `run.language_hint`). The
report names variants by their IDs, never by what was said.
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from t2_agentic_voice import T2VoiceError, configure_logging, evals, get_logger

from ole5_voice import LOGGERS
from ole5_voice.evals.compare_report import aggregates, header
from ole5_voice.evals.files import read_lines
from ole5_voice.evals.runs import HELD_OUT_MIN_ITEMS, Scorecard, VariantResult
from ole5_voice.evals.scorecard import load_scorecard

ALPHA: Final = 0.05  # a p-value below it is beyond the noise
# The settings two compared runs may always differ in: the model a comparison of models
# varies, and the cap and the smoke-only switch, which change no answer a run scores.
VARIED: Final = ("stt.model", "run.cap_usd", "run.smoke_only")
SignTest = Callable[[int, int], float]
_DESCRIPTION = "Compare two runs: fixed, broken and net per variant, and the sign test by item."
_FAILURES: Final = {"provider": "a provider failure", "stuck": "stuck past its time limit"}
log = get_logger(__name__)


class ComparisonError(T2VoiceError):
    """Two runs that cannot be judged against each other, or a focus file that names no item of
    theirs."""

    code = "comparison_refused"


@dataclass(frozen=True)
class Change:
    """One variant both runs judged: `delta` is +1 fixed, -1 broken, 0 the same."""

    item: str
    variant: str
    language: str
    device: str
    delta: int


@dataclass(frozen=True)
class ByItem:
    """The sign test by item over some variants' changes."""

    items: int
    better: int
    worse: int
    p: float


def read_focus(path: Path) -> tuple[str, ...]:
    """The item IDs of a focus file: one per line; blank lines and `#` comments skipped."""
    found = read_lines(path)
    if found is None:
        raise ComparisonError(f"{path} is not a readable focus file")
    return found


def pair(a: Scorecard, b: Scorecard) -> tuple[list[Change], list[tuple[str, str]]]:
    """Every variant of either run: a `Change` when both judged it, otherwise left out of both,
    as `(item/variant, why)`."""
    in_a = {(result.item, result.variant): result for result in a.variants}
    in_b = {(result.item, result.variant): result for result in b.variants}
    changes: list[Change] = []
    left_out: list[tuple[str, str]] = []
    for key in sorted(in_a.keys() | in_b.keys()):
        first, second = in_a.get(key), in_b.get(key)
        name = "/".join(key)
        if first is None or second is None:
            left_out.append((name, "in A only" if second is None else "in B only"))
        elif failures := _failures(first, second):
            left_out.append((name, failures))
        elif first.right is None or second.right is None:
            left_out.append((name, "not judged"))
        else:
            delta = int(second.right) - int(first.right)
            changes.append(Change(*key, first.language, first.device, delta))
    return changes, left_out


def _failures(first: VariantResult, second: VariantResult) -> str:
    return "; ".join(
        f"{_FAILURES[result.answer.failure]} in {side}"
        for side, result in (("A", first), ("B", second))
        if result.answer.failure is not None
    )


def by_item(changes: Iterable[Change], sign_test: SignTest) -> ByItem:
    """Each item's net over `changes` (its variants among them), and the sign test over the
    items better and worse."""
    nets: dict[str, int] = defaultdict(int)
    for change in changes:
        nets[change.item] += change.delta
    better = sum(1 for net in nets.values() if net > 0)
    worse = sum(1 for net in nets.values() if net < 0)
    return ByItem(len(nets), better, worse, sign_test(better, worse))


def stratum_guard(
    changes: Sequence[Change], sign_test: SignTest
) -> list[tuple[str, str, ByItem, str]]:
    """By language, each item's net over its variants; by device, each item's net over its
    variants on that device only: `(stratum, value, its sign test, its reading)`."""
    strata: dict[str, Callable[[Change], str]] = {
        "language": lambda change: change.language,
        "device": lambda change: change.device,
    }
    rows: list[tuple[str, str, ByItem, str]] = []
    for stratum, key in strata.items():
        for value in sorted({key(change) for change in changes}):
            result = by_item([change for change in changes if key(change) == value], sign_test)
            rows.append((stratum, value, result, _reading(result, sign_test)))
    return rows


def _reading(result: ByItem, sign_test: SignTest) -> str:
    if sign_test(result.better + result.worse, 0) >= ALPHA:
        return "too small to guard"
    if result.p >= ALPHA or result.better == result.worse:
        return "within the noise"
    side = "worse" if result.worse > result.better else "better"
    return f"{side} in B beyond the noise"


def smallest_change(changed: int, items: int, sign_test: SignTest) -> int | None:
    """The smallest number c of items that, added on one side to the `changed` items split
    evenly (b = c + d // 2, w = d - d // 2), gives p < 0.05; None when no c up to the `items`
    the noise left unchanged does (the plan's registration, "The noise")."""
    for c in range(1, items - changed + 1):
        if sign_test(c + changed // 2, changed - changed // 2) < ALPHA:
            return c
    return None


def compare(
    a: Scorecard,
    b: Scorecard,
    *,
    sign_test: SignTest,
    focus: Sequence[str] = (),
    allowed: Sequence[str] = (),
) -> str:
    """The report of B judged against A; `ComparisonError` for two runs that differ in commit,
    data or split, or in a setting neither `VARIED` nor `allowed` names, for held-out runs that
    cover different variants or with `focus`, and for a focus item in neither run."""
    differences = [
        f"their {what} differ (A {first}, B {second})"
        for what, first, second in (
            ("commits", a.run.commit, b.run.commit),
            ("data digests", a.run.data_digest, b.run.data_digest),
            ("splits", a.run.split, b.run.split),
        )
        if first != second
    ]
    if unallowed := differing_settings(a, b, allowed):
        differences.append(
            f"their settings differ ({', '.join(unallowed)}): name each that the registered "
            "comparison varies with --allow-setting NAME"
        )
    if differences:
        raise ComparisonError("the runs cannot be compared: " + "; ".join(differences))
    held_out = a.run.split == "held-out"
    if held_out and focus:
        raise ComparisonError("held-out runs are compared by aggregates only: no --focus")
    if held_out and a.totals.variants != b.totals.variants:
        # Their difference would be the numbers of the variants one run holds and not the other.
        raise ComparisonError(
            "held-out runs that cover different variants cannot be compared "
            f"(A {a.totals.variants}, B {b.totals.variants})"
        )
    unknown = sorted(set(focus) - {result.item for result in (*a.variants, *b.variants)})
    if unknown:
        raise ComparisonError(f"--focus names {len(unknown)} item(s) in neither run")
    lines = header(a, b)
    if held_out:
        lines.append(
            "Held-out runs are compared by aggregates only: no variant, no item, and a stratum "
            "value only where both runs hold it over the same number of items, at least "
            f"{HELD_OUT_MIN_ITEMS}, with no failure.\n"
        )
    else:
        lines += _paired(*pair(a, b), focus=focus, sign_test=sign_test)
    return "\n".join(lines + aggregates(a, b)) + "\n"


def differing_settings(a: Scorecard, b: Scorecard, allowed: Sequence[str] = ()) -> list[str]:
    """The names of the settings A and B record differently, one that only one of them records
    included, other than those in `VARIED` or `allowed`, in order."""
    shown, names = (a.run.settings, b.run.settings), set(VARIED) | set(allowed)
    return [
        name
        for name in sorted(shown[0].keys() | shown[1].keys())
        if shown[0].get(name) != shown[1].get(name) and name not in names
    ]


def _paired(
    changes: list[Change],
    left_out: list[tuple[str, str]],
    *,
    focus: Sequence[str],
    sign_test: SignTest,
) -> list[str]:
    whole = by_item(changes, sign_test)
    changed = whole.better + whole.worse
    smallest = smallest_change(changed, whole.items, sign_test)
    lines = [
        "## Variant by variant\n",
        f"Compared {len(changes)} variant(s) of {whole.items} item(s): " + _counts(changes),
        "Fixed (wrong in A, right in B): " + _names(changes, 1),
        "Broken (right in A, wrong in B): " + _names(changes, -1),
        f"Left out of both runs: {len(left_out)}.",
        *(f"- {name}: {why}" for name, why in left_out),
        "\n## The sign test by item\n",
        _verdict(whole),
        f"\nIf A and B ran the same code, this is the noise: {changed} item(s) changed, so the "
        "smallest change one run can detect is "
        + ("more than this set holds." if smallest is None else f"{smallest} item(s)."),
        "\n## The stratum guard\n",
        "| Stratum | Value | Items | Better | Worse | p | Reading |",
        "| --- | --- | --- | --- | --- | --- | --- |",
        *(
            f"| {stratum} | {value} | {r.items} | {r.better} | {r.worse} | {r.p:.4f} | {reading} |"
            for stratum, value, r, reading in stratum_guard(changes, sign_test)
        ),
    ]
    if focus:
        targets = set(focus)
        aimed = [change for change in changes if change.item in targets]
        lines += [
            f"\n## Focus: {len(targets)} item(s), shown apart\n",
            "The verdict above is still every item's.",
            "Variants: " + _counts(aimed),
            "Fixed: " + _names(aimed, 1),
            "Broken: " + _names(aimed, -1),
            _verdict(by_item(aimed, sign_test)),
        ]
    return [*lines, ""]


def _counts(changes: Sequence[Change]) -> str:
    fixed = sum(1 for change in changes if change.delta > 0)
    broken = sum(1 for change in changes if change.delta < 0)
    unchanged = len(changes) - fixed - broken
    return f"fixed {fixed}, broken {broken}, net {fixed - broken:+d}; unchanged {unchanged}."


def _names(changes: Sequence[Change], delta: int) -> str:
    names = [f"{change.item}/{change.variant}" for change in changes if change.delta == delta]
    return ", ".join(names) if names else "none"


def _verdict(result: ByItem) -> str:
    unchanged = result.items - result.better - result.worse
    beyond = "beyond the noise" if result.p < ALPHA else "within the noise"
    return (
        f"Items better {result.better}, worse {result.worse}, unchanged {unchanged}: "
        f"p = {result.p:.4f}, {beyond} (p < {ALPHA} is beyond it)."
    )


def main(argv: Sequence[str] | None = None, *, sign_test: SignTest = evals.sign_test) -> int:
    """`uv run poe eval-compare`: compare two runs variant by variant."""
    parser = argparse.ArgumentParser(prog="poe eval-compare", description=_DESCRIPTION)
    parser.add_argument("baseline", type=Path, help="run A: its --out folder or its scorecard")
    parser.add_argument("candidate", type=Path, help="run B, judged against A, given the same way")
    parser.add_argument(
        "--focus",
        type=Path,
        help="a file of the items the change aims at, one item ID per line, written before B "
        "ran; shown apart",
    )
    parser.add_argument(
        "--allow-setting",
        action="append",
        default=[],
        metavar="NAME",
        help="a setting the registered comparison varies, by its dotted name; once per setting",
    )
    args = parser.parse_args(argv)
    configure_logging(loggers=LOGGERS)
    try:
        report = compare(
            load_scorecard(args.baseline),
            load_scorecard(args.candidate),
            sign_test=sign_test,
            focus=read_focus(args.focus) if args.focus else (),
            allowed=args.allow_setting,
        )
    except T2VoiceError as error:
        log.error("comparison_not_made", code=error.code, message=error.message)
        return 1
    sys.stdout.write(report)  # the command's product, Markdown on stdout, not a log line
    return 0


if __name__ == "__main__":
    sys.exit(main())

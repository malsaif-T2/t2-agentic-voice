"""`poe eval-talker-keep`: run K's keep rule, exactly as registered, on each arm's two dev runs
(`--arm k1=RUN_A,RUN_B`, once per arm), on stdout as Markdown.

"Among the arms whose first clause comes within 1.0 s at the median after the transcript, the
one with the most right answers by the sign test on items; a tie goes to the faster." The time
is the model's own (amended before any run, Q15): a reply's time to its first clause less the
time its tools ran before it, each from its start to its end (`HeardTurn.own_first_clause_s`),
so the knowledge base's search is not counted; the wall clock's, the search in it, is reported
beside it, and the report names the time the rule read. An arm's median is taken over the first
clauses of both its runs' scored variants together. Its right
answers are its passing verdicts (`judge.PASSING`), each item's counted over both runs on the
variants all four runs scored; the sign test by item (`compare.by_item`) judges the two arms, a
p of 0.05 or more being a tie, which goes to the arm with the lower median. One arm within the
time is kept as it is; none within it keeps the default. The registration compares two arms, so
three or more are refused, and so is a run that is not a complete dev run of its arm, runs of
other commits or data, and a run marked for the owner to judge (`talker_compare.loaded`). Then
held-out is run once with the kept arm.
"""

from __future__ import annotations

import argparse
import statistics
import sys
from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from t2_agentic_voice import T2VoiceError, configure_logging, evals, get_logger

from ole5_voice import LOGGERS
from ole5_voice.evals.compare import ALPHA, Change, ComparisonError, SignTest, by_item
from ole5_voice.evals.talker_compare import check_pair, loaded
from ole5_voice.evals.talker_data import HeardTurn
from ole5_voice.evals.talker_score import TalkerScorecard

FIRST_CLAUSE_S: Final = 1.0  # the registered median, at most
_READS: Final = (
    "The rule reads the model's own time to the first clause (Q15): a reply's time to it less "
    "the time its tools ran before it, so the knowledge base's search is not counted. The wall "
    "clock's time, the search in it, is shown beside it."
)
_DESCRIPTION = "Apply run K's keep rule to each arm's two dev runs."
log = get_logger(__name__)


@dataclass(frozen=True)
class Arm:
    """One arm's two dev runs, and its median first clause over both: the model's own, which
    the rule reads, and the wall clock's, reported beside it."""

    name: str
    runs: tuple[TalkerScorecard, ...]

    def _median(self, time: Callable[[HeardTurn], float | None]) -> float | None:
        found = [
            seconds
            for card in self.runs
            for r in card.variants
            if r.passed is not None and r.turn is not None and (seconds := time(r.turn)) is not None
        ]
        return statistics.median(found) if found else None

    @property
    def median_s(self) -> float | None:
        """The model's own time to the first clause, the rule's (Q15), at the median."""
        return self._median(lambda turn: turn.own_first_clause_s)

    @property
    def wall_median_s(self) -> float | None:
        """The wall clock's, the tools' time in it, at the median."""
        return self._median(lambda turn: turn.first_clause_s)


def arms(given: Sequence[str]) -> list[Arm]:
    """Each `NAME=RUN_A,RUN_B` as an arm, its runs checked."""
    found = []
    for text in given:
        name, equals, runs = text.partition("=")
        paths = [Path(path) for path in runs.split(",") if path]
        if not equals or not name or len(paths) != 2:
            raise ComparisonError(f"--arm {text} is not NAME=RUN_A,RUN_B")
        cards = tuple(loaded(path) for path in paths)
        for card in cards:
            if card.run.split != "dev" or not card.complete or card.run.arm != name:
                raise ComparisonError(
                    f"run {card.run.name} is not a complete dev run of the arm {name}"
                )
        found.append(Arm(name, cards))
    if not 1 <= len(found) <= 2:
        raise ComparisonError("the registered keep rule compares one or two arms")
    every = [card for arm in found for card in arm.runs]
    for card in every[1:]:
        check_pair(every[0], card)
    return found


def contest(a: Arm, b: Arm, sign_test: SignTest) -> tuple[int, int, float]:
    """Items better and worse in B than in A, by their passing verdicts over both runs, on the
    variants all four runs scored, and the sign test's p."""
    scored: dict[tuple[str, str], list[bool]] = defaultdict(list)
    for card in (*a.runs, *b.runs):
        for record in card.variants:
            if record.passed is not None:
                scored[(record.item, record.variant)].append(record.passed)
    changes = []
    for (item, variant), passed in scored.items():
        if len(passed) == 4:
            delta = sum(passed[2:]) - sum(passed[:2])
            changes.append(Change(item, variant, "", "", delta))
    result = by_item(changes, sign_test)
    return result.better, result.worse, result.p


def decide(found: Sequence[Arm], sign_test: SignTest) -> tuple[str | None, list[str]]:
    """The arm kept (None: the default stays), and the report's lines."""
    lines = ["# Run K's keep rule\n", _READS, ""]
    lines.append(
        "| Arm | Runs | Median first clause, the model's own (s) "
        "| Median first clause, wall clock (s) | Within 1.0 s |"
    )
    lines.append("| --- | --- | --- | --- | --- |")
    within = []
    for arm in found:
        median, wall = arm.median_s, arm.wall_median_s
        ok = median is not None and median <= FIRST_CLAUSE_S
        within += [arm] if ok else []
        runs = ", ".join(card.run.name for card in arm.runs)
        shown = " | ".join("none" if s is None else f"{s:.3f}" for s in (median, wall))
        lines.append(f"| {arm.name} | {runs} | {shown} | {'yes' if ok else 'no'} |")
    lines.append("")
    if not within:
        lines.append("No arm's first clause comes within 1.0 s at the median: the default stays.")
        return None, lines
    if len(within) == 1:
        lines.append(f"Only {within[0].name} comes within 1.0 s: it is kept.")
        return within[0].name, lines
    a, b = within
    better, worse, p = contest(a, b, sign_test)
    lines.append(
        f"Items better in {b.name} than in {a.name}: {better}, worse: {worse}, p = {p:.4f}."
    )
    if p < ALPHA and better != worse:
        kept = b if better > worse else a
        lines.append(f"Beyond the noise: {kept.name} has the most right answers, and is kept.")
        return kept.name, lines
    faster = min(within, key=lambda arm: (arm.median_s or 0.0, arm.name))
    lines.append(f"Within the noise, a tie: it goes to the faster, {faster.name}, which is kept.")
    return faster.name, lines


def main(argv: Sequence[str] | None = None, *, sign_test: SignTest = evals.sign_test) -> int:
    """`uv run poe eval-talker-keep --arm k1=A,B --arm k3=C,D`: which arm K keeps."""
    parser = argparse.ArgumentParser(prog="poe eval-talker-keep", description=_DESCRIPTION)
    parser.add_argument(
        "--arm",
        action="append",
        default=[],
        metavar="NAME=RUN_A,RUN_B",
        help="an arm's two dev runs, their --out folders or scorecards; once per arm",
    )
    args = parser.parse_args(argv)
    configure_logging(loggers=LOGGERS)
    try:
        kept, lines = decide(arms(args.arm), sign_test)
    except T2VoiceError as error:
        log.error("keep_not_decided", code=error.code, message=error.message)
        return 1
    lines.append(
        f"\nKept: {kept or 'none (the default stays)'}. Held-out is then run once with it."
    )
    sys.stdout.write("\n".join(lines) + "\n")  # the command's product, Markdown on stdout
    return 0


if __name__ == "__main__":
    sys.exit(main())

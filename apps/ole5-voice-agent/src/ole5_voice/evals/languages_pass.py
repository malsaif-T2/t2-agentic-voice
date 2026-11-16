"""What a pass of `poe eval-languages` (languages_run.py) keeps and reads: each variant's
result (`result_of`, a paused request's turn ends judged against the owner's mark), the results
so far, each written and logged as it comes (`Progress`, counts only when held out), the
scorecard and history line at the end (`close_pass`), and `--read`, condition 4 across a
commit's passes (`read_condition_4`).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path

from t2_agentic_voice import evals, get_logger

from ole5_voice.evals import history
from ole5_voice.evals.eot_score import Decision, judge
from ole5_voice.evals.languages_card import (
    PAUSED_KIND,
    LanguageResult,
    LanguagesLine,
    LanguagesRun,
)
from ole5_voice.evals.languages_score import (
    line_of,
    load_pass,
    read_passes,
    scorecard_of,
    write_pass,
)
from ole5_voice.evals.models import Split
from ole5_voice.evals.run_lines import AnyLine
from ole5_voice.evals.run_parts import DATA, Todo, marked_end
from ole5_voice.evals.worktree import refused

log = get_logger(__name__)
AppendLine = Callable[[AnyLine, Path], None]  # `history.append_line`, or a test's


def result_of(todo: Todo, side: Split, turns: tuple[evals.LanguageTurn, ...]) -> LanguageResult:
    item, variant = todo.item, todo.variant
    judged = None
    if item.kind == PAUSED_KIND:
        ends = [Decision(speech_stop_ms=t.speech_stop_ms, end_ms=t.end_ms) for t in turns]
        judged = judge(ends, marked_end(todo), labelled=True)
    return LanguageResult(
        item=item.id,
        variant=variant.id,
        split=side,
        kind=item.kind,
        language=item.language,
        device=variant.device,
        turns=turns,
        judged=judged,
    )


class Progress:
    """The results so far, each written and logged as it comes (counts only when held out)."""

    def __init__(self, total: int, turns_file: Path | None) -> None:
        self.total, self.turns_file = total, turns_file
        self.results: list[LanguageResult] = []
        self.interrupted = False

    def add(self, result: LanguageResult) -> None:
        self.results.append(result)
        done = len(self.results)
        if self.turns_file is None:
            log.info("progress", done=done, of=self.total)
            return
        with self.turns_file.open("a", encoding="utf-8", newline="\n") as file:
            file.write(result.model_dump_json() + "\n")
        heard = [turn.by or "none" for turn in result.turns]
        log.info(
            "variant_done",
            done=done,
            of=self.total,
            item=result.item,
            variant=result.variant,
            by=",".join(heard) or "none",
        )


def close_pass(
    info: LanguagesRun,
    progress: Progress,
    total: int,
    smoke_only: bool,
    out: Path,
    top: Path,
    append_line: AppendLine,
) -> int:
    """The scorecard and, for a whole pass, its history line; 0 when complete."""
    complete = not progress.interrupted and len(progress.results) == total
    held_out = info.split == "held-out"
    kept = progress.results if complete or not held_out else []
    card = scorecard_of(info, kept, complete=complete)
    write_pass(out, card, kept if complete or not held_out else None)
    if not smoke_only:
        line: LanguagesLine = line_of(card)
        history.record_line(append_line, line, top / DATA, out)
    numbers = card.card
    log.info(
        "run_finished",
        complete=complete,
        variants=numbers.variants,
        turns=numbers.turns,
        in_time=numbers.in_time,
        late=numbers.late,
        cut_offs=numbers.paused.cut_offs,
        disagreements=numbers.disagreements,
    )
    return 0 if complete else 1


def read_condition_4(folders: Sequence[Path]) -> int:
    """Condition 4 of each classifier pass of `folders` (languages_run.py's docstring), logged."""
    passes = [load_pass(folder) for folder in folders]
    try:
        readings = read_passes(passes)
    except ValueError as error:
        raise refused(
            str(error), "give the complete passes of one commit, two of them off"
        ) from None
    for reading in readings:
        log.info(
            "condition_4",
            run=reading.run,
            classifier=reading.classifier,
            cut_offs=reading.cut_offs,
            allowed=reading.allowed,
            pairs=reading.pairs,
            unpaired=reading.unpaired,
            delay_ms=None if reading.delay_ms is None else round(reading.delay_ms, 1),
            off_ms=None if reading.off_ms is None else round(reading.off_ms, 1),
            holds=reading.holds,
        )
    return 0

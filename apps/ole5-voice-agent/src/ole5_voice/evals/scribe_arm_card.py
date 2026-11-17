"""What a pass of one Scribe arm records, and its scorer (D-115, D-117; the arms and the rule read
over each answer are scribe_arms.py's, the pass scribe_arm_run.py's): the pass (`ArmRun`), its
numbers by call language and together (`ArmNumbers`), the moves at each threshold of the table
(`ThresholdRow`, `THRESHOLDS`, 0.5 to 0.95), and its scorecard (`ArmScorecard`), which holds
every variant's answers, since an arm's pass is a dev pass.

Each turn's truth is its item's: the language it is in (`EXPECTED`: English's code for an English
item; Arabic's for Saudi, MSA and mixed, which is Arabic with English terms; none for no speech)
and its kind: a question or request (`QUESTION_KINDS`), a short reply (`SHORT_KINDS`), or no
speech (`SILENT_KINDS`), the three together every kind of the strata (a test ties them). A turn
is due to move the call when its item is a question or request in the language the call is not
held in. Of the turns read at one threshold (`Moves`):

- `right`: due, and the rule moved the call to the item's language;
- `missed`: due, and the rule did not move it there;
- `wrong`: the rule moved the call where no right move was due (a short reply, a turn in the
  call's own language, no speech), and `short_false`, those of them on a short reply.

Per call language and both together (`ArmNumbers`): the turns, those whose transcript failed, the
moves at the pass's `stt.switch_min_probability` (`detected` by its own rule, which takes none),
the error of each turn's transcript against its reference by item language (WER and CER by the
`evals` scorers, pooled over the turns with a transcript; none for no speech), and the seconds to
the transcript, its median and 95th percentile. And each turn at the pass's threshold
(`TurnRecord`): the language the answer the rule read gave, its probability, whether the turn
was due to move the call and where the rule moved it, its transcript's WER against its
reference (none for no speech or a failed request), its seconds, and, under `detected` or
`single`, whether its gate sent the request naming no language (`detects`; a turn it did not
send never moves).
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import Annotated, Final, Literal, Protocol

from pydantic import Field
from t2_agentic_voice import evals

from ole5_voice.evals.files import write_json
from ole5_voice.evals.models import Commit, Language, Model, Name, Sha256, Split
from ole5_voice.evals.runs import SCORECARD_FILE, Note, Shown
from ole5_voice.evals.scorecard import quantile
from ole5_voice.evals.scribe_arms import (
    CALL_CODES,
    ArmName,
    ArmResult,
    ArmTurn,
    CallCode,
    turns_of,
)

EXPECTED: Final[dict[Language, CallCode | None]] = {
    "english": "en",
    "saudi": "ar",
    "msa": "ar",
    "mixed": "ar",
    "none": None,
}
QUESTION_KINDS: Final = frozenset(
    {"request", "paused_request", "repeat_request", "short_request", "correction", "ticket_number"}
)
SHORT_KINDS: Final = frozenset({"listening_sound", "stop_word", "confirmation"})
SILENT_KINDS: Final = frozenset({"echo_only", "noise", "silence"})
THRESHOLDS: Final = tuple(round(0.5 + 0.05 * step, 2) for step in range(10))
_Usd = Annotated[float, Field(ge=0, allow_inf_nan=False)]
_Count = Annotated[int, Field(ge=0)]
_Rate = Annotated[float, Field(ge=0, allow_inf_nan=False)]


class Scorers(Protocol):
    """The error scorers: the library's `evals` facade, or a stand-in with its signatures."""

    def wer(self, references: Sequence[str], outputs: Sequence[str]) -> float: ...

    def cer(self, references: Sequence[str], outputs: Sequence[str]) -> float: ...


class ArmRun(Model):
    """What a pass was: when, at which commit, on which split and data, under which arm, with
    which settings and threshold, and why; its price per hour of audio, its requests and what
    they billed."""

    name: Name
    started_at: datetime
    commit: Commit
    split: Split
    arm: ArmName
    settings: Shown
    data_digest: Sha256
    min_probability: float = Field(gt=0, le=1, allow_inf_nan=False)
    note: Note
    price_per_hour_usd: _Usd
    requests: _Count = 0
    billed_seconds: _Usd = 0
    cost_usd: _Usd = 0


class Moves(Model):
    """The turns due to move the call, and the rule's right, missed and wrong moves (the
    module's docstring)."""

    due: _Count
    right: _Count
    missed: _Count
    wrong: _Count
    short_false: _Count


class Errors(Model):
    """One item language's transcripts against their references."""

    turns: _Count
    wer: _Rate | None
    cer: _Rate | None


class ArmNumbers(Model):
    """One call language's numbers, or both together (the module's docstring)."""

    turns: _Count
    failed: _Count
    moves: Moves
    errors: dict[Language, Errors]
    seconds_p50: _Rate | None
    seconds_p95: _Rate | None


class TurnRecord(Model):
    """One turn at the pass's threshold (the module's docstring)."""

    item: Name
    variant: Name
    call: CallCode
    heard: str | None
    probability: float | None
    due: bool
    moved: str | None
    wer: _Rate | None
    seconds: _Rate
    detects: bool | None = None


class ThresholdRow(Model):
    """The moves of both call languages at one threshold."""

    threshold: float = Field(gt=0, le=1)
    moves: Moves


class ArmScorecard(Model):
    """A pass's scorecard: its numbers, the threshold table and every variant's answers."""

    run: ArmRun
    speakers: Literal["one speaker"] = "one speaker"  # the owner alone (D-006)
    complete: bool
    both: ArmNumbers
    calls: dict[CallCode, ArmNumbers]
    thresholds: tuple[ThresholdRow, ...]
    turns: tuple[TurnRecord, ...]
    variants: tuple[ArmResult, ...]


def is_due(turn: ArmTurn) -> bool:
    """Whether `turn` is due to move the call (the module's docstring)."""
    expected = EXPECTED[turn.result.language]
    return expected not in (None, turn.call) and turn.result.kind in QUESTION_KINDS


def moves_of(turns: Sequence[ArmTurn]) -> Moves:
    """The moves of `turns` against their items' truth (the module's docstring)."""
    due = right = wrong = short_false = 0
    for turn in turns:
        owed = is_due(turn)
        hit = owed and turn.moved == EXPECTED[turn.result.language]
        due, right = due + owed, right + hit
        if turn.moved is not None and not hit:
            wrong += 1
            short_false += turn.result.kind in SHORT_KINDS
    return Moves(due=due, right=right, missed=due - right, wrong=wrong, short_false=short_false)


def _errors(turns: Sequence[ArmTurn], scorers: Scorers) -> dict[Language, Errors]:
    groups: dict[Language, list[ArmTurn]] = defaultdict(list)
    for turn in turns:
        if EXPECTED[turn.result.language] is not None and turn.text is not None:
            groups[turn.result.language].append(turn)
    found: dict[Language, Errors] = {}
    for language, group in sorted(groups.items()):
        references = [turn.result.reference for turn in group]
        outputs = [turn.text or "" for turn in group]
        wer, cer = scorers.wer(references, outputs), scorers.cer(references, outputs)
        found[language] = Errors(turns=len(group), wer=wer, cer=cer)
    return found


def record_of(turn: ArmTurn, scorers: Scorers) -> TurnRecord:
    """`turn`'s record (the module's docstring)."""
    spoken = EXPECTED[turn.result.language] is not None and turn.text is not None
    return TurnRecord(
        item=turn.result.item,
        variant=turn.result.variant,
        call=turn.call,
        heard=turn.read.heard,
        probability=turn.read.probability,
        due=is_due(turn),
        moved=turn.moved,
        wer=scorers.wer([turn.result.reference], [turn.text or ""]) if spoken else None,
        seconds=turn.seconds,
        detects=turn.result.detects,
    )


def numbers_of(turns: Sequence[ArmTurn], scorers: Scorers) -> ArmNumbers:
    """`turns`' numbers (the module's docstring)."""
    seconds = sorted(turn.seconds for turn in turns)
    return ArmNumbers(
        turns=len(turns),
        failed=sum(turn.text is None for turn in turns),
        moves=moves_of(turns),
        errors=_errors(turns, scorers),
        seconds_p50=quantile(seconds, 0.5),
        seconds_p95=quantile(seconds, 0.95),
    )


def scorecard_of(
    run: ArmRun, results: Sequence[ArmResult], *, complete: bool, scorers: Scorers = evals
) -> ArmScorecard:
    """The pass's scorecard over `results` (the module's docstring)."""
    registered = None if run.arm == "detected" else run.min_probability
    turns = turns_of(run.arm, results, threshold=registered)
    calls = {
        call: numbers_of([turn for turn in turns if turn.call == call], scorers)
        for call in CALL_CODES
    }
    table = tuple(
        ThresholdRow(threshold=each, moves=moves_of(turns_of(run.arm, results, threshold=each)))
        for each in THRESHOLDS
    )
    return ArmScorecard(
        run=run,
        complete=complete,
        both=numbers_of(turns, scorers),
        calls=calls,
        thresholds=table,
        turns=tuple(record_of(turn, scorers) for turn in turns),
        variants=tuple(results),
    )


def write_arm_pass(out: Path, scorecard: ArmScorecard) -> None:
    """The pass's scorecard, written whole into `out`."""
    write_json(out, SCORECARD_FILE, scorecard)

"""A run's scorecard: its totals, its breakdowns by language, device, kind and split, and its
window measures, labelled one speaker (D-006), written as `out / SCORECARD_FILE`.

The numbers, as the plan's registration defines them: accuracy is the share of the variants with
a verdict that are right; WER and CER are pooled over the variants with a verdict whose reference
is not empty after normalization (errors over all their references' length, by the `evals`
scorers); term recall pools each result's `terms`, ID recall the results of the ticket kind; text
from silence is the share of the empty-reference variants with any output, and its characters;
latency is per answered request (median and 90th percentile); the cost is the billed seconds at
the run's price per hour, over the requests of the variants scored (the run's whole spend, its
smoke test's request included, is its history line's). Every rate leaves out the infrastructure
failures (evaluation.md, "Judging a change") and a run's unjudged variants, and is None where
nothing counts. No canary applies to speech-to-text, so violations are 0, with that reason. A
held-out run's scorecard holds aggregates only.
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Protocol

from pydantic import ValidationError
from t2_agentic_voice import AppError, evals
from t2_agentic_voice.evals import Recall
from t2_agentic_voice.languages import normalize_arabic, normalize_digits

from ole5_voice.evals.models import TICKET_KIND, Language
from ole5_voice.evals.runs import (
    SCORECARD_FILE,
    Metrics,
    RunInfo,
    Scorecard,
    VariantResult,
    WindowMetrics,
)

# The strata a scorecard breaks its numbers down by, each read from a variant's result.
STRATA: Final[dict[str, Callable[[VariantResult], str]]] = {
    "language": lambda result: result.language,
    "device": lambda result: result.device,
    "kind": lambda result: result.kind,
    "split": lambda result: result.split,
}
_SECONDS_PER_HOUR: Final = 3600.0
Normalize = Callable[[str], str]


class EvalDataError(AppError):
    """A run's data (its run, a result, a scorecard, a history line) fails its model's checks.
    The message names fields only, never a value, which may be a transcript or a key."""

    code = "eval_data_invalid"


class Scorers(Protocol):
    """The scorers a scorecard takes its numbers from: the library's `evals` facade, or a
    stand-in with its signatures."""

    def wer(self, references: Sequence[str], outputs: Sequence[str]) -> float: ...

    def cer(self, references: Sequence[str], outputs: Sequence[str]) -> float: ...

    def term_recall(self, reference: str, output: str, terms: Sequence[str]) -> Recall: ...

    def id_recall(self, reference: str, output: str) -> Recall: ...

    def silence_output(self, output: str) -> int: ...


def normalize_text(text: str) -> str:
    """The canonical form a reference is read in: `normalize_arabic`, then `normalize_digits`."""
    return normalize_digits(normalize_arabic(text))


def first_problem(error: ValidationError) -> str:
    """A validation error told by its fields and messages, never by the input it refused."""
    problems = error.errors(include_input=False, include_url=False)
    where = ".".join(str(part) for part in problems[0]["loc"]) or "the top level"
    return f"{len(problems)} problem(s), the first at {where}: {problems[0]['msg']}"


@dataclass(frozen=True)
class _Scored:
    """One result with the per-variant numbers its strata pool."""

    result: VariantResult
    judged: bool  # it has a verdict, so `text` is its answer
    text: str
    reference_words: int  # after normalization; 0 for an empty reference
    terms: Recall | None
    ids: Recall | None
    silence: int | None  # characters produced where nothing was said


def write_scorecard(
    run: RunInfo,
    results: Sequence[VariantResult],
    *,
    complete: bool,
    out: Path,
    scorers: Scorers = evals,
    normalize: Normalize = normalize_text,
) -> Scorecard:
    """The scorecard of `results` (a `ScorecardWriter`), also written as `out / SCORECARD_FILE`,
    which replaces an earlier one of the same run whole. The run and every result are checked
    again first, so one made with `model_copy` is refused as reading would refuse it; they are
    serialized for it with pydantic's warnings off, whose text would quote a refused value."""
    run, checked = _checked(run, results)
    scored = [_score(result, scorers, normalize) for result in checked]
    price = run.price_per_hour_usd
    scorecard = Scorecard(
        run=run,
        complete=complete,
        totals=_metrics(scored, price, scorers),
        breakdowns={
            stratum: {
                value: _metrics(group, price, scorers)
                for value, group in sorted(_groups(scored, key).items())
            }
            for stratum, key in STRATA.items()
        },
        windows=_windows(scored),
        violations=0,
        variants=() if run.split == "held-out" else tuple(checked),
    )
    _write(out, scorecard)
    return scorecard


def _checked(run: RunInfo, results: Sequence[VariantResult]) -> tuple[RunInfo, list[VariantResult]]:
    try:
        run = RunInfo.model_validate_json(run.model_dump_json(warnings=False))
        checked = [
            VariantResult.model_validate_json(r.model_dump_json(warnings=False)) for r in results
        ]
    except ValidationError as error:
        problem = first_problem(error)
    else:
        keys = [(result.item, result.variant) for result in checked]
        if any(result.split != run.split for result in checked):
            raise EvalDataError("a run's results are all of its own split")
        if len(set(keys)) != len(keys):
            raise EvalDataError("a run scores each variant once")
        return run, checked
    # Raised here, outside the handler, so no exception chain leads to the refused input.
    raise EvalDataError(f"a run or a result fails its checks: {problem}")


def _score(result: VariantResult, scorers: Scorers, normalize: Normalize) -> _Scored:
    words = len(normalize(result.reference).split())
    text = result.answer.text
    if result.right is None or text is None:
        return _Scored(result, False, "", words, None, None, None)
    return _Scored(
        result,
        judged=True,
        text=text,
        reference_words=words,
        terms=scorers.term_recall(result.reference, text, result.terms) if result.terms else None,
        ids=scorers.id_recall(result.reference, text) if result.kind == TICKET_KIND else None,
        silence=None if words else scorers.silence_output(text),
    )


def _groups(
    scored: Sequence[_Scored], key: Callable[[VariantResult], str]
) -> dict[str, list[_Scored]]:
    groups: dict[str, list[_Scored]] = defaultdict(list)
    for one in scored:
        groups[key(one.result)].append(one)
    return groups


def _metrics(group: Sequence[_Scored], price_per_hour_usd: float, scorers: Scorers) -> Metrics:
    judged = [one for one in group if one.judged]
    spoken = [one for one in judged if one.reference_words]
    references, outputs = [one.result.reference for one in spoken], [one.text for one in spoken]
    silent = [one.silence for one in judged if one.silence is not None]
    right = sum(1 for one in judged if one.result.right)
    requests = [request for one in group for request in one.result.answer.requests]
    latencies = sorted(request.latency_ms for request in requests if request.outcome == "ok")
    billed = math.fsum(request.billed_seconds for request in requests)
    return Metrics(
        variants=len(group),
        right=right,
        failures=sum(1 for one in group if one.result.answer.failure is not None),
        accuracy=right / len(judged) if judged else None,
        wer=scorers.wer(references, outputs) if spoken else None,
        cer=scorers.cer(references, outputs) if spoken else None,
        term_recall=_pooled(one.terms for one in judged),
        id_recall=_pooled(one.ids for one in judged),
        silence_share=sum(1 for chars in silent if chars) / len(silent) if silent else None,
        silence_chars=sum(silent),
        requests=len(requests),
        retries=sum(1 for request in requests if request.attempt > 1),
        latency_median_ms=quantile(latencies, 0.5),
        latency_p90_ms=quantile(latencies, 0.9),
        billed_seconds=billed,
        cost_usd=billed / _SECONDS_PER_HOUR * price_per_hour_usd,
    )


def _pooled(recalls: Iterable[Recall | None]) -> float | None:
    """Found over expected, summed before dividing; None when nothing was expected."""
    counted = [recall for recall in recalls if recall is not None]
    expected = sum(recall.expected for recall in counted)
    return sum(recall.found for recall in counted) / expected if expected else None


def quantile(ordered: Sequence[float], q: float) -> float | None:
    """The `q` quantile of `ordered` (sorted), interpolated linearly between the two closest
    ranks (Hyndman and Fan's type 7, numpy's default), so 0.5 is the median; None when empty."""
    if not ordered:
        return None
    position = q * (len(ordered) - 1)
    low = math.floor(position)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def _windows(scored: Sequence[_Scored]) -> tuple[WindowMetrics, ...]:
    """Each window length's measures over the clips of one language and `want` label, summed
    from each answered variant's windows (an infrastructure failure's are left out)."""
    sums: dict[tuple[int, Language, str | None], list[int]] = defaultdict(lambda: [0] * 8)
    for one in scored:
        if one.result.answer.failure is not None:
            continue
        for window in one.result.answer.windows:
            counts = sums[(window.ms, one.result.language, one.result.want)]
            for index, value in enumerate(
                (
                    1,
                    window.empty,
                    window.reused,
                    window.words,
                    window.leading_words,
                    one.reference_words,
                    window.holds_word is not None,
                    window.holds_word is True,
                )
            ):
                counts[index] += int(value)
    return tuple(
        WindowMetrics(
            ms=ms,
            language=language,
            want=want,
            clips=counts[0],
            empty=counts[1],
            reused=counts[2],
            words=counts[3],
            leading_words=counts[4],
            reference_words=counts[5],
            one_word_clips=counts[6],
            holds_word=counts[7],
        )
        for (ms, language, want), counts in sorted(
            sums.items(), key=lambda entry: (entry[0][0], entry[0][1], entry[0][2] or "")
        )
    )


def _write(out: Path, scorecard: Scorecard) -> None:
    """Written whole and then moved into place, so an interrupted write leaves no half file."""
    out.mkdir(parents=True, exist_ok=True)
    partial = out / f".{SCORECARD_FILE}.partial"
    partial.write_bytes((scorecard.model_dump_json(indent=2) + "\n").encode("utf-8"))
    partial.replace(out / SCORECARD_FILE)

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
held-out run's scorecard holds aggregates only: it pools each breakdown value and window group
that covers fewer than `HELD_OUT_MIN_ITEMS` answered items, and leaves out a number of a group
shown that is taken over fewer, its totals' included, though they cover every item (plan 002's
registration, "Amendments").
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Protocol

from t2_agentic_voice import T2VoiceError, evals
from t2_agentic_voice.evals import Recall

from ole5_voice.evals import matcher
from ole5_voice.evals.files import parse_json, read_text
from ole5_voice.evals.models import TICKET_KIND, Language, Other
from ole5_voice.evals.runs import (
    HELD_OUT_MIN_ITEMS,
    SCORECARD_FILE,
    Metrics,
    RunInfo,
    Scorecard,
    VariantResult,
    Window,
    WindowMetrics,
    cost_usd,
    pool_small,
)

# The strata a scorecard breaks its numbers down by, each read from a variant's result.
STRATA: Final[dict[str, Callable[[VariantResult], str]]] = {
    "language": lambda result: result.language,
    "device": lambda result: result.device,
    "kind": lambda result: result.kind,
    "split": lambda result: result.split,
}
Normalize = Callable[[str], str]


class EvalDataError(T2VoiceError):
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


def load_scorecard(path: Path) -> Scorecard:
    """The scorecard at `path` (a run's `--out` folder, or its scorecard file), read strictly,
    so a held-out scorecard holding a variant is refused as it is read: `EvalDataError`, naming
    the file and the fields only."""
    file = path / SCORECARD_FILE if path.is_dir() else path
    text = read_text(file)
    if text is None:
        raise EvalDataError(f"{file} is not a readable scorecard")
    return parse_json(
        Scorecard,
        text,
        lambda problem: EvalDataError(f"{file} is not a valid scorecard: {problem}"),
    )


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


# One clip of a window group: a result and its window of the group's length.
_Clip = tuple[_Scored, Window]


def write_scorecard(
    run: RunInfo,
    results: Sequence[VariantResult],
    *,
    complete: bool,
    out: Path,
    scorers: Scorers = evals,
    normalize: Normalize = matcher.normalize,
) -> Scorecard:
    """The scorecard of `results` (a `ScorecardWriter`), also written as `out / SCORECARD_FILE`,
    which replaces an earlier one of the same run whole. The run and every result are checked
    again first, so one made with `model_copy` is refused as reading would refuse it; they are
    serialized for it with pydantic's warnings off, whose text would quote a refused value."""
    run, checked = _checked(run, results)
    scored = [_score(result, scorers, normalize) for result in checked]
    price = run.price_per_hour_usd
    held_out = run.split == "held-out"
    # The items a held-out group, and each of its numbers, rests on at least; a dev run's 0.
    least = HELD_OUT_MIN_ITEMS if held_out else 0
    scorecard = Scorecard(
        run=run,
        complete=complete,
        totals=_metrics(scored, price, scorers, least=least),
        breakdowns={
            stratum: {
                value: _metrics(group, price, scorers, least=least)
                for value, group in _groups(scored, key, least=least).items()
            }
            for stratum, key in STRATA.items()
        },
        windows=_windows(scored, least=least),
        violations=0,
        variants=() if held_out else tuple(checked),
    )
    _write(out, scorecard)
    return scorecard


def _checked(run: RunInfo, results: Sequence[VariantResult]) -> tuple[RunInfo, list[VariantResult]]:
    def refuse(problem: str) -> EvalDataError:
        return EvalDataError(f"a run or a result fails its checks: {problem}")

    run = parse_json(RunInfo, run.model_dump_json(warnings=False), refuse)
    checked = [
        parse_json(VariantResult, r.model_dump_json(warnings=False), refuse) for r in results
    ]
    keys = [(result.item, result.variant) for result in checked]
    if any(result.split != run.split for result in checked):
        raise EvalDataError("a run's results are all of its own split")
    if len(set(keys)) != len(keys):
        raise EvalDataError("a run scores each variant once")
    return run, checked


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
    scored: Sequence[_Scored], key: Callable[[VariantResult], str], *, least: int
) -> dict[str, list[_Scored]]:
    """Each value's results, in order of value; in a held-out run, pooled by
    `runs.pool_small`."""
    groups: dict[str, list[_Scored]] = defaultdict(list)
    for one in scored:
        groups[key(one.result)].append(one)
    ordered = dict(sorted(groups.items()))
    return pool_small(ordered, _items, least) if least else ordered


def _items(group: Iterable[_Scored]) -> int:
    """The items of `group`'s answered variants: an item whose every variant failed is not
    counted, since none of the group's rates rests on it."""
    return len({one.result.item for one in group if one.result.answer.failure is None})


def _metrics(
    group: Sequence[_Scored], price_per_hour_usd: float, scorers: Scorers, *, least: int = 0
) -> Metrics:
    """`group`'s numbers. A rate taken over the variants of fewer than `least` items (in a
    held-out group: WER and CER, term and ID recall, text from silence) is left out, as None
    and no characters; accuracy is over the answered variants, whose items the group counts."""
    judged = [one for one in group if one.judged]
    spoken = _of_enough([one for one in judged if one.reference_words], least)
    references, outputs = [one.result.reference for one in spoken], [one.text for one in spoken]
    terms = _of_enough([one for one in judged if one.terms and one.terms.expected], least)
    ids = _of_enough([one for one in judged if one.ids and one.ids.expected], least)
    empty = _of_enough([one for one in judged if one.silence is not None], least)
    silent = [one.silence for one in empty if one.silence is not None]
    right = sum(1 for one in judged if one.result.right)
    requests = [request for one in group for request in one.result.answer.requests]
    latencies = sorted(request.latency_ms for request in requests if request.outcome == "ok")
    billed = math.fsum(request.billed_seconds for request in requests)
    return Metrics(
        items=_items(group),
        variants=len(group),
        right=right,
        failures=sum(1 for one in group if one.result.answer.failure is not None),
        accuracy=right / len(judged) if judged else None,
        wer=scorers.wer(references, outputs) if spoken else None,
        cer=scorers.cer(references, outputs) if spoken else None,
        term_recall=_pooled(one.terms for one in terms),
        id_recall=_pooled(one.ids for one in ids),
        silence_share=sum(1 for chars in silent if chars) / len(silent) if silent else None,
        silence_chars=sum(silent),
        requests=len(requests),
        retries=sum(1 for request in requests if request.attempt > 1),
        latency_median_ms=quantile(latencies, 0.5),
        latency_p90_ms=quantile(latencies, 0.9),
        billed_seconds=billed,
        cost_usd=cost_usd(billed, price_per_hour_usd),
    )


def _of_enough(members: list[_Scored], least: int) -> list[_Scored]:
    """`members`, or none of them when they are of fewer than `least` items."""
    return members if len({one.result.item for one in members}) >= least else []


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


def _windows(scored: Sequence[_Scored], *, least: int) -> tuple[WindowMetrics, ...]:
    """Each window length's measures over the clips of one language and `want` label, summed
    from each answered variant's windows (an infrastructure failure's are left out); in a
    held-out run, each length's groups pooled by `runs.pool_small`, and a group's one-word clips
    counted only when they are of `least` items."""
    lengths: dict[int, dict[tuple[Language, str | None], list[_Clip]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for one in scored:
        if one.result.answer.failure is not None:
            continue
        for window in one.result.answer.windows:
            lengths[window.ms][(one.result.language, one.result.want)].append((one, window))
    found: list[WindowMetrics] = []
    for ms, groups in sorted(lengths.items()):
        ordered = dict(sorted(groups.items(), key=lambda entry: (entry[0][0], entry[0][1] or "")))
        shown = pool_small(ordered, _clip_items, least) if least else ordered
        for key, clips in shown.items():
            # The pooled group's key is `OTHER`, every other group's a language and a label.
            language, want = (key, None) if isinstance(key, str) else key
            found.append(_window_metrics(ms, language, want, clips, least=least))
    return tuple(found)


def _clip_items(clips: Iterable[_Clip]) -> int:
    return len({one.result.item for one, _ in clips})


def _window_metrics(
    ms: int, language: Language | Other, want: str | None, clips: Sequence[_Clip], *, least: int
) -> WindowMetrics:
    one_word = [(one, window) for one, window in clips if window.holds_word is not None]
    if _clip_items(one_word) < least:
        one_word = []
    return WindowMetrics(
        ms=ms,
        language=language,
        want=want,
        items=_clip_items(clips),
        clips=len(clips),
        empty=sum(window.empty for _, window in clips),
        reused=sum(window.reused for _, window in clips),
        words=sum(window.words for _, window in clips),
        leading_words=sum(window.leading_words for _, window in clips),
        reference_words=sum(one.reference_words for one, _ in clips),
        one_word_clips=len(one_word),
        holds_word=sum(window.holds_word is True for _, window in one_word),
    )


def _write(out: Path, scorecard: Scorecard) -> None:
    """Written whole and then moved into place, so an interrupted write leaves no half file."""
    out.mkdir(parents=True, exist_ok=True)
    partial = out / f".{SCORECARD_FILE}.partial"
    partial.write_bytes((scorecard.model_dump_json(indent=2) + "\n").encode("utf-8"))
    partial.replace(out / SCORECARD_FILE)

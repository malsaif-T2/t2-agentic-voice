"""The scorer of `poe eval-languages` (plan 007's Block H, run H's H1): a pass's numbers, its
history line, its folder written and read back, and condition 4 of the keep rule read across the
passes; what they are shaped as is languages_card.py's.

A pass feeds every variant of a split as a fresh call and keeps each turn's record (the `evals`
facade's `LanguageTurn`, languages_run.py). From it, for each of three call languages (`CALLS`:
`label`, the ordinary call, English items in an English call and the rest in an Arabic one;
`ar`; `en`), the library's rule (`evals.chosen`) gives the language each turn goes in, as a
talker call decides it when its held request goes at the hold's start. A pass's numbers:

- how each turn's language was chosen (`by`), which is the same in every call language (`none`
  for a turn whose request never went);
- its classifications: those with a verdict in hand at the decision (`in_time`), those not
  (`late`; `never` when none came), each verdict's time from its ask (median, 90th
  percentile), and how long after the decision the late ones came (median, most);
- for each call language, the variants whose first turn the rule sent in another language than
  the call's (`changed`), by item language in a dev pass, and those whose turns got different
  languages (`mixed`), which run H's H2 counts and reports (a variant is sent whole, in its
  first turn's language);
- the paused requests' cut-offs, misses and delays, each judged as `poe eot` judges it
  (eot_score.py), against the owner's mark;
- `disagreements`: turns the rule, read back for the language the calls were held in, decides
  otherwise than the call did. It should be none: the record is checked against itself.

A held-out pass's scorecard holds aggregates only, with no breakdown by item language (the
reading of a held-out pass is its cut-offs and condition 4). Its folder still keeps every
variant's turns (`TURNS_FILE`) for run H's held-out H2 runs and condition 4 to read, never
printed, scored or shown by variant.

`read_passes` reads the passes of one commit, split and data together: against the two off
passes (no classifier), each classifier pass's paused cut-offs, at most the worse off pass's
plus one (D-067's measured noise), and the turn-end delay, the median of the paired differences
(same variant, same turn: a variant whose passes ended a different number of turns is left
unpaired) between the pass and the mean of the two off passes, which may not be both over
`DELAY_BOUND_MS` and over the off passes' own (the median of their paired differences, taken as
a size). Condition 4 holds when both hold.
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from pydantic import ValidationError
from t2_agentic_voice import evals

from ole5_voice.evals.eot_score import Decision, EotResult, Judged, metrics
from ole5_voice.evals.files import parse_json, read_lines, read_text, write_json, write_whole
from ole5_voice.evals.languages_card import (
    CALLS,
    TURNS_FILE,
    CallCard,
    CallLanguage,
    Changed,
    LanguageResult,
    LanguagesCard,
    LanguagesLine,
    LanguagesRun,
    LanguagesScorecard,
    call_code,
)
from ole5_voice.evals.runs import SCORECARD_FILE
from ole5_voice.evals.scorecard import EvalDataError, quantile

DELAY_BOUND_MS: Final = 50.0  # condition 4's bound on the median paired turn-end difference
# The `by` of a turn whose decision had a verdict in hand.
_IN_HAND: Final = frozenset({"classified", "unsure", "busy", "failed"})


def choices(
    result: LanguageResult, run: LanguagesRun, call: CallLanguage
) -> tuple[evals.LanguageChoice, ...]:
    """The language each of the variant's turns goes in, and how, in a call of `call`."""
    current = call_code(call, result.language)
    return evals.chosen(result.turns, current=current, from_s=run.from_s, min_share=run.min_share)


def first_language(result: LanguageResult, run: LanguagesRun, call: CallLanguage) -> str:
    """The language the variant's first turn goes in, in a call of `call` (the call's own when
    no turn ended): the language a variant is sent whole in (run H's H2)."""
    found = choices(result, run, call)
    language = found[0].language if found else None
    return call_code(call, result.language) if language is None else language


def _spread(values: Iterable[float]) -> tuple[float | None, float | None]:
    ordered = sorted(values)
    return quantile(ordered, 0.5), quantile(ordered, 0.9)


def _call(
    results: Sequence[LanguageResult], run: LanguagesRun, call: CallLanguage, *, held_out: bool
) -> CallCard:
    changed = [first_language(r, run, call) != call_code(call, r.language) for r in results]
    mixed = sum(len({c.language for c in choices(r, run, call)}) > 1 for r in results)
    groups: dict[str, list[tuple[LanguageResult, bool]]] = defaultdict(list)
    for result, moved in zip(results, changed, strict=True):
        groups[result.language].append((result, moved))
    by_language = (
        {}
        if held_out
        else {
            language: Changed(
                items=len({r.item for r, _ in group}),
                variants=len(group),
                changed=sum(moved for _, moved in group),
            )
            for language, group in sorted(groups.items())
        }
    )
    return CallCard(changed=sum(changed), mixed=mixed, by_language=by_language)


def card_of(
    results: Sequence[LanguageResult], *, run: LanguagesRun, held_out: bool
) -> LanguagesCard:
    """A pass's numbers over `results` (the module's docstring)."""
    by: dict[str, int] = defaultdict(int)
    in_time = late = never = disagreements = 0
    verdicts: list[float] = []
    lateness: list[float] = []
    for result in results:
        held = choices(result, run, run.held_in)
        for turn, choice in zip(result.turns, held, strict=True):
            if turn.by is None:  # no request went: nothing was named, and nothing decided
                by["none"] += 1
                continue
            by[choice.by] += 1
            if (turn.named, turn.by) != (choice.language, choice.by):
                disagreements += 1
            came, asked, decided = turn.verdict_ms, turn.asked_ms, turn.decided_ms
            if came is not None and asked is not None:
                verdicts.append(came - asked)
            if choice.by in _IN_HAND:
                in_time += 1
            elif choice.by == "late":
                late += 1
                if came is None or decided is None:
                    never += 1
                else:
                    lateness.append(came - decided)
    verdict = _spread(verdicts)
    paused = [_paused(r, r.judged) for r in results if r.judged is not None]
    return LanguagesCard(
        items=len({result.item for result in results}),
        variants=len(results),
        turns=sum(len(result.turns) for result in results),
        by=dict(sorted(by.items())),
        in_time=in_time,
        late=late,
        never=never,
        verdict_median_ms=verdict[0],
        verdict_p90_ms=verdict[1],
        late_median_ms=quantile(sorted(lateness), 0.5),
        late_max_ms=max(lateness, default=None),
        paused=metrics(paused),
        calls={call: _call(results, run, call, held_out=held_out) for call in CALLS},
        disagreements=disagreements,
    )


def _paused(result: LanguageResult, judged: Judged) -> EotResult:
    """A paused request's result, `judged`, as `poe eot` scores it."""
    ends = tuple(Decision(speech_stop_ms=t.speech_stop_ms, end_ms=t.end_ms) for t in result.turns)
    return EotResult(
        item=result.item,
        variant=result.variant,
        split=result.split,
        kind=result.kind,
        language=result.language,
        device=result.device,
        set="paused",
        ends=ends,
        judged=judged,
    )


def scorecard_of(
    run: LanguagesRun, results: Sequence[LanguageResult], *, complete: bool
) -> LanguagesScorecard:
    """A pass's scorecard: a held-out pass's with aggregates only."""
    held_out = run.split == "held-out"
    return LanguagesScorecard(
        run=run,
        complete=complete,
        card=card_of(results, run=run, held_out=held_out),
        variants=() if held_out else tuple(results),
    )


def line_of(scorecard: LanguagesScorecard) -> LanguagesLine:
    """The history line of a pass's scorecard."""
    run, card = scorecard.run, scorecard.card
    return LanguagesLine(
        time=run.started_at,
        commit=run.commit,
        run=run.name,
        classifier=run.classifier,
        settings=run.settings,
        split=run.split,
        items=card.items,
        variants=card.variants,
        turns=card.turns,
        by=card.by,
        in_time=card.in_time,
        late=card.late,
        verdict_median_ms=card.verdict_median_ms,
        late_median_ms=card.late_median_ms,
        cut_offs=card.paused.cut_offs,
        misses=card.paused.misses,
        delay_median_ms=card.paused.delay_median_ms,
        changed={call: card.calls[call].changed for call in CALLS},
        mixed={call: card.calls[call].mixed for call in CALLS},
        disagreements=card.disagreements,
        peak_mb=run.peak_mb,
        scorecard=SCORECARD_FILE,
        data_digest=run.data_digest,
        note=run.note,
        complete=scorecard.complete,
    )


def write_pass(
    out: Path, scorecard: LanguagesScorecard, results: Sequence[LanguageResult] | None
) -> None:
    """A pass's scorecard and every variant's turns (None: no turns file) into `out`, each
    written whole."""
    if results is not None:
        write_whole(out, TURNS_FILE, "".join(r.model_dump_json() + "\n" for r in results))
    write_json(out, SCORECARD_FILE, scorecard)


def load_pass(folder: Path) -> tuple[LanguagesScorecard, tuple[LanguageResult, ...]]:
    """A pass's scorecard and every variant's turns, from its folder: `EvalDataError`, naming
    the file and never its values, for one that does not read."""
    file = folder / SCORECARD_FILE
    text = read_text(file)
    if text is None:
        raise EvalDataError(f"{file} is not a readable scorecard of a pass")
    card = parse_json(
        LanguagesScorecard,
        text,
        lambda problem: EvalDataError(f"{file} is not a pass's scorecard: {problem}"),
    )
    lines = read_lines(folder / TURNS_FILE)
    if lines is None:
        raise EvalDataError(f"{folder / TURNS_FILE} is not readable")
    try:
        results = tuple(LanguageResult.model_validate_json(line) for line in lines)
    except ValidationError:
        raise EvalDataError(
            f"{folder / TURNS_FILE} holds a line that is no variant's turns"
        ) from None
    return card, results


@dataclass(frozen=True)
class Reading:
    """Condition 4 of one classifier pass (the module's docstring): its paused cut-offs and
    the most allowed; the turns paired and the variants left unpaired; the median paired
    turn-end difference against the off passes' mean (`delay_ms`) and the off passes' own
    (`off_ms`); and whether it holds (None when no turn was paired)."""

    run: str
    classifier: str
    cut_offs: int
    allowed: int
    pairs: int
    unpaired: int
    delay_ms: float | None
    off_ms: float | None
    holds: bool | None


Pass = tuple[LanguagesScorecard, Sequence[LanguageResult]]


def read_passes(passes: Sequence[Pass]) -> tuple[Reading, ...]:
    """Condition 4 of each classifier pass of `passes`, in their order, against its two off
    passes; ValueError for passes that are not of one commit, split and data, an incomplete
    one, or not exactly two off passes."""
    cards = [card for card, _ in passes]
    for field, says in (
        ("commit", "one commit"),
        ("split", "one split"),
        ("data_digest", "the same data"),
    ):
        if len({getattr(card.run, field) for card in cards}) > 1:
            raise ValueError(f"the passes read together are of {says}")
    if not all(card.complete for card in cards):
        raise ValueError("every pass read is complete")
    keyed = [{(r.item, r.variant): r for r in results} for _, results in passes]
    if len({frozenset(found) for found in keyed}) > 1:
        raise ValueError("the passes read together hold the same variants")
    off = [n for n, card in enumerate(cards) if card.run.classifier == "off"]
    if len(off) != 2:
        raise ValueError("the reading needs two off passes, exactly")
    first, second = keyed[off[0]], keyed[off[1]]
    allowed = max(cards[n].card.paused.cut_offs for n in off) + 1
    readings: list[Reading] = []
    for n, card in enumerate(cards):
        if n in off:
            continue
        diffs, own, unpaired = [], [], 0
        for key, result in keyed[n].items():
            ends = [r.turns for r in (result, first[key], second[key])]
            if len({len(t) for t in ends}) > 1:
                unpaired += 1
                continue
            for mine, one, two in zip(*ends, strict=True):
                diffs.append(mine.end_ms - (one.end_ms + two.end_ms) / 2)
                own.append(two.end_ms - one.end_ms)
        delay = statistics.median(diffs) if diffs else None
        off_ms = abs(statistics.median(own)) if own else None
        cut_offs = card.card.paused.cut_offs
        holds = None
        if delay is not None and off_ms is not None:
            slower = delay > DELAY_BOUND_MS and delay > off_ms
            holds = cut_offs <= allowed and not slower
        readings.append(
            Reading(
                run=card.run.name,
                classifier=card.run.classifier,
                cut_offs=cut_offs,
                allowed=allowed,
                pairs=len(diffs),
                unpaired=unpaired,
                delay_ms=delay,
                off_ms=off_ms,
                holds=holds,
            )
        )
    return tuple(readings)

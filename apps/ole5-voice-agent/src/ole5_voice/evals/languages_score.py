"""The scorer of `poe eval-languages` (plan 007's run H, its H1): a pass's numbers, its
history line, and its folder written and read back (condition 4 of the keep rule, read across the
passes, is languages_reading.py's); what they are shaped as is languages_card.py's.

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
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence
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
        price_per_hour_usd=run.price_per_hour_usd,
        billed_seconds=run.billed_seconds,
        cost_usd=run.cost_usd,
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

"""Run K's numbers (talker_score.py) and its history line (talker_lines.py): rates over variants
and over items, failures counted apart, the registered targets, a held-out run's aggregates
only with its small groups pooled and its rates over too few items left out, and the scorecard's
and the line's checks as they are read."""

from __future__ import annotations

from collections.abc import Sequence

import pytest
from ole5_voice.evals.talker_lines import TalkerCount, TalkerLine, talker_line
from ole5_voice.evals.talker_score import (
    PriceShown,
    Session,
    TalkerRun,
    TalkerScorecard,
    VariantRecord,
    breakdowns,
    metrics,
    rate,
    scorecard,
    targets,
)
from pydantic import ValidationError

from tests.ole5_voice.evals.samples import WHEN
from tests.ole5_voice.evals.talker_support import record


def _run(split: str = "dev") -> TalkerRun:
    return TalkerRun(
        name="k1-a",
        started_at=WHEN,
        commit="ab" * 20,
        arm="k1",
        model="openai/gpt-oss-120b",
        judge_model="llama-3.3-70b-versatile",
        split=split,  # type: ignore[arg-type]
        settings={},
        prices={"openai/gpt-oss-120b": PriceShown(input_usd=0.15, output_usd=0.6)},
        cap_usd=1.0,
        data_digest="cd" * 32,
        note="made up",
    )


def test_a_rate_is_kept_over_variants_and_over_items() -> None:
    found = [record("a", "v1"), record("a", "v2", passed=False), record("a", "v3", passed=False)]
    found += [record("b")]
    share = rate(found, lambda r: r.passed, 1)
    assert share is not None and (share.hits, share.of, share.items) == (2, 4, 2)
    assert share.rate == pytest.approx(0.5) and share.item_rate == pytest.approx((1 / 3 + 1) / 2)
    assert rate(found, lambda r: r.passed, 3) is None  # fewer than three items
    assert rate(found, lambda r: None, 1) is None


def test_the_numbers_count_failures_apart() -> None:
    found = [record("a"), record("b", failure="provider"), record("n", kind="none", passed=False)]
    totals = metrics(found)
    assert (totals.items, totals.variants, totals.failures) == (2, 3, 1)
    assert totals.answers is not None and totals.answers.of == 1
    assert totals.honest is not None and totals.honest.hits == 0
    assert totals.retrieval is not None and totals.retrieval.of == 1
    assert totals.verdicts["right"] == 1 and totals.verdicts["wrong"] == 1
    assert totals.words_median == 3.0 and totals.first_clause_median_s == 0.5
    assert totals.model_requests == 4


def test_the_targets_are_read_on_items_and_the_language_on_variants() -> None:
    passing = [record(f"a{n}") for n in range(10)] + [record("n", kind="none")]
    assert targets(metrics(passing)) == {
        "retrieval": True,
        "answers": True,
        "honest": True,
        "language": True,
        "guard": True,
    }
    found = [record(f"a{n}", hit=n > 1, passed=n > 2) for n in range(10)]
    held = targets(metrics(found))
    assert held["retrieval"] is False and held["answers"] is False and held["honest"] is None
    assert targets(metrics([]))["guard"] is None


def test_every_calls_violations_count_whatever_failed() -> None:
    failed = record("a", failure="judge").model_copy(update={"violations": 1})
    assert metrics([failed]).violations == 1


def test_a_held_out_runs_small_groups_are_pooled_and_left_out() -> None:
    found = [record(f"e{n}", split="held-out") for n in range(3)]
    found += [record("s1", language="saudi", split="held-out")]
    found += [record("m1", language="msa", split="held-out")]
    groups = breakdowns(found, held_out=True)
    assert set(groups["language"]) == {"english"}  # saudi and msa: two items, left out
    assert set(groups["kind"]) == {"answerable"}
    found += [record("x1", language="mixed", split="held-out")]
    assert set(breakdowns(found, held_out=True)["language"]) == {"english", "other"}
    small = metrics(found[:2], least=3)
    assert small.answers is None and small.words_median is None


def test_a_scorecard_holds_a_held_out_runs_aggregates_only() -> None:
    found = [record(f"e{n}", split="held-out") for n in range(3)]
    card = scorecard(_run("held-out"), found, complete=True, stopped=None, sessions=[])
    assert card.variants == () and card.totals.variants == 3
    with pytest.raises(ValidationError, match="aggregates only"):
        TalkerScorecard.model_validate(card.model_dump() | {"variants": [found[0].model_dump()]})
    small = card.model_dump()
    small["breakdowns"] = {"language": {"english": metrics(found[:1]).model_dump()}}
    with pytest.raises(ValidationError, match="groups each cover at least 3 items"):
        TalkerScorecard.model_validate(small)


def test_a_scorecard_holds_its_own_splits_variants_each_once() -> None:
    card = scorecard(_run(), [record("a")], complete=True, stopped=None, sessions=[])
    twice = card.model_dump()
    twice["variants"] = twice["variants"] * 2
    with pytest.raises(ValidationError, match="each variant once"):
        TalkerScorecard.model_validate(twice)
    other = card.model_dump()
    other["variants"][0]["split"] = "held-out"
    with pytest.raises(ValidationError, match="its own split"):
        TalkerScorecard.model_validate(other)


def test_a_record_has_a_verdict_exactly_when_nothing_failed() -> None:
    with pytest.raises(ValidationError, match="exactly when nothing failed"):
        VariantRecord.model_validate(record("a").model_dump() | {"failure": "stuck"})


def _line(found: Sequence[VariantRecord], split: str = "dev") -> TalkerLine:
    session = Session(started_at=WHEN, stopped=None, variants=len(found), cost_usd=0.01)
    card = scorecard(_run(split), found, complete=True, stopped=None, sessions=[session])
    return talker_line(card, session, 1)


def test_a_sessions_line_holds_the_scorecards_numbers() -> None:
    line = _line([record("a"), record("b", passed=False), record("n", kind="none")])
    assert line.kind == "talker" and line.items == 3 and line.answers == pytest.approx(0.5)
    assert line.breakdowns["kind"]["none"] == TalkerCount(
        items=1, variants=1, failures=0, answers=None, passed=1.0
    )
    assert line.cost_usd == 0.01 and line.session == 1 and line.complete


def test_a_held_out_line_refuses_a_small_group() -> None:
    line = _line([record(f"e{n}", split="held-out") for n in range(3)], "held-out")
    small = line.model_dump()
    small["breakdowns"]["language"]["english"]["items"] = 2
    with pytest.raises(ValidationError, match="at least 3 items"):
        TalkerLine.model_validate(small)
    more = line.model_dump()
    more["breakdowns"]["language"]["english"]["items"] = 9
    with pytest.raises(ValidationError, match="no more items than the run"):
        TalkerLine.model_validate(more)

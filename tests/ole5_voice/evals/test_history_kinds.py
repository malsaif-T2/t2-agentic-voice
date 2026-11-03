"""The run history's new kinds (run_lines.py): an end-of-turn run's line and a timing run's,
appended and read back beside `poe eval`'s, which carry no `kind`; each rendered in its own
table, with its strata and its prices, and counted in the spend; and the checks they are read
with, a held-out run's groups and a kind no line has."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from ole5_voice.evals.eot_score import EotMetrics, EotRun, EotScorecard, EotSetCard
from ole5_voice.evals.history import append_line, read_history, render_history
from ole5_voice.evals.run_lines import EotCount, EotLine, TimingLine
from ole5_voice.evals.scorecard import EvalDataError
from pydantic import ValidationError

from tests.ole5_voice.evals import samples


def eot_line(**fields: Any) -> EotLine:
    count = EotCount(items=3, variants=5, cut_offs=1, misses=0)
    base: dict[str, Any] = {
        "time": samples.WHEN,
        "commit": "0f44056",
        "run": "e1",
        "answerer": "pipeline",
        "settings": {"turns.vad_stop_ms": "200"},
        "split": "dev",
        "items": 3,
        "variants": 5,
        "cut_offs": 1,
        "misses": 0,
        "delay_median_ms": 412.5,
        "delay_p90_ms": 980.0,
        "secondary": EotCount(items=10, variants=20, cut_offs=2, misses=1),
        "breakdowns": {"language": {"saudi": count}},
        "scorecard": "scorecard.json",
        "data_digest": samples.SHA,
        "note": "E1, the baseline",
        "complete": True,
    }
    return EotLine.model_validate(base | fields)


def timing_line(**fields: Any) -> TimingLine:
    base: dict[str, Any] = {
        "time": samples.WHEN,
        "commit": "0f44056",
        "run": "t1",
        "settings": {"stt.model": "whisper-large-v3"},
        "split": "dev",
        "variants": 23,
        "cut_variants": 2,
        "failures": 0,
        "phrase_requests": 6,
        "requests": {"whisper-large-v3": 26, "canopylabs/orpheus-arabic-saudi": 22},
        "characters": {"canopylabs/orpheus-arabic-saudi": 1100},
        "billed_seconds": 260.0,
        "price_per_hour_usd": 0.111,
        "tts_price_per_million_usd": {"canopylabs/orpheus-arabic-saudi": 40.0},
        "cost_usd": 0.052,
        "medians_ms": {"whisper": 271.0, "heard_words": None},
        "scorecard": "scorecard.json",
        "data_digest": samples.SHA,
        "note": "T1",
        "complete": True,
    }
    return TimingLine.model_validate(base | fields)


def test_each_kind_is_appended_and_read_back_as_its_own(tmp_path: Path) -> None:
    path = tmp_path / "history.jsonl"
    lines = (samples.history_line("r1"), eot_line(), timing_line())
    for line in lines:
        append_line(line, path)
    assert read_history(path) == lines
    written = [json.loads(raw) for raw in path.read_text("utf-8").splitlines()]
    assert ["kind" in raw for raw in written] == [False, True, True]
    assert [raw.get("kind") for raw in written[1:]] == ["eot", "timing"]


def test_a_line_of_no_known_kind_is_refused_by_its_fields(tmp_path: Path) -> None:
    raw = json.loads(eot_line().model_dump_json()) | {"kind": "other"}
    (path := tmp_path / "history.jsonl").write_bytes(json.dumps(raw).encode() + b"\n")
    with pytest.raises(EvalDataError, match="line 1: not a history line"):
        read_history(path)


def test_a_held_out_end_of_turn_line_holds_no_small_group() -> None:
    small = {"language": {"english": EotCount(items=2, variants=4, cut_offs=0, misses=0)}}
    with pytest.raises(ValidationError, match="at least 3 items"):
        eot_line(split="held-out", breakdowns=small)
    wide = {"language": {"saudi": EotCount(items=9, variants=9, cut_offs=0, misses=0)}}
    with pytest.raises(ValidationError, match="no more items than the run"):
        eot_line(breakdowns=wide)


def test_each_kind_has_its_table_and_counts_in_the_spend() -> None:
    page = render_history([samples.history_line("r1"), eot_line(), timing_line()])
    assert "Spend so far: 3 run(s), 260.0 billed seconds, $0.0520." in page
    assert "## End-of-turn runs" in page and "## Timing runs" in page
    assert (
        "| 2 | 2026-11-03T09:00:00+00:00 | e1 | 0f44056 | pipeline | dev | 3 | 5 | 1 | 0 | 412 "
        in page
    )
    assert "| 2 of 20 | yes |" in page
    assert "canopylabs/orpheus-arabic-saudi 22, whisper-large-v3 26" in page
    assert "| Price per million characters, canopylabs/orpheus-arabic-saudi | $40 |" in page
    assert "| language | saudi | 3 | 5 | 1 | 0 |" in page
    assert "| whisper | 271 |" in page and "| heard_words | — |" in page
    assert page.count("### ") == 3
    alone = render_history([eot_line(secondary=None, delay_median_ms=None, delay_p90_ms=None)])
    assert "## Timing runs" not in alone and "| — | — | — | yes |" in alone
    assert "Price per hour" not in alone


def _card(split: str, **fields: Any) -> dict[str, Any]:
    totals = EotMetrics(items=3, variants=3, cut_offs=0, misses=0)
    run = EotRun(
        name="h1",
        started_at=samples.WHEN,
        commit="0f44056",
        answerer="pipeline",
        split=split,  # type: ignore[arg-type]
        settings={},
        data_digest=samples.SHA,
        lead_s=1.0,
        tail_s=4.5,
        note="held out",
    )
    card = EotSetCard(totals=totals, breakdowns={"language": {"saudi": totals}})
    return {"run": run, "complete": True, "paused": card} | fields


def test_a_held_out_scorecard_holds_the_paused_requests_aggregates_only() -> None:
    assert EotScorecard.model_validate(_card("held-out")).variants == ()
    card = EotSetCard(totals=EotMetrics(items=3, variants=3, cut_offs=0, misses=0), breakdowns={})
    with pytest.raises(ValidationError, match="paused requests' aggregates"):
        EotScorecard.model_validate(_card("held-out", secondary=card))
    small = EotMetrics(items=2, variants=2, cut_offs=0, misses=0)
    pooled = EotSetCard(totals=small, breakdowns={"device": {"wired": small}})
    with pytest.raises(ValidationError, match="at least 3 items"):
        EotScorecard.model_validate(_card("held-out", paused=pooled))
    assert EotScorecard.model_validate(_card("dev", paused=pooled)).paused == pooled

"""The run history's kinds of plan 006's runs (talker_lines.py, measure_lines.py): K's talker
line, S's scenario line, U's uncertain line and T's first-audio line, each appended and read back
as its own beside the older kinds, rendered in its own table with its strata, its targets and its
prices (history_measures.py), and counted in the spend; and a held-out line's groups checked."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from ole5_voice.evals.first_audio_score import PathStats, ReplyPath
from ole5_voice.evals.history import append_line, read_history, render_history
from ole5_voice.evals.measure_lines import (
    FirstAudioGroup,
    FirstAudioLine,
    UncertainCount,
    UncertainLine,
)
from ole5_voice.evals.run_folder import history_accepts, requests_today
from ole5_voice.evals.run_lines import AnyLine
from ole5_voice.evals.talker_lines import ScenarioLine, TalkerCount, TalkerLine
from ole5_voice.evals.talker_score import PriceShown
from pydantic import ValidationError

from tests.ole5_voice.evals import samples
from tests.ole5_voice.evals.test_history_kinds import timing_line

TALKER = "openai/gpt-oss-120b"
JUDGE = "llama-3.3-70b-versatile"
_BASE: dict[str, Any] = {
    "time": samples.WHEN,
    "commit": "0f44056",
    "settings": {"llm.model": TALKER},
    "scorecard": "scorecard.json",
    "data_digest": samples.SHA,
    "complete": True,
}
_PRICES = {
    TALKER: PriceShown(input_usd=0.15, output_usd=0.6),
    JUDGE: PriceShown(input_usd=0.59, output_usd=0.79),
}


def talker_line(**fields: Any) -> TalkerLine:
    count = TalkerCount(items=3, variants=6, failures=0, answers=0.75, passed=0.8)
    base = _BASE | {
        "run": "k1-dev-a",
        "arm": "k1",
        "model": TALKER,
        "judge_model": JUDGE,
        "split": "dev",
        "items": 4,
        "variants": 8,
        "failures": 1,
        "answers": 0.8125,
        "honest": 1.0,
        "retrieval": 0.9,
        "retrieval_raw": 0.85,
        "search": 1.0,
        "language": 0.875,
        "words_median": 21.0,
        "first_clause_median_s": 1.412,
        "own_first_clause_median_s": 0.734,
        "blocked": 0,
        "violations": 0,
        "targets": {"answers": True, "retrieval": True, "language": False, "guard": True},
        "breakdowns": {"language": {"saudi": count}},
        "requests": {TALKER: 20, JUDGE: 9},
        "tokens": {TALKER: 40000, JUDGE: 9000},
        "prices": _PRICES,
        "cost_usd": 0.0123,
        "session": 1,
        "stopped": None,
        "note": "K1, the first dev run",
    }
    return TalkerLine.model_validate(base | fields)


def scenario_line(**fields: Any) -> ScenarioLine:
    base = _BASE | {
        "run": "s-dev",
        "model": TALKER,
        "judge_model": JUDGE,
        "repeats": 3,
        "scenarios": 2,
        "plays": 6,
        "failures": 0,
        "passed": {"s01_password_stop_go_on": 3, "s04_mumble": 2},
        "targets_met": True,
        "violations": 0,
        "requests": {TALKER: 30, JUDGE: 12},
        "tokens": {TALKER: 50000, JUDGE: 8000},
        "prices": _PRICES,
        "cost_usd": 0.02,
        "session": 1,
        "stopped": None,
        "note": "S with K1",
    }
    return ScenarioLine.model_validate(base | fields)


def _count(right: int, listening_stops: int, **fields: Any) -> UncertainCount:
    base = {"items": 5, "variants": 9, "failed": 1, "right": right, "should_stop": 6}
    base |= {"stopped": 5, "should_go_on": 2, "false_stops": 1, "listening": 3}
    return UncertainCount.model_validate(base | {"listening_stops": listening_stops} | fields)


def uncertain_line(**fields: Any) -> UncertainLine:
    base = _BASE | {
        "run": "u1-o1",
        "source": "o1",
        "model": "llama-3.1-8b-instant",
        "split": "dev",
        "rule": _count(4, 1),
        "arm": _count(7, 0, answer_median_ms=212.0, unclear=1),
        "better": 3,
        "worse": 0,
        "p": 0.125,
        "targets": {"raises_right": False, "listening_no_more": True, "answers_in_time": True},
        "kept": False,
        "breakdowns": {"kind": {"listening_sound": _count(3, 0, items=3)}},
        "requests": {"llama-3.1-8b-instant": 10},
        "tokens": {"llama-3.1-8b-instant": 2000},
        "prices": {"input": 0.05, "cached": 0.05, "output": 0.08},
        "cost_usd": 0.0001,
        "note": "U1 on O1",
    }
    return UncertainLine.model_validate(base | fields)


def _paths(median: float | None, items: int = 3) -> dict[ReplyPath, PathStats]:
    stats = PathStats(turns=items, items=items, median_ms=median, p90_ms=median)
    return {"search": stats, "no_search": PathStats(turns=0, items=0)}


def first_audio_line(**fields: Any) -> FirstAudioLine:
    ends = {
        "label": FirstAudioGroup(items=3, variants=3, paths=_paths(2600.0), progress_late=0),
        "detector": FirstAudioGroup(items=4, variants=4, paths=_paths(2900.0, 4), progress_late=1),
    }
    base = _BASE | {
        "run": "t1",
        "agent": "ole5_voice.agent:talker_agent",
        "tools": True,
        "split": "dev",
        "items": 7,
        "variants": 7,
        "cut": 0,
        "failures": 0,
        "unanswered": 0,
        "no_audio": 0,
        "paths": _paths(2750.0, 7),
        "progress_lines": 2,
        "progress_median_ms": 1500.0,
        "progress_late": 1,
        "targets": {"search_median_ms": True, "no_search_median_ms": None, "progress_late": False},
        "ends": ends,
        "phrase_requests": 4,
        "requests": {"whisper-large-v3": 7, TALKER: 14},
        "characters": {"canopylabs/orpheus-arabic-saudi": 900},
        "billed_seconds": 70.0,
        "price_per_hour_usd": 0.111,
        "tts_price_per_million_usd": {"canopylabs/orpheus-arabic-saudi": 40.0},
        "chat_price_per_million_usd": {"input": 0.15, "cached": 0.075, "output": 0.6},
        "cost_usd": 0.04,
        "note": "T1",
    }
    return FirstAudioLine.model_validate(base | fields)


def test_each_of_plan_006s_kinds_is_appended_and_read_back_as_its_own(tmp_path: Path) -> None:
    path = tmp_path / "history.jsonl"
    lines = (talker_line(), scenario_line(), uncertain_line(), first_audio_line(), timing_line())
    for line in lines:
        assert history_accepts(line)
        append_line(line, path)
    assert read_history(path) == lines
    kinds = [json.loads(raw)["kind"] for raw in path.read_text("utf-8").splitlines()]
    assert kinds == ["talker", "scenarios", "uncertain", "first_audio", "timing"]
    # Each counts its requests by model, so a run's pacers start the day from them.
    today = requests_today(path, samples.WHEN.date())
    assert today[TALKER] == 20 + 30 + 14 and today["llama-3.1-8b-instant"] == 10


def test_each_kind_has_its_table_its_strata_its_targets_and_its_prices() -> None:
    lines: list[AnyLine] = [talker_line(), scenario_line(), uncertain_line(), first_audio_line()]
    page = render_history(lines)
    # Only T bills audio; every run's cost counts.
    assert "Spend so far: 4 run(s), 70.0 billed seconds, $0.0724." in page
    for title in ("Talker runs", "Scenario runs", "Uncertain-middle runs", "First-audio runs"):
        assert f"## {title}" in page
    assert (
        "| 1 | 2026-11-03T09:00:00+00:00 | k1-dev-a | 0f44056 | k1 | openai/gpt-oss-120b |" in page
    )
    assert "| 81.2% | 100.0% | 90.0% | 87.5% | 0.734 | 1.412 | 0 | $0.0123 | yes |" in page
    assert "| language | saudi | 3 | 6 | 0 | 75.0% | 80.0% |" in page
    assert "| s01_password_stop_go_on | 3 |" in page and "| 3 | 2 | 6 | 0 | 5 | yes |" in page
    assert "| o1 | llama-3.1-8b-instant | 9 | 1 | 4 | 7 | 1 | 0 | 212 | 0.1250 | no |" in page
    assert "| kind | listening_sound | 3 | 9 | 3 | 5 of 6 | 1 of 2 |" in page
    assert "| raises_right | fails |" in page and "| answers_in_time | holds |" in page
    assert "| dev | declared | 7 | — | — | 2750 | 2750 | 1 | 1 of 3 | 70.0 |" in page
    assert "| detector | 4 | 4 | — | — | 2900 | 2900 | 1 |" in page
    assert "| label | 3 | 3 | — | — | 2600 | 2600 | 0 |" in page
    assert "| no_search_median_ms | — |" in page and "| progress_late | fails |" in page
    assert "| Price per million tokens, openai/gpt-oss-120b | $0.15 in, $0.6 out |" in page
    assert "| Price per million tokens, cached | $0.05 |" in page
    assert page.count("| Price per hour of audio |") == 1  # T's alone
    assert "| Price per million characters, canopylabs/orpheus-arabic-saudi | $40 |" in page
    assert page.count("### ") == 4
    bare = render_history([scenario_line(passed={}), uncertain_line(targets={}, breakdowns={})])
    assert "| Scenario |" not in bare and "| Target | Held |" not in bare


@pytest.mark.parametrize("build", [uncertain_line, first_audio_line])
def test_a_held_out_line_of_u_or_t_holds_no_small_group(build: Any) -> None:
    if build is uncertain_line:
        small: dict[str, Any] = {"breakdowns": {"kind": {"echo": _count(1, 0, items=2)}}}
        wide: dict[str, Any] = {"breakdowns": {"kind": {"echo": _count(1, 0, items=9)}}}
    else:
        group = FirstAudioGroup(items=2, variants=2, paths=_paths(None, 2), progress_late=0)
        small = {"ends": {"label": group}}
        wide = {"ends": {"label": group.model_copy(update={"items": 9})}}
    with pytest.raises(ValidationError, match="at least 3 items"):
        build(split="held-out", **small)
    with pytest.raises(ValidationError, match="no more items than the run"):
        build(**wide)

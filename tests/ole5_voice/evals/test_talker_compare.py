"""Two dev runs of K compared (talker_compare.py) and the keep rule (talker_keep.py): fixed,
broken and net by passing verdict, the sign test by item, the noise as registered, the stratum
guard; refusals of held-out, other commits, data or settings, and of a run marked for the
owner; and the keep rule as registered, the first clause's median first, then the sign test,
then the faster."""

from __future__ import annotations

from pathlib import Path

import pytest
from ole5_voice.evals import talker_compare, talker_keep
from ole5_voice.evals.judge_check import CHECK_FILE, JudgeCheck
from ole5_voice.evals.runs import SCORECARD_FILE
from ole5_voice.evals.talker_data import ToolUse
from ole5_voice.evals.talker_score import TalkerScorecard, VariantRecord

from tests.ole5_voice.evals.talker_fakes import TOOL
from tests.ole5_voice.evals.talker_support import record, write_run

BETTER = [f"i{n}" for n in range(8)]


def _records(passing: set[str], first_clause_s: float = 0.5) -> list[VariantRecord]:
    found = [
        record(item, variant, passed=item in passing, first_clause_s=first_clause_s)
        for item in BETTER
        for variant in ("v1", "v2")
    ]
    found.append(record("f1", failure="provider"))
    found.append(record("n1", kind="none", language="saudi", passed=True))
    return found


def test_a_comparison_counts_fixed_and_broken_and_judges_by_item(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    a = write_run(tmp_path / "a", _records(set()))
    b = write_run(tmp_path / "b", _records(set(BETTER)), arm="k3", model="openai/gpt-oss-20b")
    assert talker_compare.main([str(a), str(b / SCORECARD_FILE)]) == 0
    report = capsys.readouterr().out
    assert "fixed 16, broken 0, net +16; unchanged 1." in report
    assert "Items better 8, worse 0, unchanged 1: p = 0.0078, beyond the noise" in report
    assert "- f1/v1: provider in A; provider in B" in report
    assert "Variants whose verdict differs: 16 of 17" in report
    assert "| kind | none | 1 | 0 | 0 | 1.0000 |" in report


def test_two_runs_of_one_arm_give_the_noise(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    a = write_run(tmp_path / "a", _records({"i0", "i1", "i2"}))
    b = write_run(tmp_path / "b", [*_records({"i0", "i1", "i3"})[:-1], record("n2")])
    assert talker_compare.main([str(a), str(b)]) == 0
    report = capsys.readouterr().out
    assert "Variants whose verdict differs: 4 of 16 (i2/v1, i2/v2, i3/v1, i3/v2)." in report
    assert "2 item(s) changed, so the smallest change one run can detect is" in report
    assert "- n1/v1: in A only" in report and "- n2/v1: in B only" in report


@pytest.mark.parametrize(
    ("other", "words"),
    [
        ({"split": "held-out"}, "held-out is read once"),
        ({"commit": "ef" * 20}, "their commits differ"),
        ({"effort": "medium"}, "their settings differ (llm.reasoning_effort)"),
    ],
)
def test_runs_that_cannot_be_compared_are_refused(
    tmp_path: Path, other: dict[str, str], words: str, capsys: pytest.CaptureFixture[str]
) -> None:
    a = write_run(tmp_path / "a", _records(set()))
    records = _records(set()) if "split" not in other else []
    b = write_run(tmp_path / "b", records, **other)  # type: ignore[arg-type]
    assert talker_compare.main([str(a), str(b)]) == 1
    assert words in capsys.readouterr().out


def test_a_run_marked_for_the_owner_is_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    a = write_run(tmp_path / "a", _records(set()))
    check = JudgeCheck(run="a", seed=6, drawn=24, disagreements=4, owner_judges=True)
    (a / CHECK_FILE).write_text(check.model_dump_json(), encoding="utf-8")
    b = write_run(tmp_path / "b", _records(set()))
    assert talker_compare.main([str(b), str(a)]) == 1
    assert "marked for the owner to judge" in capsys.readouterr().out


def _arms(tmp_path: Path, k1: list[VariantRecord], k3: list[VariantRecord]) -> list[str]:
    folders = []
    for arm, model, found in (("k1", "openai/gpt-oss-120b", k1), ("k3", "openai/gpt-oss-20b", k3)):
        runs = [write_run(tmp_path / f"{arm}-{n}", found, arm=arm, model=model) for n in "ab"]
        folders += ["--arm", f"{arm}={runs[0]},{runs[1]}"]
    return folders


def test_the_keep_rule_keeps_the_arm_with_more_right_answers_beyond_the_noise(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    argv = _arms(tmp_path, _records(set(), 0.6), _records(set(BETTER), 0.9))
    assert talker_keep.main(argv) == 0
    report = capsys.readouterr().out
    assert "| k1 |" in report and "| 0.600 | yes |" in report
    assert "Items better in k3 than in k1: 8, worse: 0" in report and "Kept: k3." in report


def test_a_tie_goes_to_the_faster_arm(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    argv = _arms(tmp_path, _records({"i0"}, 0.8), _records({"i1"}, 0.4))
    assert talker_keep.main(argv) == 0
    report = capsys.readouterr().out
    assert "a tie: it goes to the faster, k3" in report and "Kept: k3." in report


def test_an_arm_past_the_first_clauses_median_is_not_kept(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    argv = _arms(tmp_path, _records(set(), 0.6), _records(set(BETTER), 1.4))
    assert talker_keep.main(argv) == 0
    assert "Only k1 comes within 1.0 s: it is kept." in capsys.readouterr().out
    argv = _arms(tmp_path / "slow", _records(set(), 1.2), _records(set(), 1.4))
    assert talker_keep.main(argv) == 0
    assert "the default stays" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("argv", "words"),
    [
        (["--arm", "k1=onlyone"], "is not NAME=RUN_A,RUN_B"),
        ([], "compares one or two arms"),
    ],
)
def test_the_keep_rule_refuses_what_it_cannot_judge(
    argv: list[str], words: str, capsys: pytest.CaptureFixture[str]
) -> None:
    assert talker_keep.main(argv) == 1
    assert words in capsys.readouterr().out


def test_the_keep_rule_takes_complete_dev_runs_of_each_arm(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    a = write_run(tmp_path / "a", _records(set()))
    b = write_run(tmp_path / "b", _records(set()), complete=False)
    assert talker_keep.main(["--arm", f"k1={a},{b}"]) == 1
    assert "is not a complete dev run of the arm k1" in capsys.readouterr().out
    argv = [*_arms(tmp_path / "three", _records(set()), _records(set())), "--arm", f"k9={a},{a}"]
    assert talker_keep.main(argv) == 1


def _searched(records: list[VariantRecord], ms: float) -> list[VariantRecord]:
    """`records`, each answerable reply having searched from 0.3 s for `ms` before it spoke."""
    search = (ToolUse(tool=TOOL, outcome="ok", ms=ms, began_s=0.3),)
    return [
        r.model_copy(update={"turn": r.turn.model_copy(update={"tools": search})})
        if r.turn is not None and r.kind == "answerable"
        else r
        for r in records
    ]


def test_the_keep_rule_reads_the_models_own_time_the_search_taken_out(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Q15: k1 searches for 0.9 s before its first clause at 1.6 s on the wall clock, its own
    time 0.7 s, so it is within 1.0 s; k3 does not search and takes 1.2 s."""
    k1, k3 = _searched(_records(set(), 1.6), 900.0), _records(set(), 1.2)
    argv = _arms(tmp_path, k1, k3)
    assert talker_keep.main(argv) == 0
    report = capsys.readouterr().out
    assert "The rule reads the model's own time to the first clause (Q15)" in report
    assert "| k1 |" in report and "| 0.700 | 1.600 | yes |" in report
    assert "| 1.200 | 1.200 | no |" in report and "Only k1 comes within 1.0 s" in report
    card = TalkerScorecard.model_validate_json((tmp_path / "k1-a" / SCORECARD_FILE).read_bytes())
    assert card.keep_time == "own_first_clause_median_s"
    assert card.totals.own_first_clause_median_s == pytest.approx(0.7)
    assert card.totals.first_clause_median_s == pytest.approx(1.6)

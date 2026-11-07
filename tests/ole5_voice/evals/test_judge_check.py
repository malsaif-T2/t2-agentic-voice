"""The owner's check of the judge (judge_check.py, plan 006's Q6): 24 judged answers drawn at
random, seeded and stratified by verdict, into a sheet the owner fills; the filled sheet read
back, more than 3 disagreements marking the run for the owner to judge; a held-out run, other
data and an unfilled sheet refused."""

from __future__ import annotations

import tomllib
from collections import Counter
from pathlib import Path

import pytest
from ole5_voice.evals import judge_check, talker_run
from ole5_voice.evals.judge_check import (
    CHECK_FILE,
    SHEET_FILE,
    JudgeCheck,
    draw,
    judged_of,
    marked,
    read_sheet,
)
from ole5_voice.evals.talker_data import TalkerDataError
from t2_agentic_voice import Card

from tests.ole5_voice.evals.talker_fakes import Scripted
from tests.ole5_voice.evals.talker_support import Setup, item, make_setup, record, write_run

ITEMS = [item(f"a{n:02d}") for n in range(14)] + [item("n1", kind="none")]


def test_a_draw_is_seeded_and_stratified_by_verdict() -> None:
    found = [record(f"i{n}", passed=n % 4 != 0) for n in range(40)]  # 30 right, 10 wrong
    found += [record("x1", failure="stuck")]
    drawn = draw(found, seed=3)
    verdicts = Counter(r.judged.verdict for r in drawn if r.judged)
    assert len(drawn) == 24 and verdicts == {"right": 18, "wrong": 6}
    assert drawn == draw(found, seed=3) and drawn != draw(found, seed=4)
    rare = [record(f"i{n}") for n in range(30)] + [record("w1", passed=False)]
    assert Counter(r.judged.verdict for r in draw(rare, 0) if r.judged)["wrong"] == 1
    assert len(draw(found[:5], seed=3)) == 5  # every one, when there are no more


def test_a_record_with_no_verdict_is_never_checked() -> None:
    with pytest.raises(TalkerDataError, match="has no verdict"):
        judged_of(record("a", failure="provider"))


def _dev_run(setup: Setup) -> Path:
    setup.calls.script["How do I print? a00"] = Scripted(cards=(Card(title="T", steps=("s",)),))
    argv = [*setup.argv(), "--split", "dev", "--call-language", "first"]
    setup.chat.verdicts = {"a01": "wrong", "a02": "invented", "n1": "not_in_knowledge"}
    assert talker_run.main(argv, parts=setup.parts()) == 0
    return setup.out()


@pytest.fixture
def setup(tmp_path: Path) -> Setup:
    return make_setup(tmp_path, ITEMS)


def _main(setup: Setup, *argv: str) -> int:
    return judge_check.main(list(argv), git=setup.world.git)


def test_a_sheet_is_drawn_for_the_owner_and_read_back(
    setup: Setup, capsys: pytest.CaptureFixture[str]
) -> None:
    out = _dev_run(setup)
    folder = ["--folder", str(setup.world.top)]
    assert _main(setup, "draw", str(out), "--points-text", str(setup.points_text), *folder) == 0
    sheet = tomllib.loads((out / SHEET_FILE).read_text(encoding="utf-8"))
    assert sheet["run"] == "k1-a" and len(sheet["answers"]) == 24
    assert {a["owner"] for a in sheet["answers"]} == {""}
    first = next(a for a in sheet["answers"] if a["item"] == "a00" and a["variant"] == "v1")
    assert first["caller_said"] == "How do I print? a00" and first["card"] == "T: s"
    assert first["points"] == ["The made-up text of point 1."] and len(first["key_facts"]) == 2
    assert {a["judge"] for a in sheet["answers"]} >= {"right", "wrong", "invented"}
    # Unfilled, it is refused; filled with four disagreements, the run is marked.
    assert _main(setup, "read", str(out)) == 1
    assert "have no owner's verdict" in capsys.readouterr().out
    text = (out / SHEET_FILE).read_text(encoding="utf-8")
    filled, changed = [], 0
    for line in text.splitlines():
        if line.startswith("judge = "):
            verdict = line.removeprefix("judge = ")
        if line == 'owner = ""':
            line = f"owner = {'"partly_right"' if changed < 4 else verdict}"
            changed += 1
        filled.append(line)
    (out / SHEET_FILE).write_text("\n".join(filled) + "\n", encoding="utf-8")
    assert _main(setup, "read", str(out)) == 0
    check = JudgeCheck.model_validate_json((out / CHECK_FILE).read_bytes())
    assert check.drawn == 24 and check.disagreements == 4 and check.owner_judges
    assert marked(out) and not marked(out.parent)
    assert read_sheet(out / SHEET_FILE).seed == 6


def test_a_held_out_run_or_one_with_no_verdict_is_never_drawn(
    setup: Setup, capsys: pytest.CaptureFixture[str]
) -> None:
    held = write_run(setup.world.main / "var" / "held", [], split="held-out")
    assert _main(setup, "draw", str(held), "--points-text", str(setup.points_text)) == 1
    assert "read only as counts" in capsys.readouterr().out
    failed = write_run(setup.world.main / "var" / "failed", [record("a00", failure="stuck")])
    folder = ["--folder", str(setup.world.top)]
    assert _main(setup, "draw", str(failed), "--points-text", str(setup.points_text), *folder) == 1
    assert "holds no judged answer" in capsys.readouterr().out


def test_a_sheet_of_other_data_or_another_run_is_refused(
    setup: Setup, capsys: pytest.CaptureFixture[str]
) -> None:
    out = _dev_run(setup)
    (setup.data / "knowledge" / "a00.toml").write_text(
        (setup.data / "knowledge" / "a00.toml")
        .read_text(encoding="utf-8")
        .replace("made-up item", "changed"),
        encoding="utf-8",
    )
    folder = ["--folder", str(setup.world.top)]
    assert _main(setup, "draw", str(out), "--points-text", str(setup.points_text), *folder) == 1
    assert "their digest differs" in capsys.readouterr().out
    other = out / "other.toml"
    other.write_text('run = "k9"\nseed = 1\n[[answers]]\n' + _answer(), encoding="utf-8")
    assert _main(setup, "read", str(out), "--sheet", str(other)) == 1
    assert "not k1-a's" in capsys.readouterr().out
    other.write_text("run = [", encoding="utf-8")
    assert _main(setup, "read", str(out), "--sheet", str(other)) == 1
    assert "not TOML" in capsys.readouterr().out
    other.write_text('run = "k1-a"\nseed = 1\n', encoding="utf-8")
    assert _main(setup, "read", str(out), "--sheet", str(other)) == 1
    assert "answers" in capsys.readouterr().out
    assert _main(setup, "read", str(out), "--sheet", str(out / "missing.toml")) == 1


def _answer() -> str:
    keys = ("item", "variant", "caller_said", "answer", "card", "judge_reason")
    values = "\n".join(f'{key} = "a1"' if key == "item" else f'{key} = "v1"' for key in keys)
    return values + '\npoints = []\nkey_facts = []\njudge = "right"\nowner = "right"\n'


def test_draw_needs_the_points_text(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        judge_check.main(["draw", "somewhere"])
    assert "draw needs --points-text" in capsys.readouterr().err

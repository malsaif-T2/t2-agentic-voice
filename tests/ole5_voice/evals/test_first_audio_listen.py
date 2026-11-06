"""`poe first-audio-listen`, the owner's check of T1 (plan 006's registration, T): ten of T1's
reply openings picked by a seed into a new folder with a sheet to mark, the same ten for the
same seed, and the marked sheet read back; refused for a run that is not T1's, or keeps too few
replies, before anything is written."""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest
from ole5_voice.evals import first_audio, first_audio_listen
from ole5_voice.evals.first_audio_score import ReplayedTurn
from ole5_voice.evals.models import Item

from tests.ole5_voice.evals.eot_support import paused
from tests.ole5_voice.evals.first_audio_support import TRun, call, t_run
from tests.ole5_voice.evals.run_support import World


def _many(world: World) -> list[Item]:
    return [paused(world, f"n{n:02}_made_up", kind="request") for n in range(1, 13)]


def _t1(tmp_path: Path, *extra: str) -> TRun:
    """A complete dev run of T1 over 12 recordings, each reply's opening kept."""
    run = t_run(tmp_path, call(ReplayedTurn(ttfa_ms=1000.0)), items=_many)
    argv = run.argv(*extra)
    argv[argv.index("--cap-usd") + 1] = "50"
    assert first_audio.main(argv, parts=run.parts()) == 0
    return run


def _pick(run: TRun, out: Path, seed: str = "7", *extra: str) -> int:
    argv = ["--run", str(run.out), "--seed", seed, "--out", str(out), *extra]
    return first_audio_listen.main(argv, parts=run.parts().plan)


def test_ten_replies_are_picked_by_the_seed_with_a_sheet_to_mark(tmp_path: Path) -> None:
    run = _t1(tmp_path)
    first, again = run.world.main / "var" / "listen-a", run.world.main / "var" / "listen-b"
    assert _pick(run, first) == 0 and _pick(run, again) == 0
    files = sorted(path.name for path in first.glob("*.wav"))
    assert files == [f"{n:02}.wav" for n in range(1, 11)]
    sheet = tomllib.loads((first / "sheet.toml").read_text(encoding="utf-8"))
    assert (sheet["run"], sheet["seed"], len(sheet["replies"])) == ("t1", 7, 10)
    assert {entry["clipped"] for entry in sheet["replies"]} == {"?"}
    assert len({entry["item"] for entry in sheet["replies"]}) == 10
    same = tomllib.loads((again / "sheet.toml").read_text(encoding="utf-8"))
    assert same == sheet  # the same seed, the same ten
    reply = sheet["replies"][0]
    kept = run.out / "replies" / f"{reply['variant']}-{reply['reply']}.wav"
    assert (first / "01.wav").read_bytes() == kept.read_bytes()


def _marked(run: TRun, tmp_path: Path, marks: list[str]) -> Path:
    out = run.world.main / "var" / "listen"
    assert _pick(run, out) == 0
    text = (out / "sheet.toml").read_text(encoding="utf-8")
    for mark in marks:
        text = text.replace('clipped = "?"', f'clipped = "{mark}"', 1)
    (out / "sheet.toml").write_text(text, encoding="utf-8")
    return out / "sheet.toml"


@pytest.mark.parametrize(
    ("marks", "code", "verdict"),
    [(["no"] * 10, 0, "passes"), (["no"] * 9 + ["yes"], 0, "fails"), (["no"] * 9, 1, "unmarked")],
)
def test_a_marked_sheet_is_read_back(
    tmp_path: Path,
    marks: list[str],
    code: int,
    verdict: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    sheet = _marked(_t1(tmp_path), tmp_path, marks)
    capsys.readouterr()
    assert first_audio_listen.main(["--read", str(sheet)]) == code
    assert f"verdict={verdict}" in capsys.readouterr().out


def test_each_refusal_comes_before_anything_is_written(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    run = _t1(tmp_path)
    out = run.world.main / "var" / "listen"
    assert _pick(run, out, "7", "--count", "13") == 2
    assert "fewer than --count 13" in capsys.readouterr().out and not out.exists()
    (tmp_path / "t0").mkdir()
    off = _t1(tmp_path / "t0", "--trim-silence", "off")
    assert _pick(off, out) == 2
    assert "tts.trim_silence on" in capsys.readouterr().out and not out.exists()
    (tmp_path / "broken.json").write_text("{}", encoding="utf-8")
    argv = ["--run", str(tmp_path / "broken.json"), "--seed", "1", "--out", str(out)]
    assert first_audio_listen.main(argv) == 2
    assert "not a run T scorecard" in capsys.readouterr().out
    out.mkdir(parents=True)
    assert _pick(run, out) == 2 and "exists" in capsys.readouterr().out
    (tmp_path / "sheet.toml").write_text("run = 1\n", encoding="utf-8")
    assert first_audio_listen.main(["--read", str(tmp_path / "sheet.toml")]) == 2
    assert "not a listening sheet" in capsys.readouterr().out


def test_picking_names_its_run_seed_and_folder(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as done:
        first_audio_listen.main(["--run", "t1"])
    assert done.value.code == 2 and "--seed and --out" in capsys.readouterr().err

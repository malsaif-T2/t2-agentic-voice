"""`poe overlap` (plan 005's registration, the arm O; its scorer is test_overlap_score.py's, its
measuring test_overlap_run.py's): the `reference` answerer over each split of the committed
golden set, every verdict right and 0 ms, reading no audio and appending no history line (inside
`poe check`); a run of the replay through a fake `AudioCall`, each clip over its reply, its
results, scorecard and history line; a held-out run's aggregates only; the settings on the
command line; and the refusals before any clip is fed."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from ole5_voice.evals import audio, items, overlap, run_settings
from ole5_voice.evals.items import EVALS, HISTORY_FILE
from ole5_voice.evals.models import Split
from ole5_voice.evals.overlap_card import OverlapScorecard
from ole5_voice.evals.overlap_plan import DEFAULT_REPLY, with_set
from ole5_voice.evals.overlap_score import in_set
from ole5_voice.evals.run_lines import OverlapLine
from ole5_voice.evals.run_parts import Parts
from ole5_voice.evals.runs import SCORECARD_FILE
from ole5_voice.evals.split import load_split
from t2_agentic_voice import T2VoiceError
from t2_agentic_voice.evals import OverlapReplay

from tests.ole5_voice.evals.overlap_support import (
    SCRIPT,
    WENT_ON,
    FakeReplayer,
    Run,
    clip,
    pipeline,
    stop,
)
from tests.ole5_voice.evals.run_support import FakeClock, golden_set, make_world
from tests.ole5_voice.evals.test_reference_answerer import _confirmed


def _no_audio(path: Path) -> audio.Wav:
    raise AssertionError("the reference answerer's run read an audio file")


@pytest.mark.parametrize("side", ["dev", "held-out"])
def test_the_reference_answerer_scores_every_committed_overlap_right_at_0_ms(
    side: Split, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Plan 005's step 9: `poe overlap --answerer reference` over the committed golden set,
    each variant given a made-up confirmation, gives every overlap clip its kind's verdict: all
    right, every stop 0 ms, no request, no target failing."""
    monkeypatch.setattr(audio, "read_wav", _no_audio)
    world = make_world(tmp_path)
    shutil.copytree(EVALS / "golden", world.data / "golden")
    for name in ("split.json", "spelling.toml", "script.toml"):
        shutil.copy2(EVALS / name, world.data / name)
    out = world.main / "var" / "runs" / f"o-{side}"
    argv = ["--answerer", "reference", "--split", side, "--out", str(out), "--note", "step 9"]
    lines: list[object] = []
    parts = overlap.OverlapParts(
        plan=Parts(folder=world.top, git=world.git, load_items=_confirmed),
        append_line=lambda line, path: lines.append(line),
    )
    assert overlap.main(argv, parts=parts) == 0
    card = OverlapScorecard.model_validate_json((out / SCORECARD_FILE).read_bytes())
    sides = load_split(EVALS / "split.json").items
    on_side = [
        v
        for i in items.load_items(EVALS / "golden")
        for v in i.variants
        if sides[i.id] == side and in_set(i.kind, v.tags)
    ]
    totals = card.totals
    assert (card.complete, totals.variants, totals.right) == (True, len(on_side), len(on_side))
    assert totals.variants > 10 and totals.should_stop and totals.should_go_on
    assert (totals.false_stops, totals.requests_max, card.requests) == (0, 0, 0)
    assert {totals.detected_median_ms, totals.marked_median_ms} <= {0.0, None}
    assert all(target.holds is not False for target in card.targets)
    assert len(card.variants) == (len(on_side) if side == "dev" else 0)
    assert lines == [] and (out / "results.jsonl").exists() == (side == "dev")


def _world(tmp_path: Path, *script: OverlapReplay | BaseException) -> Run:
    world = make_world(tmp_path)
    found = (
        clip(world, "k1", "stop_word", source="script", end_ms=1000, devices=("laptop", "wired")),
        clip(world, "b1", "listening_sound", tags=("over-assistant",)),
        clip(world, "r1", "request", language="english", tags=("over-assistant",)),
        clip(world, "r2", "request", tags=("duck",)),  # recorded alone: not an overlap clip
        clip(world, "q1", "echo_only", language="none", source="script"),
    )
    (world.data / "script.toml").write_text(SCRIPT, encoding="utf-8")
    replies = world.top / "lab"
    replies.mkdir()
    lab = [{"id": "r1", "lang": "en", "spoken": "A made-up reply, as said.", "ms": 9}]
    (replies / "replies.json").write_text(json.dumps(lab), encoding="utf-8")
    clock = FakeClock()
    return Run(world, golden_set(*found), FakeReplayer(list(script), clock), clock=clock)


def test_a_run_of_the_replay_plays_each_clip_over_its_reply_and_writes_as_it_goes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    run = _world(tmp_path, stop(), stop(last_ms=1300.0), stop(), WENT_ON, WENT_ON)
    replies = str(run.world.top / "lab")
    argv = pipeline(run, "--replies", replies, "--set", "stt.no_speech_max=0.5", "--stt-rpm", "10")
    assert overlap.main(argv, parts=run.parts()) == 0
    card = OverlapScorecard.model_validate_json((run.out / SCORECARD_FILE).read_bytes())
    found = [(r.variant, r.expected, r.verdict.action, r.judged.right) for r in card.variants]
    assert found == [
        ("k1-laptop", "stop", "stop", True),
        ("k1-wired", "stop", "stop", True),
        ("b1-laptop", "go_on", "stop", False),  # a false stop
        ("r1-laptop", "stop", "go_on", False),  # a stop missed
        ("q1-laptop", "go_on", "go_on", True),
    ]
    marks = [r.judged.from_mark_ms for r in card.variants]
    assert marks == [600.0, 300.0, None, None, None]
    asked = run.replayer.asked
    assert [a["language"] for a in asked] == ["ar-SA", "ar-SA", "ar-SA", "en", "en"]
    assert asked[4]["reply"] == ("A made-up reply, as said.",) and card.variants[4].reply_known
    assert asked[0]["reply"] == (DEFAULT_REPLY["ar-SA"],) and not card.variants[0].reply_known
    assert asked[3]["reply"] == (DEFAULT_REPLY["en"],)
    assert [a["word_end_ms"] for a in asked] == [1000.0, 1000.0, None, None, None]
    assert {(a["at_s"], a["tail_s"]) for a in asked} == {(1.0, 4.5)}
    assert asked[0]["seconds"] == pytest.approx(1.0 + 1.0 + 4.5 + 2.0)
    built = run.replayer.built["settings"]
    assert (built.interruptions.mode, built.stt.no_speech_max) == ("two_step", 0.5)
    assert run.replayer.started == run.replayer.closed == 1 and run.stt.closed
    assert (card.requests, card.billed_seconds) == (6, 60.0)
    assert card.run.settings["stt.no_speech_max"] == "0.5"
    assert card.run.settings["run.replies"] == "given"
    assert (run.out / "results.jsonl").read_text("utf-8").count("\n") == 5
    ((line, first), (same, second)) = run.lines.appended
    assert line is same and isinstance(line, OverlapLine)
    assert (first, second) == (run.world.data / HISTORY_FILE, run.out / HISTORY_FILE)
    assert (line.variants, line.right, line.requests_max, line.stop_median_ms) == (5, 3, 2, 450.0)
    assert line.targets["listening_false_stops"] is False and "item" not in line.breakdowns
    logged = capsys.readouterr().out
    assert "variant_done" in logged and "made-up" not in logged


def test_a_held_out_run_writes_aggregates_only(tmp_path: Path) -> None:
    world = make_world(tmp_path)
    found = [clip(world, f"h{n}", "stop_word") for n in range(3)]
    found.append(clip(world, "d1", "stop_word"))  # the dev side, which a held-out run needs
    clock = FakeClock()
    golden = golden_set(*found, held_out=("h0", "h1", "h2"))
    run = Run(world, golden, FakeReplayer([stop(), stop(), stop()], clock), clock=clock)
    (world.data / "script.toml").write_text(SCRIPT, encoding="utf-8")
    assert overlap.main(pipeline(run, split="held-out"), parts=run.parts()) == 0
    card = OverlapScorecard.model_validate_json((run.out / SCORECARD_FILE).read_bytes())
    assert card.variants == () and card.totals.variants == 3 and "item" not in card.breakdowns
    assert not (run.out / "results.jsonl").exists()
    (line, _), _ = run.lines.appended
    assert isinstance(line, OverlapLine) and line.split == "held-out"


@pytest.mark.parametrize(
    ("failure", "stopped"),
    [
        (KeyboardInterrupt(), "interrupted"),
        (T2VoiceError("The file-fed call's greeting never played."), "failed"),
        (ValueError("the reply is no phrase a greeting may say"), "failed"),
    ],
)
def test_a_run_stopped_early_keeps_what_it_measured(
    tmp_path: Path, failure: BaseException, stopped: str
) -> None:
    run = _world(tmp_path, stop(), failure)
    argv = pipeline(run, "--replies", str(run.world.top / "lab"))
    assert overlap.main(argv, parts=run.parts()) == 1
    card = OverlapScorecard.model_validate_json((run.out / SCORECARD_FILE).read_bytes())
    assert (card.complete, card.stopped, len(card.variants)) == (False, stopped, 1)
    assert run.replayer.closed == 1 and run.stt.closed


@pytest.mark.parametrize(
    ("change", "named"),
    [
        ({"main": True}, "this is the main checkout"),
        ({"dirty": True}, "the worktree has changes"),
    ],
)
def test_a_run_refuses_the_main_checkout_and_a_dirty_tree_before_any_clip(
    tmp_path: Path, change: dict[str, bool], named: str, capsys: pytest.CaptureFixture[str]
) -> None:
    run = _world(tmp_path)
    parts = run.parts()
    if change.get("main"):
        run.world.git.top = run.world.main
        parts = overlap.OverlapParts(
            plan=Parts(**{**parts.plan.__dict__, "folder": run.world.main}),
            audio_call=run.replayer,
        )
    run.world.git.dirty = change.get("dirty", False)
    assert overlap.main(pipeline(run), parts=parts) == 2
    assert named in capsys.readouterr().out and run.replayer.asked == []


@pytest.mark.parametrize(
    ("extra", "named"),
    [
        (["--set", "made.up=1"], "--set made.up names no setting"),
        (["--set", "stt.no_speech_max=loud"], "a value of --set stt.no_speech_max"),
        (["--set", "stt.live_language=auto"], "stt.live_language session"),
        ([], "holds no text of the reply r1"),  # q1's reply, with no --replies
    ],
)
def test_a_run_refuses_what_it_cannot_measure(
    tmp_path: Path, extra: list[str], named: str, capsys: pytest.CaptureFixture[str]
) -> None:
    run = _world(tmp_path)
    assert overlap.main(pipeline(run, *extra), parts=run.parts()) == 2
    assert named in capsys.readouterr().out and run.replayer.asked == []


def test_a_run_refuses_a_split_with_no_overlap_clip_a_bad_lab_file_and_a_bad_name(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    run = _world(tmp_path)
    (run.world.top / "lab" / "replies.json").write_text("[{}]", encoding="utf-8")
    argv = pipeline(run, "--replies", str(run.world.top / "lab"))
    assert overlap.main(argv, parts=run.parts()) == 2
    assert "replies.json" in capsys.readouterr().out
    world = make_world(tmp_path / "none")
    (world.data / "script.toml").write_text(SCRIPT, encoding="utf-8")
    alone = Run(world, golden_set(clip(world, "r2", "request")), run.replayer)
    assert overlap.main(pipeline(alone), parts=alone.parts()) == 2
    assert "no overlap clip" in capsys.readouterr().out
    (world.data / "script.toml").write_text("[made", encoding="utf-8")
    assert overlap.main(pipeline(alone), parts=alone.parts()) == 2
    assert "do not load" in capsys.readouterr().out
    bad = ["--answerer", "reference", "--split", "dev", "--out", str(run.out.parent / "Bad")]
    assert overlap.main([*bad, "--note", "n"], parts=run.parts()) == 2
    assert "is not a name" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("argv", "named"),
    [
        (["--answerer", "reference", "--split", "dev"], "a run needs --out, --note"),
        (
            ["--answerer", "pipeline", "--split", "dev", "--out", "x", "--note", "n"],
            "a run needs --model, --timeout-s, --price-per-hour, --cap-usd",
        ),
        (
            ["--answerer", "reference", "--split", "dev", "--out", "x", "--note", "{{" + "X}}"],
            "placeholder",
        ),
        (["--set", "nodot=1"], "GROUP.NAME=VALUE"),
        (["--cap-usd", "-1"], "0 or more"),
        (["--stt-rpm", "0"], "1 or more"),
    ],
)
def test_the_flags_a_run_needs(
    argv: list[str], named: str, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit):
        overlap.main(argv)
    assert named in capsys.readouterr().err


def test_the_settings_load_as_poe_evals_with_each_set_on_top(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env = tmp_path / "made-up.env"
    env.write_text("T2V_TURNS__VAD_STOP_MS=300\n", encoding="utf-8")
    monkeypatch.setattr(run_settings, "DOTENV", env)
    argv = ["--set", "interruptions.mode=drop", "--set", "stt.caption_filter=true"]
    args = overlap._parser().parse_args(argv)
    loaded = with_set(run_settings.load_settings(args), args.set)
    assert (loaded.turns.vad_stop_ms, loaded.interruptions.mode, loaded.stt.caption_filter) == (
        300,
        "two_step",  # the arm's rule, whatever was given
        True,
    )
    assert overlap.shown(loaded, args)["run.replies"] == "none"

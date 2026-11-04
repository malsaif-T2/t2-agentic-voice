"""`poe eot` (plan 003's registration, E; its scorer is test_eot_score.py's): the `reference`
answerer over each split of the committed golden set at 0 cut-offs and 0 ms, reading no audio
and appending no history line (inside `poe check`); a run of the pipeline through a fake
`turn_ends`, its results, scorecard and history line; a held-out run's aggregates only; and the
refusals before any clip is fed."""

from __future__ import annotations

import shutil
from collections.abc import AsyncIterator, Iterable
from pathlib import Path
from typing import Any

import pytest
from ole5_voice.evals import audio, eot, items, run_settings
from ole5_voice.evals.eot_score import (
    EotScorecard,
)
from ole5_voice.evals.items import EVALS, HISTORY_FILE
from ole5_voice.evals.models import Split
from ole5_voice.evals.run_lines import EotLine
from ole5_voice.evals.run_parts import Parts
from ole5_voice.evals.runs import SCORECARD_FILE
from ole5_voice.evals.split import load_split
from t2_agentic_voice import VoiceSettings, evals
from t2_agentic_voice.ports import AudioClip

from tests.ole5_voice.evals.eot_support import Lines, golden_set, parts_of, paused
from tests.ole5_voice.evals.run_support import World, make_world
from tests.ole5_voice.evals.test_reference_answerer import _confirmed


def _no_audio(path: Path) -> audio.Wav:
    raise AssertionError("the reference answerer's run read an audio file")


@pytest.mark.parametrize("side", ["dev", "held-out"])
def test_the_reference_answerer_scores_the_committed_paused_requests_at_0_cut_offs_and_0_ms(
    side: Split, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Plan 003's step 16: `poe eot --answerer reference` over the committed golden set, each
    variant given a made-up confirmation (none is confirmed before the owner's review), gives
    every paused request its own mark: 0 cut-offs, 0 misses, 0 ms."""
    for module in (audio, eot):
        monkeypatch.setattr(module, "read_wav", _no_audio)
    world = make_world(tmp_path)
    shutil.copytree(EVALS / "golden", world.data / "golden")
    for name in ("split.json", "spelling.toml"):
        shutil.copy2(EVALS / name, world.data / name)
    out = world.main / "var" / "runs" / f"eot-{side}"
    argv = ["--answerer", "reference", "--split", side, "--out", str(out), "--note", "step 16"]
    lines = Lines()
    parts = Parts(folder=world.top, git=world.git, load_items=_confirmed)
    assert eot.main(argv, parts=parts, append_line=lines) == 0
    card = EotScorecard.model_validate_json((out / SCORECARD_FILE).read_bytes())
    sides = load_split(EVALS / "split.json").items
    committed = items.load_items(EVALS / "golden")
    on_side = [
        v
        for i in committed
        if sides[i.id] == side and i.kind == "paused_request"
        for v in i.variants
    ]
    totals = card.paused.totals
    assert (card.complete, totals.variants, totals.cut_offs, totals.misses) == (
        True,
        len(on_side),
        0,
        0,
    )
    assert (totals.delay_median_ms, totals.delay_p90_ms) == (0.0, 0.0)
    assert (totals.vad_stop_median_ms, totals.decision_median_ms) == (0.0, 0.0)
    assert len(card.variants) == (len(on_side) if side == "dev" else 0)
    assert lines.appended == [] and not (world.data / HISTORY_FILE).exists()
    assert (out / "results.jsonl").exists() == (side == "dev")


class FakeTurnEnds:
    """Stands in for `evals.turn_ends`: each clip's turn ends from a script, keeping the clips
    and what it was asked."""

    def __init__(
        self, script: list[list[tuple[float, float]]], *, interrupt_after: int | None = None
    ) -> None:
        self.script, self.interrupt_after = script, interrupt_after
        self.clips: list[AudioClip] = []
        self.asked: dict[str, Any] = {}
        self.closed = False

    async def __call__(
        self, clips: Iterable[AudioClip], **asked: Any
    ) -> AsyncIterator[tuple[evals.TurnEnd, ...]]:
        self.clips, self.asked = list(clips), asked
        try:
            for number, ends in enumerate(self.script):
                if number == self.interrupt_after:
                    raise KeyboardInterrupt
                yield tuple(evals.TurnEnd(speech_stop_ms=s, end_ms=e) for s, e in ends)
        finally:
            self.closed = True


def _world(tmp_path: Path) -> tuple[World, Parts]:
    world = make_world(tmp_path)
    found = (
        paused(world, "p1", devices=("laptop", "wired")),
        paused(world, "p2", language="english", end_ms=1000),
        paused(world, "r1", kind="request", seconds=1.0),
        paused(world, "n1", kind="noise", seconds=1.0),
    )
    return world, parts_of(world, golden_set(*found))


def _pipeline(world: World, *extra: str, split: str = "dev") -> list[str]:
    out = world.main / "var" / "runs" / "e1"
    return [
        "--answerer",
        "pipeline",
        "--split",
        split,
        "--out",
        str(out),
        "--note",
        "E1",
        "--audio",
        f"owner={world.audio}",
        *extra,
    ]


def test_a_run_of_the_pipeline_feeds_each_variant_and_writes_as_it_goes(
    tmp_path: Path, settings: VoiceSettings, capsys: pytest.CaptureFixture[str]
) -> None:
    world, parts = _world(tmp_path)
    fake = FakeTurnEnds(
        [
            [(1600.0, 1800.0)],
            [(900.0, 1000.0), (1700.0, 1900.0)],
            [(1100.0, 1500.0)],
            [(500.0, 700.0)],
        ]
    )
    lines = Lines()
    code = eot.main(_pipeline(world, "--secondary"), parts=parts, turn_ends=fake, append_line=lines)
    assert code == 0
    out = world.main / "var" / "runs" / "e1"
    card = EotScorecard.model_validate_json((out / SCORECARD_FILE).read_bytes())
    assert [r.variant for r in card.variants] == ["p1-laptop", "p1-wired", "p2-laptop", "r1-laptop"]
    assert [r.judged.verdict for r in card.variants] == ["timed", "cut_off", "timed", "timed"]
    assert card.paused.totals.cut_offs == 1 and card.secondary is not None
    assert card.secondary.totals.variants == 1 and card.secondary.totals.vad_stop_median_ms is None
    assert [len(clip.pcm16) for clip in fake.clips] == [64_000, 64_000, 64_000, 32_000]
    assert fake.asked == {"settings": fake.asked["settings"], "lead_s": 1.0, "tail_s": 4.5}
    assert fake.closed and (out / "results.jsonl").read_text("utf-8").count("\n") == 4
    ((line, first), (same, second)) = lines.appended
    assert line is same and isinstance(line, EotLine)
    assert (first, second) == (world.data / HISTORY_FILE, out / HISTORY_FILE)
    assert (line.variants, line.cut_offs, line.secondary and line.secondary.variants) == (3, 1, 1)
    assert line.settings["turns.vad_stop_ms"] == "200" and "item" not in line.breakdowns
    logged = capsys.readouterr().out
    assert "variant_done" in logged and "verdict=cut_off" in logged and "made-up" not in logged


def test_a_held_out_run_writes_aggregates_only(tmp_path: Path) -> None:
    world = make_world(tmp_path)
    found = [paused(world, f"h{n}") for n in range(3)]
    parts = parts_of(world, golden_set(*found, paused(world, "d1"), held_out=("h0", "h1", "h2")))
    lines = Lines()
    fake = FakeTurnEnds([[(1600.0, 1800.0)]] * 3)
    assert (
        eot.main(_pipeline(world, split="held-out"), parts=parts, turn_ends=fake, append_line=lines)
        == 0
    )
    out = world.main / "var" / "runs" / "e1"
    card = EotScorecard.model_validate_json((out / SCORECARD_FILE).read_bytes())
    assert card.variants == () and card.paused.totals.variants == 3
    assert not (out / "results.jsonl").exists()
    (line, _), _ = lines.appended
    assert isinstance(line, EotLine) and line.split == "held-out"


def test_an_interrupted_run_keeps_what_it_measured_and_says_it_is_incomplete(
    tmp_path: Path,
) -> None:
    world, parts = _world(tmp_path)
    fake = FakeTurnEnds([[(1600.0, 1800.0)]] * 3, interrupt_after=1)
    assert eot.main(_pipeline(world), parts=parts, turn_ends=fake, append_line=Lines()) == 1
    card = EotScorecard.model_validate_json(
        (world.main / "var" / "runs" / "e1" / SCORECARD_FILE).read_bytes()
    )
    assert (card.complete, len(card.variants)) == (False, 1) and fake.closed


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
    world, parts = _world(tmp_path)
    if change.get("main"):
        world.git.top = world.main
        parts = Parts(**{**parts.__dict__, "folder": world.main})
    world.git.dirty = change.get("dirty", False)
    fake = FakeTurnEnds([])
    assert eot.main(_pipeline(world), parts=parts, turn_ends=fake, append_line=Lines()) == 2
    assert named in capsys.readouterr().out and fake.clips == []


def test_a_run_refuses_what_it_cannot_measure(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    world = make_world(tmp_path)
    no_pause = parts_of(world, golden_set(paused(world, "r1", kind="request")))
    assert eot.main(_pipeline(world), parts=no_pause, append_line=Lines()) == 2
    assert "no paused request" in capsys.readouterr().out
    unmarked = paused(world, "p9")
    blank = unmarked.model_copy(
        update={"variants": (unmarked.variants[0].model_copy(update={"turn_ends_ms": ()}),)}
    )
    assert (
        eot.main(_pipeline(world), parts=parts_of(world, golden_set(blank)), append_line=Lines())
        == 2
    )
    assert "no turn end marked" in capsys.readouterr().out
    world, parts = _world(tmp_path / "named")
    bad = world.main / "var" / "runs" / "Bad Name"
    argv = ["--answerer", "reference", "--split", "dev", "--out", str(bad), "--note", "n"]
    assert eot.main(argv, parts=parts) == 2
    assert "is not a name" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("argv", "named"),
    [
        (["--answerer", "reference", "--split", "dev"], "a run needs --out, --note"),
        (
            ["--answerer", "reference", "--split", "dev", "--out", "x", "--note", "{{" + "X}}"],
            "placeholder",
        ),
        (
            [
                "--answerer",
                "reference",
                "--split",
                "dev",
                "--out",
                "x",
                "--note",
                "n",
                "--secondary",
            ],
            "--secondary is a dev run of the pipeline",
        ),
    ],
)
def test_the_flags_a_run_needs_together(
    argv: list[str], named: str, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit):
        eot.main(argv)
    assert named in capsys.readouterr().err


def test_the_settings_load_as_poe_evals_with_the_var_dir_on_top(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env = tmp_path / "made-up.env"
    env.write_text("T2V_TURNS__VAD_STOP_MS=300\n", encoding="utf-8")
    args = eot._parser().parse_args(["--env-file", str(env), "--var-dir", str(tmp_path / "v")])
    loaded = eot._settings(args)
    assert (loaded.turns.vad_stop_ms, loaded.storage.var_dir, loaded.env) == (
        300,
        tmp_path / "v",
        "dev",
    )
    monkeypatch.setattr(run_settings, "DOTENV", env)
    assert eot._settings(eot._parser().parse_args([])).turns.vad_stop_ms == 300


def test_the_hold_after_smart_turns_complete_is_set_and_shown_as_every_turn_setting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """E's arms (plan 005's amendment (8)) set `turns.complete_hold_ms` on the command line, as
    `T2V_TURNS__COMPLETE_HOLD_MS=500 uv run poe eot ...`, over the `.env`; the run's settings,
    which its scorecard and history line keep, name it."""
    env = tmp_path / "made-up.env"
    env.write_text("T2V_TURNS__COMPLETE_HOLD_MS=300\n", encoding="utf-8")
    args = eot._parser().parse_args(["--env-file", str(env)])
    assert eot.shown(eot._settings(args), args)["turns.complete_hold_ms"] == "300"
    monkeypatch.setenv("T2V_TURNS__COMPLETE_HOLD_MS", "500")
    loaded = eot._settings(args)
    assert (loaded.turns.complete_hold_ms, eot.shown(loaded, args)["turns.complete_hold_ms"]) == (
        500,
        "500",
    )

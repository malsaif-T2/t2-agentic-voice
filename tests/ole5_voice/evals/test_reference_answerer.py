"""Step 15 of plan 002, inside `poe check`: `poe eval --answerer reference` over each split of the
committed golden set scores 100%, with the real items, split, matcher and scorecard writer, and
sends nothing. A run scores only the variants the owner has confirmed (`items.unchecked`), and
none is confirmed before the owner's review (step 18), so each committed variant is given a
made-up confirmation here: every one of them is checked, as step 15 asks."""

from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest
from ole5_voice.evals import items, run
from ole5_voice.evals.items import EVALS
from ole5_voice.evals.models import Item, Split
from ole5_voice.evals.run_parts import Parts
from ole5_voice.evals.runs import SCORECARD_FILE, Scorecard
from ole5_voice.evals.split import load_split
from t2_agentic_voice import configure_logging

from tests.ole5_voice.evals.test_run_parts import make_world

MADE_UP_CONFIRMATION = {"at": datetime(2026, 11, 1, 12, 0, tzinfo=UTC), "review_pass": 1}


def _confirmed(folder: Path) -> tuple[Item, ...]:
    """The committed items, each variant with a made-up confirmation."""
    return tuple(
        Item.model_validate(
            item.model_dump()
            | {
                "variants": [
                    v.model_dump() | {"confirmations": [MADE_UP_CONFIRMATION]}
                    for v in item.variants
                ]
            }
        )
        for item in items.load_items(folder)
    )


@pytest.mark.parametrize("side", ["dev", "held-out"])
def test_the_reference_answerer_scores_every_committed_variant_right(
    side: Split, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    configure_logging("INFO", "console")
    world = make_world(tmp_path)
    shutil.copytree(EVALS / "golden", world.data / "golden")
    for name in ("split.json", "spelling.toml"):
        shutil.copy2(EVALS / name, world.data / name)
    out = world.main / "var" / "runs" / f"step-15-{side}"
    argv = ["--answerer", "reference", "--split", side, "--out", str(out), "--note", "step 15"]
    parts = Parts(folder=world.top, git=world.git, load_items=_confirmed)
    assert run.main(argv, parts=parts) == 0
    card = Scorecard.model_validate_json((out / SCORECARD_FILE).read_bytes())
    sides = load_split(EVALS / "split.json").items
    committed = items.load_items(EVALS / "golden")
    on_side = [v for i in committed if sides[i.id] == side for v in i.variants]
    totals = card.totals
    assert (card.complete, totals.variants, totals.right) == (True, len(on_side), len(on_side))
    assert (totals.accuracy, totals.failures, totals.requests, totals.cost_usd) == (1.0, 0, 0, 0.0)
    assert totals.wer in (0.0, None) and totals.cer in (0.0, None)
    assert totals.term_recall in (1.0, None) and totals.id_recall in (1.0, None)
    assert len(card.variants) == (len(on_side) if side == "dev" else 0)
    assert not (world.data / "history.jsonl").exists()  # a reference run spends nothing
    logged = capsys.readouterr().out
    assert "unchecked_left_out" in logged and f"of={len(on_side)}" in logged

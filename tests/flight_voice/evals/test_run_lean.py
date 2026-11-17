"""`poe eval-flights --agent lean` (flight_voice/evals/run.py, run_args.py) with a fake git, a
fake chat model and fake plays, as test_run.py runs it: each play is the lean play's, under the
lean settings path, and the run, its records, its scorecard and its history line name the lean
agent and hold its measures; a run with no `--agent` is the scripted agent's, as before."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from flight_voice.evals.call import PlayRead
from flight_voice.evals.lean_call import LeanRead
from flight_voice.evals.run import RunParts, main
from flight_voice.evals.scenarios import Scenario
from t2_agentic_voice import VoiceSettings
from t2_agentic_voice.evals import FunctionLLM, ScriptedLLM
from t2_agentic_voice.ports import ChatModel

from tests.flight_voice.evals.test_run import NOW, TWO, Plays, Tree


class LeanPlays(Plays):
    """The fake play of test_run.py, its read a lean one booked at its second caller turn."""

    def __init__(self) -> None:
        super().__init__()
        self.yes_held: list[bool] = []

    async def __call__(
        self, scenario: Scenario, llm: ChatModel, settings: VoiceSettings
    ) -> PlayRead:
        read = await super().__call__(scenario, llm, settings)
        self.yes_held.append(settings.interruptions.yes_over_read_back)
        return LeanRead(
            turns=read.turns,
            violations=read.violations,
            failure=read.failure,
            booked_turns=2,
            booked_index=1,
            booked_s=12.5,
        )


def _lines(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _run(tree: Tree, scripted: Plays, lean: Plays, *extra: str) -> int:
    async def nap(seconds: float) -> None:
        return None

    parts = RunParts(
        folder=tree.top,
        git=tree.git,
        chat=lambda env_file: FunctionLLM(lambda request: ScriptedLLM.reply("-")),
        play=scripted,
        lean=lean,
        now=lambda: NOW,
        sleep=nap,
    )
    out = tree.main / "var" / "runs" / "f-dev-lean-1"
    return main(["--split", "dev", "--out", str(out), "--repeats", "1", *extra], parts=parts)


def test_a_lean_run_plays_the_lean_agent_and_names_it(tmp_path: Path) -> None:
    tree, scripted, lean = Tree(tmp_path), Plays(), LeanPlays()
    assert _run(tree, scripted, lean, "--agent", "lean") == 0
    assert scripted.played == [] and lean.played == [TWO[0], *TWO]
    assert lean.yes_held == [False, False, False]  # the lean settings path
    out = tree.main / "var" / "runs" / "f-dev-lean-1"
    assert json.loads((out / "run.json").read_text(encoding="utf-8"))["agent"] == "lean"
    records = _lines(out / "plays.jsonl")
    measured = [r["measures"] for r in records if not r["smoke"]]
    assert all(m["turns_to_booking"] == 2 and m["seconds_to_booking"] == 12.5 for m in measured)
    card = json.loads((out / "scorecard.json").read_text(encoding="utf-8"))
    assert card["run"]["agent"] == "lean"
    assert card["scenarios"][0]["measures"]["turns_to_booking"] == 2
    assert "the lean agent" in (out / "scorecard.md").read_text(encoding="utf-8")
    (line,) = _lines(tree.history)
    assert line["agent"] == "lean"


def test_a_run_with_no_agent_named_is_the_scripted_agents(tmp_path: Path) -> None:
    tree, scripted, lean = Tree(tmp_path), Plays(), LeanPlays()
    assert _run(tree, scripted, lean) == 0
    assert lean.played == [] and scripted.played == [TWO[0], *TWO]
    (line,) = _lines(tree.history)
    assert line["agent"] == "scripted"

"""`poe eval-flights` (flight_voice/evals/run.py) with a fake git, a fake chat model and a fake
play, in a made-up tree with two of the dev scenarios: nothing is sent. A dev run plays the smoke
play, then every scenario once and again until each has its repeats, and writes the records,
the scorecard and one history line the library's day counter reads; it refuses, before anything
is sent, the main checkout, a dirty tree, an out folder inside the worktree or in use, and an
estimate past the cap; a smoke play that breaks a rule stops it; and a run stopped at the cap
goes on with --resume once its history line is committed, each play played once, and a resume
that differs is refused: in its command line, or at a commit that changed more than the run
histories. Named, `--split held-out` lists the committed held-out set, each scenario that
plays once a repeat and the one that waits skipped, behind the dev smoke play (the fake play
alone: no held-out scenario is played here). The fake git's HEAD moves on with each fake
commit, and its tree is dirty while the history file holds a line not committed."""

from __future__ import annotations

import json
import shutil
from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest
from flight_voice.evals import run_setup
from flight_voice.evals.call import PlayRead
from flight_voice.evals.folder import LOCK_FILE
from flight_voice.evals.run import RunParts, main
from flight_voice.evals.scenarios import CALLS, Scenario, load
from t2_agentic_voice import ConfigurationError, InvalidRequestError, VoiceSettings
from t2_agentic_voice.agent.turn import MAX_REQUESTS
from t2_agentic_voice.evals import FunctionLLM, GitResult, PacedChat, ScriptedLLM, requests_today
from t2_agentic_voice.ports import ChatModel

COMMIT = "a" * 40
NOW = datetime(2026, 11, 16, 9, 0, tzinfo=UTC)
TWO = ("f01_round_trip_saudi", "f02_one_way_english")


class Tree:
    """A main checkout with a linked worktree in it, as a fake git describes them: its commits
    in order, each with the files it changed, and the history file as last committed."""

    def __init__(self, root: Path, *, dirty: bool = False) -> None:
        self.main = root / "main"
        self.top = self.main / ".claude" / "worktrees" / "run"
        self.dirty = dirty
        self.commits: list[tuple[str, tuple[str, ...]]] = [(COMMIT, ())]
        self.saved: bytes | None = None
        calls = self.top / run_setup.CALLS
        calls.mkdir(parents=True)
        for name in TWO:
            shutil.copy(CALLS / f"{name}.toml", calls / f"{name}.toml")
        (self.main / "var" / "runs").mkdir(parents=True)

    def git(self, args: Sequence[str], cwd: Path) -> GitResult:
        if "--show-toplevel" in args:
            inside = cwd.resolve().is_relative_to(self.top.resolve())
            return GitResult(0, f"{self.top if inside else self.main}\n")
        if args[0] == "worktree":
            return GitResult(0, f"worktree {self.main}\0HEAD x\0\0worktree {self.top}\0HEAD x\0\0")
        if "HEAD" in args:
            return GitResult(0, self.commits[-1][0] + "\n")
        if "status" in args:
            return GitResult(0, " M x\0" if self.dirty or self._unsaved() else "")
        heads = [head for head, _ in self.commits]
        if args[:2] == ["merge-base", "--is-ancestor"]:
            return GitResult(0 if heads.index(args[2]) <= heads.index(args[3]) else 1, "")
        if args[:3] == ["diff", "--name-only", "-z"]:
            since = self.commits[heads.index(args[3]) + 1 : heads.index(args[4]) + 1]
            return GitResult(0, "".join(f"{name}\0" for _, names in since for name in names))
        if args[0] == "check-ignore":
            ignored = Path(args[-1]).is_relative_to((self.main / "var").resolve())
            return GitResult(0 if ignored else 1, "")
        raise AssertionError(f"an unexpected git command: {args}")

    @property
    def history(self) -> Path:
        return self.top / run_setup.HISTORY

    def _unsaved(self) -> bool:
        return self.history.exists() and self.history.read_bytes() != self.saved

    def commit(self, *also: str) -> str:
        """A fake commit of the history file, and of the files `also` names; its HEAD."""
        self.saved = self.history.read_bytes() if self.history.exists() else None
        head = f"{len(self.commits):x}" * 40
        self.commits.append((head, (run_setup.HISTORY.as_posix(), *also)))
        return head


class Plays:
    """A fake play: each scenario's id kept, an empty play returned; optionally the paced
    model stopped at the `stop_at`th play, or a violation on every play."""

    def __init__(self, *, stop_at: int | None = None, violations: tuple[str, ...] = ()) -> None:
        self.played: list[str] = []
        self.models: set[str] = set()
        self.stop_at, self.violations = stop_at, violations

    async def __call__(
        self, scenario: Scenario, llm: ChatModel, settings: VoiceSettings
    ) -> PlayRead:
        self.played.append(scenario.id)
        if self.stop_at is not None and len(self.played) == self.stop_at:
            assert isinstance(llm, PacedChat)
            llm.stopped = "cap"
        self.models.add(settings.llm.model)
        return PlayRead(turns=(None,) * len(scenario.turns), violations=self.violations)


def _parts(tree: Tree, plays: Plays, *, folder: Path | None = None) -> RunParts:
    async def nap(seconds: float) -> None:
        return None

    return RunParts(
        folder=tree.top if folder is None else folder,
        git=tree.git,
        chat=lambda env_file: FunctionLLM(lambda request: ScriptedLLM.reply("-")),
        play=plays,
        now=lambda: NOW,
        sleep=nap,
    )


def _run(tree: Tree, plays: Plays, *extra: str, out: Path | None = None, **options: Any) -> int:
    target = tree.main / "var" / "runs" / "f-dev-1" if out is None else out
    argv = ["--split", "dev", "--out", str(target), *extra]
    return main(argv, parts=_parts(tree, plays, **options))


def _lines(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def test_a_dev_run_plays_the_smoke_play_then_each_scenario_its_repeats(tmp_path: Path) -> None:
    tree, plays = Tree(tmp_path), Plays()
    assert _run(tree, plays) == 0
    assert plays.played == [TWO[0], *TWO * 3]
    out = tree.main / "var" / "runs" / "f-dev-1"
    records = _lines(out / "plays.jsonl")
    assert [(r["scenario"], r["repeat"]) for r in records] == [
        (name, repeat) for repeat in (1, 2, 3) for name in TWO
    ]
    card = json.loads((out / "scorecard.json").read_text(encoding="utf-8"))
    assert card["complete"] and card["held"] and card["totals"]["plays"] == 6
    # Nothing was said, so every check of each play failed: no scenario passed.
    assert [c["passed"] for c in card["scenarios"]] == [False, False]
    assert "| f01_round_trip_saudi | 3 | 0 | failed |" in (out / "scorecard.md").read_text("utf-8")
    (line,) = _lines(tree.history)
    assert line["kind"] == "flights" and line["complete"] and _lines(out / "history.jsonl")
    assert requests_today([tree.history], date(2026, 11, 16)) == {}  # nothing was sent
    assert not (out / LOCK_FILE).exists()


def test_the_held_out_split_named_lists_the_committed_held_out_set(tmp_path: Path) -> None:
    tree, plays = Tree(tmp_path), Plays()
    calls = tree.top / run_setup.CALLS
    for path in CALLS.glob("*.toml"):
        shutil.copy(path, calls / path.name)
    held_out = [s for s in load() if s.split == "held-out"]
    waits = [s.id for s in held_out if run_setup.waiting(s)]
    out = tree.main / "var" / "runs" / "f-held-out-1"
    assert _run(tree, plays, "--split", "held-out", "--repeats", "1", out=out) == 0
    run = json.loads((out / "run.json").read_text(encoding="utf-8"))
    assert run["split"] == "held-out" and run["data"] == [s.id for s in held_out]
    assert plays.played == [TWO[0], *(s.id for s in held_out if s.id not in waits)]
    card = json.loads((out / "scorecard.json").read_text(encoding="utf-8"))
    assert (
        [c["id"] for c in card["scenarios"] if c["skipped"]]
        == waits
        == ["h06_switch_at_read_back_saudi"]
    )


@pytest.mark.parametrize(
    ("given", "dirty"),
    [("main", False), ("worktree", True)],
)
def test_the_main_checkout_and_a_dirty_tree_are_refused(
    tmp_path: Path, given: str, dirty: bool
) -> None:
    tree, plays = Tree(tmp_path, dirty=dirty), Plays()
    folder = tree.main if given == "main" else tree.top
    assert _run(tree, plays, folder=folder) == 2
    assert plays.played == [] and not (tree.main / "var" / "runs" / "f-dev-1").exists()


def test_an_out_folder_inside_the_worktree_or_in_use_is_refused(tmp_path: Path) -> None:
    tree, plays = Tree(tmp_path), Plays()
    assert _run(tree, plays, out=tree.top / "var" / "runs" / "f-dev-1") == 2
    assert _run(tree, Plays(stop_at=2)) == 1
    tree.commit()
    out = tree.main / "var" / "runs" / "f-dev-1"
    (out / LOCK_FILE).write_bytes(b"")
    assert _run(tree, plays, "--resume") == 2
    assert plays.played == []


def test_the_estimate_past_the_cap_is_refused_before_anything_is_sent(tmp_path: Path) -> None:
    tree, plays = Tree(tmp_path), Plays()
    assert _run(tree, plays, "--cap-usd", "0.001") == 2
    assert plays.played == [] and not (tree.main / "var" / "runs" / "f-dev-1").exists()


def test_a_model_with_no_price_or_limits_is_refused(tmp_path: Path) -> None:
    tree, plays = Tree(tmp_path), Plays()
    other = ("--model", "llama-3.3-70b-versatile")
    priced = ("--price", "llama-3.3-70b-versatile=0.59/0.79")
    limited = ("--limits", "llama-3.3-70b-versatile=30/100000/1000")
    assert _run(tree, plays, *other) == 2
    assert _run(tree, plays, *other, *priced) == 2
    assert plays.played == []
    assert _run(tree, plays, *other, *priced, *limited) == 0
    assert plays.models == {"llama-3.3-70b-versatile"}


def test_a_smoke_play_that_breaks_a_rule_stops_the_run(tmp_path: Path) -> None:
    tree, plays = Tree(tmp_path), Plays(violations=("rule A: a claim",))
    assert _run(tree, plays) == 1
    assert plays.played == [TWO[0]]
    card = json.loads(
        (tree.main / "var" / "runs" / "f-dev-1" / "scorecard.json").read_text("utf-8")
    )
    assert card["stopped"] == "smoke_failed" and not card["held"] and not card["complete"]


def test_a_run_stopped_at_the_cap_goes_on_with_resume_each_play_once(tmp_path: Path) -> None:
    tree, first = Tree(tmp_path), Plays(stop_at=3)
    assert _run(tree, first) == 1
    assert first.played == [TWO[0], TWO[0], TWO[1]]  # the third play's record is dropped
    assert _run(tree, Plays(), "--resume") == 2  # the history line not committed: dirty
    later = tree.commit()
    assert _run(tree, Plays(), "--resume", "--repeats", "2") == 2  # differs: refused
    again = Plays()
    assert _run(tree, again, "--resume") == 0
    assert again.played == [TWO[0], TWO[1], *TWO, *TWO]
    out = tree.main / "var" / "runs" / "f-dev-1"
    records = _lines(out / "plays.jsonl")
    assert sorted((r["scenario"], r["repeat"]) for r in records) == sorted(
        (name, repeat) for repeat in (1, 2, 3) for name in TWO
    )
    sessions = _lines(out / "sessions.jsonl")
    assert [(s["stopped"], s["commit"]) for s in sessions] == [("cap", COMMIT), (None, later)]
    assert json.loads((out / "run.json").read_text(encoding="utf-8"))["commit"] == COMMIT
    assert [line["session"] for line in _lines(tree.history)] == [1, 2]


def test_a_resume_at_a_commit_that_changed_more_than_the_histories_is_refused(
    tmp_path: Path,
) -> None:
    tree = Tree(tmp_path)
    assert _run(tree, Plays(stop_at=3)) == 1
    tree.commit("apps/flight-voice-agent/src/flight_voice/agent.py")
    plays = Plays()
    assert _run(tree, plays, "--resume") == 2
    assert plays.played == []


def test_the_estimate_counts_each_model_request_a_play_may_send() -> None:
    assert run_setup.TALKER_REQUESTS == MAX_REQUESTS
    (f01,) = [s for s in load() if s.id == TWO[0]]
    settings = run_setup.call_settings("openai/gpt-oss-120b", "medium")
    asked = run_setup.asks(f01, settings)
    # Four turns: three talker requests each; the yes said over the closing question is said
    # over the agent and answers the read-back.
    assert [(model, n) for model, n, _ in asked] == [
        ("openai/gpt-oss-120b", 12),
        (run_setup.OVERLAP.model, 1),
        (run_setup.CHECK.model, 1),
    ]


def test_a_set_that_breaks_a_rule_is_refused_but_the_missing_held_out_set(tmp_path: Path) -> None:
    folder = tmp_path / "calls"
    folder.mkdir()
    shutil.copy(CALLS / f"{TWO[0]}.toml", folder / f"{TWO[0]}.toml")
    assert [s.id for s in run_setup.checked_scenarios(folder)] == [TWO[0]]
    text = (CALLS / f"{TWO[1]}.toml").read_text(encoding="utf-8")
    broken = text.replace('depart = "2026-11-17"', 'depart = "2026-11-18"')
    (folder / f"{TWO[1]}.toml").write_bytes(broken.encode("utf-8"))
    with pytest.raises(InvalidRequestError, match=r"break 2 rule\(s\), first: f02.*FIX: write"):
        run_setup.checked_scenarios(folder)


def test_a_failed_smoke_plays_violations_stay_counted_when_the_run_goes_on(tmp_path: Path) -> None:
    tree = Tree(tmp_path)
    assert _run(tree, Plays(violations=("rule A: a claim",))) == 1
    tree.commit()
    assert _run(tree, Plays(), "--resume") == 0
    out = tree.main / "var" / "runs" / "f-dev-1"
    card = json.loads((out / "scorecard.json").read_text(encoding="utf-8"))
    assert card["complete"] and not card["held"] and card["totals"]["violations"] == 1


def test_a_chat_model_that_cannot_be_built_is_refused_before_the_folder_is_made(
    tmp_path: Path,
) -> None:
    tree, plays = Tree(tmp_path), Plays()

    def no_key(env_file: Path | None) -> ChatModel:
        raise ConfigurationError("GROQ_API_KEY is not set. FIX: set it.")

    parts = replace(_parts(tree, plays), chat=no_key)
    out = tree.main / "var" / "runs" / "f-dev-1"
    assert main(["--split", "dev", "--out", str(out)], parts=parts) == 2
    assert plays.played == [] and not out.exists()

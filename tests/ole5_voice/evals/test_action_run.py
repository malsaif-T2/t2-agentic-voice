"""`poe eval-actions` (action_run.py), run A, end to end on fakes only: the committed scenarios
played through the library's `TextCall` (on its virtual clock) with Ole5's agent on a mock
ticket system each play, its talker on the oracle's `FunctionLLM` (action_run_support.py); a
smoke test first; each scenario of the split three times, evenly; a dev run's records, mocks
and scorecard, a held-out run's aggregates only; a stopped run resumed; a violation that fails
the run though the card keeps no play of it (the smoke test's, an unfinished held-out run's);
the shared history's line; and what a run refuses before anything is sent, its dry estimate
past the cap among them."""

from __future__ import annotations

import dataclasses
import json
from collections import Counter
from pathlib import Path
from typing import Any

import pytest
from ole5_voice.evals import action_run, run_folder
from ole5_voice.evals.action_card import ActionScorecard
from ole5_voice.evals.action_history import ActionLine
from ole5_voice.evals.action_scenarios import ACTIONS_DIR
from ole5_voice.evals.history import read_history
from ole5_voice.evals.items import HISTORY_FILE
from ole5_voice.evals.run_folder import RESULTS_FILE
from ole5_voice.evals.run_parts import DATA
from ole5_voice.evals.runs import SCORECARD_FILE
from t2_agentic_voice import ProviderError
from t2_agentic_voice.evals import TextCall

from tests.ole5_voice.evals.action_run_support import (
    JUDGE,
    NO_TICKETS,
    TALKER,
    ActionSetup,
    committed,
    make_action_setup,
    said,
    virtual,
)

DEV = [scenario.id for scenario in committed() if scenario.split == "dev"]
HELD_OUT = [scenario.id for scenario in committed() if scenario.split == "held-out"]


@pytest.fixture
def setup(tmp_path: Path) -> ActionSetup:
    return make_action_setup(tmp_path)


def _main(setup: ActionSetup, *extra: str, out: str = "a-dev", split: str = "dev") -> int:
    return action_run.main([*setup.argv(*extra, out=out, split=split)], parts=setup.parts())


def _card(setup: ActionSetup, out: str = "a-dev") -> ActionScorecard:
    return ActionScorecard.model_validate_json((setup.out(out) / SCORECARD_FILE).read_bytes())


def test_a_dev_run_plays_each_scenario_three_times_evenly_after_a_smoke_test(
    setup: ActionSetup,
) -> None:
    assert _main(setup) == 0
    card = _card(setup)
    plays = 3 * len(DEV)  # each of dev's 25 scenarios three times
    assert card.complete and len(card.plays) == plays == 75 and card.run.repeats == 3
    order = [
        json.loads(line)["scenario"]
        for line in (setup.out() / RESULTS_FILE).read_text("utf-8").splitlines()
    ]
    assert order == DEV * 3
    assert setup.oracle.heard[0] == committed()[0].turns[0].says  # the smoke test's, first
    kept = {path.name for path in (setup.out() / "plays").iterdir()}  # each mock that was used
    made = {f"{play.scenario}-r{play.repeat}" for play in card.plays if play.made}
    assert made and made <= kept and f"smoke-{DEV[0]}" in kept
    assert "a11_no_english-r1" not in kept  # a mock that made and held nothing made no folder
    assert [count.needed for count in card.scenarios if count.scenario.startswith("a05")] == [3]
    ((line, _), (copy, _)) = setup.lines.lines
    assert isinstance(line, ActionLine) and line == copy and line.split == "dev"
    assert line.plays == plays and line.requests[TALKER] > plays and line.requests[JUDGE] > plays
    assert line.estimate_usd == card.run.estimate_usd > 0
    assert line.stray_characters == card.totals.stray_characters == 0  # the oracle writes none


def test_a_held_out_run_keeps_its_aggregates_only(setup: ActionSetup) -> None:
    assert _main(setup, "--repeats", "1", out="a-held-out", split="held-out") == 0
    card = _card(setup, "a-held-out")
    assert card.complete and card.plays == () and card.scenarios == ()
    assert card.totals.plays + card.totals.failures == len(HELD_OUT)
    assert not (setup.out("a-held-out") / RESULTS_FILE).exists()
    assert not (setup.out("a-held-out") / "plays").exists()
    ((line, _), _) = setup.lines.lines
    assert isinstance(line, ActionLine) and line.split == "held-out" and line.passed == {}
    assert line.stray_characters == card.totals.stray_characters == 0  # the total, held-out's too
    assert setup.oracle.heard[0] == committed()[0].turns[0].says  # its smoke test is dev's


def test_the_smoke_test_alone_with_the_registered_model_effort_and_cap(setup: ActionSetup) -> None:
    assert _main(setup, "--smoke-only") == 0
    card = _card(setup)
    assert card.complete and len(card.plays) == 1 and card.passed is None
    assert card.run.model == "openai/gpt-oss-120b" and card.run.cap_usd == 10.0
    assert card.run.settings["llm.reasoning_effort"] == "medium"


def test_a_smoke_test_that_fails_stops_the_run(setup: ActionSetup) -> None:
    smoke = committed()[0]
    setup.oracle.says[smoke.turns[0].says] = [ProviderError("rejected", False)]
    assert _main(setup) == 1
    card = _card(setup)
    assert card.stopped == "smoke_failed" and card.plays == ()
    assert set(setup.oracle.heard) <= {turn.says for turn in smoke.turns}  # nothing played after


def test_the_days_limit_stops_a_run_which_resume_goes_on_with(setup: ActionSetup) -> None:
    today = Counter({TALKER: 9_980})
    parts = dataclasses.replace(setup.parts(), requests_today=lambda path, day: today)
    argv = setup.argv("--repeats", "1")
    assert action_run.main(argv, parts=parts) == 1
    first = _card(setup)
    assert first.stopped == "daily_limit" and 0 < len(first.plays) < len(DEV)
    today[TALKER] = 0
    assert action_run.main([*argv, "--resume"], parts=parts) == 0
    card = _card(setup)
    assert card.complete and len(card.plays) == len(DEV) and len(card.sessions) == 2


def test_an_interrupt_keeps_what_was_played(setup: ActionSetup) -> None:
    calls: list[str] = []

    def interrupted(agent: Any, **given: Any) -> TextCall:
        calls.append(agent.name)
        if len(calls) == 3:
            raise KeyboardInterrupt
        return virtual(agent, **given)

    setup.call = interrupted
    assert _main(setup) == 1
    card = _card(setup)
    assert card.stopped == "interrupted" and len(card.plays) == 1 and card.passed is None


def _unscripted(setup: ActionSetup, scenario: str) -> None:
    """`scenario`'s yes, in the run's data, scripted as a turn the session asks again after,
    and a yes with the send word after it: the session confirms the write all the same, on a
    turn its script gives no yes."""
    path = next((setup.world.top / DATA / ACTIONS_DIR).glob(f"{scenario}_*.toml"))
    text = path.read_text("utf-8")
    assert 'outcome = "done"' in text
    sent = '\n[[turns]]\nsays = "إيه أرسلها"\noutcome = "done"\n'
    changed = text.replace('outcome = "done"', 'outcome = "asked_again"', 1)
    path.write_text(changed + sent, encoding="utf-8")


def test_a_smoke_test_that_breaks_the_hard_constraint_fails_the_run_resumed_or_not(
    setup: ActionSetup,
) -> None:
    _unscripted(setup, "a01")
    argv = setup.argv("--repeats", "1")
    assert action_run.main(argv, parts=setup.parts()) == 1
    first = _card(setup)
    assert first.stopped == "smoke_failed" and first.plays == () and first.totals.violations
    assert first.held is False and first.passed is False
    smoke = committed()[0].turns[0].says
    setup.oracle.says[smoke] = said("طيب.")  # no read-back, so nothing is confirmed
    assert action_run.main([*argv, "--resume"], parts=setup.parts()) == 0
    card = _card(setup)
    assert card.complete and len(card.plays) == len(DEV) and card.passed is False
    played = sum(len(play.violations) for play in card.plays)
    assert card.totals.violations == first.totals.violations + played and card.held is False


def test_a_held_out_run_that_does_not_finish_keeps_its_violations(setup: ActionSetup) -> None:
    _unscripted(setup, HELD_OUT[0][:3])
    calls: list[str] = []

    def interrupted(agent: Any, **given: Any) -> TextCall:
        calls.append(agent.name)
        if len(calls) == 3:  # the smoke test, the first held-out play, then the next
            raise KeyboardInterrupt
        return virtual(agent, **given)

    setup.call = interrupted
    assert _main(setup, "--repeats", "1", out="a-held-out", split="held-out") == 1
    card = _card(setup, "a-held-out")
    assert card.stopped == "interrupted" and card.totals.plays + card.totals.failures == 0
    assert card.totals.violations and card.held is False and card.passed is False
    ((line, _), _) = setup.lines.lines
    assert isinstance(line, ActionLine) and line.violations == card.totals.violations


def test_the_shared_history_takes_run_as_line_and_reads_it_back(setup: ActionSetup) -> None:
    parts = dataclasses.replace(
        setup.parts(),
        history_accepts=run_folder.history_accepts,
        append_line=run_folder.append_shared,
    )
    assert action_run.main([*setup.argv(), "--smoke-only"], parts=parts) == 0
    (line,) = read_history(setup.world.top / DATA / HISTORY_FILE)
    assert getattr(line, "kind", None) == "actions" and getattr(line, "complete", None) is True


@pytest.mark.parametrize(
    ("change", "words"),
    [
        ("drop", "the scenarios break"),
        ("break", "the scenarios cannot be read"),
        ("history", "takes no line of run A's kind yet"),
        ("held-out", "held-out is read once"),
        ("cap", "passes --cap-usd 0.5"),
        ("agent", "the agent has no tool create_ticket"),
        ("checkout", "the worktree has changes"),
        ("out", "exists"),
        ("prices", "--price names nothing for llama-3.3-70b-versatile"),
    ],
)
def test_what_a_run_refuses_before_anything_is_sent(
    setup: ActionSetup, change: str, words: str, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = setup.world.top / DATA / ACTIONS_DIR
    if change == "drop":
        next(folder.glob("a30_*.toml")).unlink()
    if change == "break":
        next(folder.glob("a30_*.toml")).write_text("id = 1\n", encoding="utf-8")
    setup.accepts = change != "history"
    setup.held_out_run = change == "held-out"
    extra = ["--cap-usd", "0.5"] if change == "cap" else []
    argv = setup.argv(*extra, split="held-out" if change == "held-out" else "dev")
    if change == "agent":
        argv[argv.index("--agent") + 1] = NO_TICKETS
    if change == "prices":
        price = argv.index(f"{JUDGE}=0.59/0.79")
        del argv[price - 1 : price + 1]
    setup.world.git.dirty = change == "checkout"
    if change == "out":
        setup.out().mkdir(parents=True)
    assert action_run.main(argv, parts=setup.parts()) == 2
    assert words in capsys.readouterr().out and setup.chat.requests == []
    assert not (setup.out() / SCORECARD_FILE).exists()


@pytest.mark.parametrize(
    ("extra", "words"),
    [
        (["--repeats", "0"], "must be 1 or more"),
        (["--resume", "--smoke-only"], "no --smoke-only"),
        (["--points-text", "points.jsonl"], "no --points-text"),
        (["--arm", "A"], "--arm is not a name"),
        (["--judge-model", TALKER], "other than the talker's"),
    ],
)
def test_the_command_line_refuses_what_a_run_cannot_be(
    setup: ActionSetup, extra: list[str], words: str, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit):
        _main(setup, *extra)
    assert words in capsys.readouterr().err
    with pytest.raises(SystemExit):
        _main(setup, "--resume", split="held-out")
    assert "one whole session" in capsys.readouterr().err
    with pytest.raises(SystemExit):
        action_run.main(["--split", "dev"], parts=setup.parts())
    assert "a run needs" in capsys.readouterr().err

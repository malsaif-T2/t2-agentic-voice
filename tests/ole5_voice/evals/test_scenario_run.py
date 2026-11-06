"""`poe eval-scenarios` (scenario_run.py, scenario_score.py), run S, on fakes only: ten made-up
scripted calls, each played three times, checked turn by turn (the tool called or not, the
earlier reply cut or its search cancelled, the language, the words, the judge's checks), each
scenario counted against its target (the rehearsal's 3 of 3, the others 2 of 3); a smoke test
first; a stopped run resumed; refusals before anything is sent."""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest
from ole5_voice.evals import scenario_run
from ole5_voice.evals.judge import Checked
from ole5_voice.evals.run_folder import RESULTS_FILE
from ole5_voice.evals.runs import SCORECARD_FILE
from ole5_voice.evals.scenario_score import (
    PlayRecord,
    ScenarioScorecard,
    TurnCheck,
    checks_of,
    needed,
)
from ole5_voice.evals.scenarios import ScriptTurn
from ole5_voice.evals.talker_data import HeardTurn, ToolUse
from ole5_voice.evals.talker_lines import ScenarioLine
from pydantic import ValidationError
from t2_agentic_voice import ProviderError

from tests.ole5_voice.evals.talker_fakes import TALKER, TOOL, Scripted
from tests.ole5_voice.evals.talker_support import Setup, make_setup


def write_scenarios(data: Path, count: int = 10) -> None:
    """`count` made-up scenarios, the first six the rehearsal's: the first with a stop over its
    reply and a go-on, the second with a correction while its search runs."""
    folder = data / "scenarios"
    folder.mkdir()
    for n in range(1, count + 1):
        lines = [f'id = "s{n:02d}"', f"rehearsal = {str(n <= 6).lower()}"]
        lines += ['language = "en"', 'notes = "Made up."', "", "[[turns]]"]
        lines += [f'says = "question {n}"', "search = true", 'language = "en"', 'item = "a1"']
        if n == 1:
            lines += ["", "[[turns]]", 'says = "stop 1"', 'when = "agent_speaking"']
            lines += ["after_s = 1.0", "cuts_reply = true", "search = false", "max_words = 6"]
            lines += ["", "[[turns]]", 'says = "go on 1"', 'follows = "continues"']
        if n == 2:
            lines += ["", "[[turns]]", 'says = "correction 2"', 'when = "tool_running"']
            lines += ["cancels_search = true", 'facts = ["It answers the correction."]']
        (folder / f"s{n:02d}.toml").write_text("\n".join(lines) + "\n", encoding="utf-8")


@pytest.fixture
def setup(tmp_path: Path) -> Setup:
    found = make_setup(tmp_path)
    write_scenarios(found.data)
    found.calls.script["stop 1"] = Scripted(cuts_earlier=True, search=False, said="Okay.")
    found.calls.script["go on 1"] = Scripted(search=False)
    found.calls.script["correction 2"] = Scripted(cancels_search=True)
    return found


def _card(setup: Setup) -> ScenarioScorecard:
    return ScenarioScorecard.model_validate_json((setup.out("s-a") / SCORECARD_FILE).read_bytes())


def _main(setup: Setup, *extra: str) -> int:
    return scenario_run.main([*setup.argv(out="s-a"), *extra], parts=setup.parts())


def test_each_scenario_is_played_three_times_and_counted_against_its_target(setup: Setup) -> None:
    assert _main(setup) == 0
    card = _card(setup)
    assert card.complete and card.targets_met is True and len(card.plays) == 30
    assert [c.needed for c in card.scenarios] == [3] * 6 + [2] * 4
    first = next(play for play in card.plays if play.scenario == "s01")
    assert [check.cut for check in first.checks] == [None, True, None]
    assert first.checks[1].words is True and first.checks[2].judged == (True,)
    second = next(play for play in card.plays if play.scenario == "s02")
    assert second.checks[1].cancelled is True
    # The plays go round the scenarios: every one once, then again.
    order = [
        json.loads(line)["scenario"]
        for line in (setup.out("s-a") / RESULTS_FILE).read_text("utf-8").splitlines()
    ]
    assert order[:10] == [f"s{n:02d}" for n in range(1, 11)] and order[10] == "s01"
    ((line, _), _) = setup.lines.lines
    assert isinstance(line, ScenarioLine) and line.plays == 30 and line.targets_met is True
    assert line.passed["s01"] == 3 and line.requests[TALKER] > 30
    assert ("stop 1", "agent_speaking", None, "en") in setup.calls.said
    assert ("correction 2", None, "tool_running", "en") in setup.calls.said
    assert setup.calls.advanced[:1] == [1.0]


def test_a_rehearsal_scenario_must_pass_every_play_and_another_two_of_three(setup: Setup) -> None:
    setup.chat.failing["question 1"] = 2  # the smoke test's play, then the first counted
    setup.chat.failing["question 8"] = 1
    assert _main(setup) == 0
    counts = {count.scenario: count for count in _card(setup).scenarios}
    assert counts["s01"].passed == 2 and counts["s01"].met is False
    assert counts["s08"].passed == 2 and counts["s08"].met is True
    assert _card(setup).targets_met is False


def test_a_play_with_no_result_leaves_its_scenario_without_a_verdict(setup: Setup) -> None:
    setup.calls.script["question 9"] = Scripted(error=ProviderError("timeout", True))
    setup.calls.script["question 10"] = Scripted(violations=1)
    setup.calls.script["question 7"] = Scripted(search=False)
    assert _main(setup) == 0
    card = _card(setup)
    counts = {count.scenario: count for count in card.scenarios}
    assert counts["s09"].failures == 3 and counts["s09"].met is None
    assert counts["s10"].passed == 0 and card.violations == 3
    assert counts["s07"].passed == 0  # it should have searched
    assert card.targets_met is None


def test_a_judge_with_no_valid_answer_is_a_failure(setup: Setup) -> None:
    setup.calls.script["question 3"] = Scripted()
    original = setup.chat._checks

    def broken(asked: str) -> list[dict[str, object]]:
        found = original(asked)
        return found[:-1] if "question 3" in asked else found

    setup.chat._checks = broken  # type: ignore[method-assign]
    assert _main(setup) == 0
    plays = [play for play in _card(setup).plays if play.scenario == "s03"]
    assert {play.failure for play in plays} == {"judge"}


def test_a_failed_search_or_a_stuck_play_is_counted_apart(setup: Setup) -> None:
    setup.kb.failing.add("question 4")
    setup.calls.script["question 5"] = Scripted(delay_s=0.3)
    assert _main(setup, "--variant-timeout-s", "0.05") == 0
    counts = {count.scenario: count for count in _card(setup).scenarios}
    assert counts["s04"].failures == 3 and counts["s05"].failures == 3
    failures = {play.failure for play in _card(setup).plays if play.scenario in ("s04", "s05")}
    assert failures == {"provider", "stuck"}


def test_a_smoke_test_that_fails_stops_the_run(setup: Setup) -> None:
    setup.calls.script["question 1"] = Scripted(error=ProviderError("server_error", True))
    assert _main(setup) == 1
    card = _card(setup)
    assert card.stopped == "smoke_failed" and card.plays == () and len(setup.calls.said) == 1


def test_the_smoke_test_alone(setup: Setup) -> None:
    assert _main(setup, "--smoke-only") == 0
    card = _card(setup)
    assert card.complete and len(card.plays) == 1 and card.targets_met is None


def test_the_days_limit_stops_a_run_which_resume_goes_on_with(setup: Setup) -> None:
    setup.today[TALKER] = 980
    assert _main(setup) == 1
    first = _card(setup)
    assert first.stopped == "daily_limit" and 0 < len(first.plays) < 30
    setup.today[TALKER] = 0
    assert _main(setup, "--resume") == 0
    card = _card(setup)
    assert card.complete and len(card.plays) == 30 and len(card.sessions) == 2


def test_an_interrupt_or_an_error_keeps_what_was_played(setup: Setup) -> None:
    setup.calls.script["question 4"] = Scripted(error=KeyboardInterrupt())
    assert _main(setup) == 1
    assert _card(setup).stopped == "interrupted" and len(_card(setup).plays) == 3


def test_an_error_is_raised_once_the_scorecard_is_written(setup: Setup) -> None:
    setup.calls.script["question 4"] = Scripted(error=RuntimeError("made up"))
    with pytest.raises(RuntimeError):
        _main(setup)
    assert _card(setup).stopped == "error"


def test_the_cap_stops_a_run(setup: Setup) -> None:
    setup.chat.input_tokens = 3000
    assert scenario_run.main([*setup.argv(out="s-a", cap="0.05")], parts=setup.parts()) == 1
    assert _card(setup).stopped == "cap"


@pytest.mark.parametrize(
    ("change", "words"),
    [
        ("drop", "the scenarios break 1 rule(s)"),
        ("break", "the scenarios cannot be read"),
        ("history", "takes no line of run S's kind yet"),
    ],
)
def test_what_a_run_refuses_before_anything_is_sent(
    setup: Setup, change: str, words: str, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = setup.data / "scenarios"
    if change == "drop":
        (folder / "s10.toml").unlink()
    if change == "break":
        (folder / "s10.toml").write_text("id = 1\n", encoding="utf-8")
    setup.accepts = change != "history"
    assert _main(setup) == 2
    assert words in capsys.readouterr().out and setup.chat.requests == []


@pytest.mark.parametrize(
    ("extra", "words"),
    [
        (["--repeats", "0"], "--repeats is 1 or more"),
        (["--resume", "--smoke-only"], "no --smoke-only"),
        (["--arm", "K"], "--arm is not a name"),
        (["--note", "{{" + "X" + "}}"], "install placeholder"),
    ],
)
def test_the_command_line_refuses_what_a_run_cannot_be(
    setup: Setup, extra: list[str], words: str, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit):
        _main(setup, *extra)
    assert words in capsys.readouterr().err
    with pytest.raises(SystemExit):
        scenario_run.main(["--model", TALKER], parts=setup.parts())
    assert "a run needs" in capsys.readouterr().err


def test_checks_are_read_from_what_the_call_did() -> None:
    searched = HeardTurn(fate="cut", tools=(ToolUse(tool=TOOL, outcome="cancelled"),))
    quiet = HeardTurn(fate="answered")
    turns = [
        ScriptTurn(says="a", search=True, language="en"),
        ScriptTurn(says="b", when="tool_running", cancels_search=True, cuts_reply=False),
        ScriptTurn(says="c", when="agent_speaking", cuts_reply=True, max_words=0),
    ]
    found = checks_of(turns, [searched, quiet, quiet], [None, Checked(holds=(False,)), None], TOOL)
    assert found[0] == TurnCheck(search=True, language=False)  # it said nothing in English
    assert found[1].cancelled is True and found[1].passed is False
    assert found[2].cut is False and found[2].words is True
    assert needed(True, 3) == 3 and needed(False, 3) == 2 and needed(False, 5) == 4


def test_a_stop_the_talker_swallowed_still_stops_the_run(setup: Setup) -> None:
    setup.today[TALKER] = 996
    for words, scripted in list(setup.calls.script.items()):
        setup.calls.script[words] = dataclasses.replace(scripted, swallows=True)
    for n in range(1, 11):
        setup.calls.script[f"question {n}"] = Scripted(swallows=True)
    assert _main(setup) == 1
    assert _card(setup).stopped == "daily_limit"


def test_a_judge_whose_provider_fails_gives_a_failed_play(setup: Setup) -> None:
    setup.chat.judge_fails_at = {4}  # after the smoke test's three checked turns
    assert _main(setup) == 0
    first = next(play for play in _card(setup).plays if play.scenario == "s01")
    assert first.failure == "judge" and first.passed is None


def test_a_play_has_a_verdict_exactly_when_nothing_failed() -> None:
    with pytest.raises(ValidationError, match="exactly when nothing failed"):
        PlayRecord(scenario="s01", repeat=1, rehearsal=True, failure="stuck", passed=True)


def test_a_model_request_the_talker_caught_still_fails_its_play(setup: Setup) -> None:
    setup.calls.script["question 2"] = Scripted(swallows=True)
    # The smoke test sends 3 talker requests and 2 judge requests; s01 the same; s02 opens.
    setup.chat.fails_at = {11}
    assert _main(setup) == 0
    second = next(play for play in _card(setup).plays if play.scenario == "s02")
    assert second.failure == "provider" and second.turns != ()

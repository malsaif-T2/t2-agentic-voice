"""`poe uncertain` as a run (plan 006's registration, U): a stored dev overlap run read, the
uncertain overlaps asked one short request each through the chat model port, paced, capped,
held under the day's requests, the 429 waited for, each result written as it finishes and never
its words logged, and the scorecard and history line written; every refusal before anything is
sent."""

from __future__ import annotations

import runpy
import sys
import warnings
from pathlib import Path

import pytest
from ole5_voice.evals import uncertain
from ole5_voice.evals.run_lines import OverlapLine
from ole5_voice.evals.runs import SCORECARD_FILE
from ole5_voice.evals.uncertain_card import UncertainScorecard
from ole5_voice.evals.uncertain_run import INSTRUCTION, RESULTS_FILE, Prices
from t2_agentic_voice import ProviderError

from tests.ole5_voice.evals.uncertain_support import URun, overlap, stored, u_run


def _source(run: URun, n: int = 3) -> Path:
    results = [overlap(f"i{k}", "request", expected="stop") for k in range(n)]
    results.append(overlap("q", "stop_word", expected="stop", reason="stop_word", action="stop"))
    return stored(run.world.main / "var" / "runs" / "o1", results)


def _card(run: URun) -> UncertainScorecard:
    return UncertainScorecard.model_validate_json((run.out / SCORECARD_FILE).read_bytes())


def test_a_run_asks_each_uncertain_overlap_and_scores_it_against_the_rule(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    run = u_run(tmp_path, "stop", "stop", "Stop.", "go_on")
    source = _source(run)
    assert uncertain.main(run.argv(source), parts=run.parts()) == 0
    first = run.chat.requests[0]
    assert [m.role for m in first.messages] == ["system", "user"]
    assert first.messages[0].content == INSTRUCTION
    assert "the first clause. the second clause." in first.messages[1].content
    assert "made-up words" in first.messages[1].content
    assert (first.model, first.reasoning_effort, first.max_output_tokens) == (
        "llama-3.1-8b-instant",
        "low",
        16,
    )
    assert first.temperature == 0.0 and first.tools == ()
    assert len(run.chat.requests) == 4 and run.chat.closed  # the smoke test's, then 3
    card = _card(run)
    assert card.complete and card.stopped is None
    assert (card.rule.right, card.arm.right, card.arm.unclear) == (0, 2, 0)
    assert card.arm.answer_median_ms == pytest.approx(200.0)
    assert (card.keep.better, card.keep.worse, card.keep.kept) == (2, 0, False)
    assert card.requests == 4 and card.input_tokens == 800
    assert card.cost_usd == pytest.approx(4 * (100 * 0.05 + 100 * 0.05 + 2 * 0.08) / 1e6)
    assert len((run.out / RESULTS_FILE).read_text(encoding="utf-8").splitlines()) == 3
    assert card.run.source == "o1" and card.run.settings["llm.model"] == "llama-3.1-8b-instant"
    (line, history), (copy, beside) = run.lines.appended
    assert isinstance(line, OverlapLine) and line.answerer == "uncertain" and line == copy
    assert history == run.world.data / "history.jsonl" and beside == run.out / "history.jsonl"
    assert line.targets == {
        "raises_right": False,
        "listening_no_more": True,
        "answers_in_time": True,
    }
    out = capsys.readouterr().out
    assert "overlap_done" in out and "made-up words" not in out and "first clause" not in out


def test_the_price_of_cached_tokens_is_its_own_when_given(tmp_path: Path) -> None:
    run = u_run(tmp_path)
    source = _source(run, 1)
    argv = run.argv(source, "--price-cached", "0", "--smoke-only")
    assert uncertain.main(argv, parts=run.parts()) == 0
    card = _card(run)
    assert card.results == () and card.complete
    assert card.cost_usd == pytest.approx((100 * 0.05 + 2 * 0.08) / 1e6)


@pytest.mark.parametrize(
    ("answer", "attempts"), [("maybe", 1), (ProviderError("rejected", False), 1)]
)
def test_a_smoke_test_that_failed_stops_the_run_before_any_overlap(
    tmp_path: Path, answer: str | ProviderError, attempts: int
) -> None:
    run = u_run(tmp_path, answer)
    assert uncertain.main(run.argv(_source(run)), parts=run.parts()) == 1
    card = _card(run)
    assert card.stopped == "smoke_failed" and card.results == ()
    assert len(run.chat.requests) == attempts


def test_a_rate_limit_waits_its_retry_after_then_asks_again(tmp_path: Path) -> None:
    limited = ProviderError("rate_limited", True, 7.0)
    run = u_run(tmp_path, "stop", limited, "stop", "stop", "stop")
    assert uncertain.main(run.argv(_source(run)), parts=run.parts()) == 0
    assert 7.0 in run.clock.pauses
    card = _card(run)
    assert card.requests == 5 and [r.answer.attempts for r in card.results] == [2, 1, 1]


def test_a_request_still_rate_limited_on_its_last_attempt_stops_the_run(tmp_path: Path) -> None:
    limited = ProviderError("rate_limited", True, None)
    run = u_run(tmp_path, "stop", limited, limited, limited)
    assert uncertain.main(run.argv(_source(run)), parts=run.parts()) == 1
    assert run.clock.pauses.count(60.0) == 2  # no retry-after: a whole pacer window
    assert _card(run).stopped == "rate_limited"


def test_a_failure_is_counted_apart_after_its_retries(tmp_path: Path) -> None:
    server = ProviderError("server_error", True)
    rejected = ProviderError("rejected", False)
    run = u_run(tmp_path, "stop", server, server, server, rejected, "stop")
    assert uncertain.main(run.argv(_source(run)), parts=run.parts()) == 0
    card = _card(run)
    assert [r.answer.failure for r in card.results] == ["server_error", "rejected", None]
    assert run.clock.pauses.count(3.0) == 2 and card.arm.failed == 2 and card.arm.right == 1


def test_a_request_past_its_time_limit_is_stuck(tmp_path: Path) -> None:
    run = u_run(tmp_path, "stop", 5.0)
    argv = run.argv(_source(run, 1), "--item-timeout-s", "0.05")
    assert uncertain.main(argv, parts=run.parts()) == 0
    assert [r.answer.failure for r in _card(run).results] == ["stuck"]


def test_the_cap_stops_the_run_before_a_request_it_cannot_afford(tmp_path: Path) -> None:
    """Each request is charged its budget, the most it can cost, until its usage says what it
    did; a failed one keeps its budget, so retries the run's budget did not count reach the
    cap."""
    first = u_run(tmp_path / "first")
    assert uncertain.main(first.argv(_source(first, 30), "--smoke-only"), parts=first.parts()) == 0
    budget = Prices(input_usd=0.05, cached_usd=0.05, output_usd=0.08).budget(first.chat.requests[0])
    server = ProviderError("server_error", True)
    run = u_run(tmp_path / "second", "stop", *[server] * 90)
    argv = run.argv(_source(run, 30))
    argv[argv.index("--cap-usd") + 1] = str(budget * 31)  # the smoke test and 30 overlaps
    assert uncertain.main(argv, parts=run.parts()) == 1
    card = _card(run)
    assert card.stopped == "cap" and 0 < len(card.results) < 30
    assert card.cost_usd <= budget * 31


def test_the_day_limit_stops_the_run_before_it_passes(tmp_path: Path) -> None:
    server = ProviderError("server_error", True)
    run = u_run(tmp_path, "stop", server, server, "stop", "stop")
    argv = run.argv(_source(run))
    argv[argv.index("--day-requests") + 1] = "4"
    assert uncertain.main(argv, parts=run.parts()) == 1
    card = _card(run)
    assert card.stopped == "day_limit" and card.requests == 4


def test_an_interrupt_keeps_what_was_measured(tmp_path: Path) -> None:
    run = u_run(tmp_path, "stop", "stop", KeyboardInterrupt())
    assert uncertain.main(run.argv(_source(run)), parts=run.parts()) == 1
    card = _card(run)
    assert card.stopped == "interrupted" and len(card.results) == 1


def _refused(run: URun, argv: list[str], capsys: pytest.CaptureFixture[str], says: str) -> None:
    assert uncertain.main(argv, parts=run.parts()) == 2
    assert says in capsys.readouterr().out
    assert run.chat.requests == [] and not run.out.exists() and run.lines.appended == []


def test_a_held_out_or_unfinished_overlap_run_is_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A held-out overlap run's scorecard holds aggregates only, no overlap's words, so U's
    held-out pass has nothing stored to read."""
    run = u_run(tmp_path)
    folder = stored(run.world.main / "o", [overlap("a")], complete=False)
    _refused(run, run.argv(folder), capsys, "not a complete dev overlap run")
    held_out = stored(run.world.main / "h", [], split="held-out")
    _refused(run, run.argv(held_out), capsys, "a held-out run's scorecard holds no")
    card = folder / SCORECARD_FILE
    card.write_text("{}", encoding="utf-8")
    _refused(run, run.argv(card), capsys, "is not an overlap run's scorecard")


def test_a_run_with_nothing_uncertain_or_past_its_limits_is_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    run = u_run(tmp_path)
    none = stored(run.world.main / "o", [overlap("a", reason="listening")])
    _refused(run, run.argv(none), capsys, "holds no overlap the rule left uncertain")
    source = _source(run)
    argv = run.argv(source)
    argv[argv.index("--cap-usd") + 1] = "0.000001"
    _refused(run, argv, capsys, "passes --cap-usd")
    argv = run.argv(source)
    argv[argv.index("--day-requests") + 1] = "3"
    _refused(run, argv, capsys, "more than --day-requests")
    _refused(run, run.argv(source, "--set", "llm.model=made-up"), capsys, "--set llm.model")
    argv = run.argv(source)
    argv[argv.index("--out") + 1] = str(run.world.main / "var" / "runs" / "U1")
    _refused(run, argv, capsys, "is not a name")


def test_a_run_names_every_limit_and_price(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as done:
        uncertain.main(["--overlaps", "o1", "--note", "n"])
    err = capsys.readouterr().err
    assert done.value.code == 2 and "--model" in err and "--day-requests" in err
    placeholder = "{{" + "NAME" + "}}"  # written apart, or the docs check flags this file
    argv = u_run(tmp_path).argv(Path("o1"))
    argv[argv.index("--note") + 1] = f"see {placeholder}"
    with pytest.raises(SystemExit):
        uncertain.main(argv)
    assert "install placeholder" in capsys.readouterr().err


@pytest.mark.parametrize(("flag", "value"), [("--cap-usd", "-1"), ("--rpm", "0")])
def test_a_limit_out_of_its_range_is_refused(
    tmp_path: Path, flag: str, value: str, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as done:
        uncertain.main([*u_run(tmp_path).argv(Path("o1")), flag, value])
    assert done.value.code == 2 and flag in capsys.readouterr().err


def test_the_command_prints_its_help_and_runs_nothing(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    module = "ole5_voice.evals.uncertain"
    monkeypatch.setattr(sys, "argv", [module, "--help"])
    with warnings.catch_warnings(), pytest.raises(SystemExit) as done:
        warnings.simplefilter("ignore", RuntimeWarning)  # imported already, by the other tests
        runpy.run_module(module, run_name="__main__", alter_sys=True)
    assert done.value.code == 0 and capsys.readouterr().out.startswith("usage: poe uncertain")

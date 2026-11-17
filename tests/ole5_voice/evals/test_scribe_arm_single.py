"""Run H's Scribe `single` arm (D-117; scribe_arms.py, scribe_arm_card.py, scribe_arm_run.py),
with made-up answers and a fake Scribe: a variant its gate passed sends (c)'s request alone,
naming no language with the call language's prompt, its answer the turn's words whether or not
it moves the call by D-115's rule at a threshold; any other sends the call language's request
alone and never moves it; the scorecard's moves, false moves on short replies, error rates by
item language, seconds and threshold table, and each turn's record with its gate; and a pass
shaped so, one request a turn, with its dry estimate, `--estimate-only`, the gate it needs and
no word heard in any log."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from ole5_voice.evals.runs import SCORECARD_FILE
from ole5_voice.evals.scribe_arm_card import ArmScorecard, scorecard_of
from ole5_voice.evals.scribe_arms import (
    ARM_TURNS_FILE,
    GATED,
    ArmAnswer,
    ArmResult,
    Ask,
    asks,
    distinct_asks,
    turn_of,
)

from tests.leaks import holding, shown
from tests.ole5_voice.evals.fakes import FakeSpeechToText
from tests.ole5_voice.evals.test_scribe_arm_run import (
    HEARD,
    Made,
    _argv,
    _gate,
    _heard,
    _main,
    _out,
    _world,
)
from tests.ole5_voice.evals.test_scribe_arms import QUESTION, Scorers, _answer, _result, _run

NONE_AR, NONE_EN = Ask(named=None, prompt="ar"), Ask(named=None, prompt="en")
NAMED_AR, NAMED_EN = Ask(named="ar", prompt="ar"), Ask(named="en", prompt="en")


def _gated(*answers: ArmAnswer, **result: Any) -> ArmResult:
    """A variant its gate passed: each call's request named no language."""
    return _result(*answers, **result).model_copy(update={"detects": True})


def _ungated(*answers: ArmAnswer, **result: Any) -> ArmResult:
    """A variant under the gate: each call's request named its language."""
    return _result(*answers, **result).model_copy(update={"detects": False})


def test_single_sends_one_request_a_turn_shaped_by_the_gate() -> None:
    assert {"detected", "single"} == GATED
    assert asks("single", "ar") == (NONE_AR,) and asks("single", "en") == (NONE_EN,)
    assert asks("single", "ar", detects=False) == (NAMED_AR,)
    assert distinct_asks("single") == (NONE_AR, NONE_EN)
    assert distinct_asks("single", detects=False) == (NAMED_AR, NAMED_EN)


def test_a_gated_answer_is_the_turns_words_and_moves_the_call_at_its_threshold() -> None:
    english = _gated(_answer(NONE_AR, "en", 0.9, seconds=0.6), _answer(NONE_EN, "en", 0.99))
    moved = turn_of("single", english, "ar", threshold=0.8)
    assert (moved.moved, moved.text, moved.seconds) == ("en", QUESTION, 0.6)
    stays = turn_of("single", english, "ar", threshold=0.95)
    assert (stays.moved, stays.text) == (None, QUESTION)  # its words still the turn's
    assert turn_of("single", english, "en", threshold=0.5).moved is None  # its own language
    short = _gated(_answer(NONE_AR, "en", 0.99, text="okay thanks"), _answer(NONE_EN, "en", 0.9))
    assert turn_of("single", short, "ar", threshold=0.5).moved is None
    failed = _gated(
        _answer(NONE_AR, None, None, text=None, failure="timeout"), _answer(NONE_EN, "en", 0.9)
    )
    turn = turn_of("single", failed, "ar", threshold=0.5)
    assert (turn.moved, turn.text) == (None, None)


def test_a_variant_its_gate_did_not_pass_keeps_its_named_answer_and_never_moves() -> None:
    named = _answer(NAMED_AR, "en", 0.99, text="translated words", seconds=0.4)
    gated = _ungated(named, _answer(NAMED_EN, "en", 0.99))
    for threshold in (0.5, 0.8):
        turn = turn_of("single", gated, "ar", threshold=threshold)
        assert (turn.moved, turn.text, turn.seconds, turn.read) == (
            None,
            "translated words",
            0.4,
            named,
        )
    card = scorecard_of(_run("single"), [gated], complete=True, scorers=Scorers())
    assert (card.both.moves.due, card.both.moves.missed, card.both.moves.wrong) == (1, 1, 0)
    assert all(row.moves.right == 0 for row in card.thresholds)
    assert {record.detects for record in card.turns} == {False}
    with pytest.raises(KeyError):  # a passed variant whose no-language answers are missing
        turn_of("single", gated.model_copy(update={"detects": True}), "ar", threshold=0.8)


def test_the_scorecard_counts_the_moves_errors_seconds_and_table_of_single() -> None:
    results = [
        _gated(_answer(NONE_AR, "en", 0.9), _answer(NONE_EN, "en", 0.99)),  # right in Arabic
        _gated(
            _answer(NONE_AR, "ar", 0.99), _answer(NONE_EN, "ar", 0.7), item="s1", language="saudi"
        ),  # missed at 0.8 in the English call, right at 0.7 or under
        _gated(
            _answer(NONE_AR, "en", 0.95, text="that one sounds right to me"),
            _answer(NONE_EN, "en", 0.9),
            item="y1",
            kind="confirmation",
        ),  # a short reply that moves the Arabic call: wrong, short_false
        _ungated(
            _answer(NAMED_AR, "en", 0.99, text="translated words"),
            _answer(NAMED_EN, "en", 0.99),
            item="u1",
        ),  # under the gate: never moves, missed
    ]
    card = scorecard_of(_run("single"), results, complete=True, scorers=Scorers())
    moves = card.both.moves
    assert (moves.due, moves.right, moves.missed) == (3, 1, 2)
    assert (moves.wrong, moves.short_false) == (1, 1)
    by_threshold = {row.threshold: (row.moves.right, row.moves.wrong) for row in card.thresholds}
    assert by_threshold[0.5] == by_threshold[0.7] == (2, 1)
    assert by_threshold[0.75] == (1, 1) and by_threshold[0.95] == (0, 1)
    assert card.both.errors["english"].turns == 6 and card.both.errors["saudi"].wer == 0.0
    assert card.both.errors["english"].wer == pytest.approx(2 / 6)  # y1 and u1 in Arabic
    assert card.both.seconds_p50 == 0.5 and card.both.seconds_p95 == 0.5
    detects = {(r.item, r.call): r.detects for r in card.turns}
    assert detects[("e1", "ar")] and detects[("y1", "en")] and detects[("u1", "ar")] is False
    first = next(r for r in card.turns if (r.item, r.call) == ("e1", "ar"))
    assert (first.heard, first.probability, first.due, first.moved) == ("en", 0.9, True, "en")


def test_a_single_pass_sends_one_request_a_turn_by_its_gate(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], caplog: pytest.LogCaptureFixture
) -> None:
    world, parts = _world(tmp_path)
    gate = _gate(world, parts, ("e1",))
    script = [
        _heard("ar", 0.97),  # p1, Saudi, under the gate, in the Arabic call: stays
        _heard("ar", 0.99),  # p1 in the English call, named English: never moves (missed)
        _heard("en", 0.9),  # e1, English, naming none, in the Arabic call: moves it (right)
        _heard("en", 0.95),  # e1 in the English call: its own language, stays
    ]
    made = Made(FakeSpeechToText(script))
    assert _main(_argv(world, *gate, arm="single"), parts, made) == 0
    sent = [(language, prompt is not None) for _, language, prompt in made.stt.calls]
    assert sent == [("ar", True), ("en", True), (None, True), (None, True)]
    assert all(clip.other_languages == () for clip, _, _ in made.stt.calls)
    lines = (_out(world) / ARM_TURNS_FILE).read_text(encoding="utf-8").splitlines()
    assert [ArmResult.model_validate_json(line).detects for line in lines] == [False, True]
    card = ArmScorecard.model_validate_json((_out(world) / SCORECARD_FILE).read_bytes())
    assert card.complete and card.run.arm == "single" and card.run.min_probability == 0.8
    moves = card.both.moves
    assert (moves.due, moves.right, moves.missed, moves.wrong) == (2, 1, 1, 0)
    assert (card.run.requests, card.run.billed_seconds) == (4, 8.0)  # one request a turn
    assert card.run.settings["run.language_from"] == (
        "lid1-dev-detected (detected), 1 of 2 variants sent naming no language"
    )
    surfaces = shown(caplog=caplog, capsys=capsys)
    assert "arm=single" in surfaces["stdout"] and "requests=4" in surfaces["stdout"]
    assert holding(HEARD, surfaces) == []


def test_the_estimate_alone_builds_no_adapter_and_a_gate_is_needed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    world, parts = _world(tmp_path)
    made = Made(FakeSpeechToText())
    gate = _gate(world, parts, ("p1",))
    assert _main(_argv(world, "--estimate-only", *gate, arm="single"), parts, made) == 0
    assert made.settings == [] and not _out(world).exists()
    logged = capsys.readouterr().out
    for part in ("run_estimate", "arm=single", "requests=4", "billed_s=8.0"):
        assert part in logged
    silero = _gate(world, parts, ("p1",), classifier="silero")
    assert _main(_argv(world, "--estimate-only", *silero, arm="single"), parts, made) == 2
    assert "is not a detected pass" in capsys.readouterr().out and made.settings == []

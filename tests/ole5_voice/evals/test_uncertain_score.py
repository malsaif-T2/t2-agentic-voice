"""Run U's scoring (plan 006's registration, U): which stored overlaps it reads, the answer read
from the model's text, each overlap judged under the rule and the arm, and the keep rule."""

from __future__ import annotations

from pathlib import Path

from ole5_voice.evals.overlap_card import OverlapScorecard
from ole5_voice.evals.overlap_score import OverlapResult
from ole5_voice.evals.runs import SCORECARD_FILE
from ole5_voice.evals.uncertain_run import answer_of
from ole5_voice.evals.uncertain_score import (
    ArmAnswer,
    UncertainOverlap,
    UncertainResult,
    judged,
    keep_rule,
    metrics,
    uncertain_overlaps,
)

from tests.ole5_voice.evals.uncertain_support import overlap, stored


def _card(tmp_path: Path, *results: OverlapResult) -> OverlapScorecard:
    folder = stored(tmp_path / "o1", results)
    return OverlapScorecard.model_validate_json((folder / SCORECARD_FILE).read_bytes())


def test_only_the_overlaps_the_rule_left_uncertain_are_read(tmp_path: Path) -> None:
    card = _card(
        tmp_path,
        overlap("a", reason="short_output"),
        overlap("b", "request", expected="stop", reason="too_few_words"),
        overlap("c", "stop_word", expected="stop", reason="stop_word", action="stop"),
        overlap("d", reason="short_output", failure="timeout"),
        overlap("e", reason="short_output", words="  "),
        overlap("f", "repeat_request", expected="repeat", reason="too_few_words"),
    )
    found = uncertain_overlaps(card)
    assert [(o.item, o.expected, o.rule, o.reason) for o in found] == [
        ("a", "go_on", "go_on", "short_output"),
        ("b", "stop", "go_on", "too_few_words"),
        ("f", "stop", "go_on", "too_few_words"),  # a repeat request is a stop for the talker
    ]
    assert found[0].reply == "the first clause. the second clause."
    assert found[0].words == "made-up words"  # the deciding request's, not the other part's


def test_the_answer_is_one_of_the_two_words_or_unclear() -> None:
    cases = {"stop": "stop", " Stop.": "stop", "go_on": "go_on", "Go on!": "go_on"}
    cases |= {"maybe": "unclear", "": "unclear", "stop now": "unclear", "continue": "unclear"}
    assert {text: answer_of(text) for text in cases} == cases


def _overlap(item: str, *, expected: str = "go_on", kind: str = "request") -> UncertainOverlap:
    return UncertainOverlap.model_validate(
        {
            "item": item,
            "variant": f"{item}-laptop",
            "kind": kind,
            "language": "saudi",
            "device": "laptop",
            "expected": expected,
            "rule": "go_on",
            "reason": "short_output",
            "reply": "a reply",
            "words": "some words",
        }
    )


def test_an_unclear_answer_takes_the_rules_verdict_and_a_failure_none() -> None:
    wanted = _overlap("a", expected="stop")
    unclear = judged(wanted, ArmAnswer(answer="unclear", answer_ms=100.0))
    assert (unclear.arm, unclear.arm_right, unclear.rule_right) == ("go_on", False, False)
    failed = judged(wanted, ArmAnswer(failure="server_error"))
    assert (failed.arm, failed.arm_right) == (None, None)
    stopped = judged(wanted, ArmAnswer(answer="stop", answer_ms=100.0))
    assert (stopped.arm, stopped.arm_right) == ("stop", True)


def test_the_metrics_count_each_arms_stops_and_leave_failures_apart() -> None:
    results = [
        judged(_overlap("a", expected="stop"), ArmAnswer(answer="stop", answer_ms=100.0)),
        judged(_overlap("b", kind="listening_sound"), ArmAnswer(answer="stop", answer_ms=300.0)),
        judged(_overlap("c"), ArmAnswer(answer="unclear", answer_ms=200.0)),
        judged(_overlap("d"), ArmAnswer(failure="stuck")),
    ]
    arm, rule = metrics(results, arm=True), metrics(results, arm=False)
    assert (arm.variants, arm.failed, arm.items, arm.right) == (4, 1, 3, 2)
    assert (arm.stopped, arm.should_stop, arm.false_stops, arm.should_go_on) == (1, 1, 1, 2)
    assert (arm.listening, arm.listening_stops, arm.unclear) == (1, 1, 1)
    assert (arm.answer_median_ms, arm.answer_p90_ms) == (200.0, 280.0)
    assert (rule.right, rule.stopped, rule.listening_stops, rule.unclear) == (2, 0, 0, 0)
    assert rule.answer_median_ms is None


def _stops(n: int, *, ms: float = 250.0) -> list[UncertainResult]:
    return [
        judged(_overlap(f"i{k}", expected="stop"), ArmAnswer(answer="stop", answer_ms=ms))
        for k in range(n)
    ]


def test_the_keep_rule_needs_all_three_parts() -> None:
    kept = keep_rule(_stops(6))
    assert (kept.better, kept.worse, kept.p) == (6, 0, 2 / 64)
    assert kept.raises_right and kept.listening_no_more and kept.answers_in_time and kept.kept
    few = keep_rule(_stops(5))  # 2/32: not beyond the noise
    assert not few.raises_right and not few.kept
    slow = keep_rule(_stops(6, ms=301.0))
    assert slow.raises_right and not slow.answers_in_time and not slow.kept
    listening = judged(_overlap("x", kind="listening_sound"), ArmAnswer(answer="stop"))
    noisy = [*_stops(8), listening]  # 8 better, 1 worse: p = 20/512
    loud = keep_rule(noisy)
    assert loud.raises_right and not loud.listening_no_more and not loud.kept
    none = keep_rule([])
    assert (none.p, none.answers_in_time, none.kept) == (1.0, False, False)

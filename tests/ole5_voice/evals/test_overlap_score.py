"""The scorer of `poe overlap` (overlap_score.py, overlap_card.py) on hand-made verdicts: a stop
missed, a false stop, a stop timed from a marked word end and one from the detector's stop, a
repeat that only stopped, a clip of two overlaps counted by overlap, a variant whose deciding
request failed counted apart, the overlap set's selection, the numbers by group, the
registration's targets, and a held-out run's aggregates only."""

from __future__ import annotations

from typing import Any

import pytest
from ole5_voice.evals.overlap_card import OverlapRun, OverlapScorecard, breakdowns
from ole5_voice.evals.overlap_score import (
    EXPECTED,
    Action,
    Heard,
    OverlapResult,
    Verdict,
    in_set,
    judge,
    metrics,
    targets,
)
from pydantic import ValidationError

from tests.ole5_voice.evals import samples


def _heard(turn: int, part: str, sent_ms: float, **fields: Any) -> Heard:
    base = {"turn_id": turn, "part": part, "sent_ms": sent_ms, "audio_s": 0.75}
    return Heard.model_validate(base | {"answered_ms": sent_ms + 300, "text": "made-up"} | fields)


STOP = Verdict(
    opened=True,
    overlap_turns=(0,),
    action="stop",
    kind="stop",
    reason="stop_word",
    decided_by="overlap",
    decided_turn=0,
    requests=(
        _heard(0, "window", 500.0),
        _heard(0, "overlap", 900.0, audio_s=1.1),
        _heard(0, "turn", 3000.0, answered_ms=None, text=None, audio_s=1.1),
    ),
    speech_stop_ms=1100.0,
    last_audio_ms=1600.0,
)
WENT_ON = Verdict(
    opened=True,
    overlap_turns=(0,),
    action="go_on",
    kind="false",
    reason="listening",
    decided_by="overlap",
    decided_turn=0,
    requests=(_heard(0, "overlap", 400.0),),
)
# A long clip (the agent's echo) that opened two overlaps, each decided by its window and its
# whole part, and went on: two requests an overlap, four in the clip.
TWICE = Verdict(
    opened=True,
    overlap_turns=(0, 1),
    action="go_on",
    kind="false",
    reason="own_words",
    decided_by="overlap",
    decided_turn=0,
    requests=(
        _heard(0, "window", 500.0),
        _heard(0, "overlap", 900.0),
        _heard(1, "window", 9000.0),
        _heard(1, "overlap", 9400.0),
        _heard(1, "turn", 12000.0),
    ),
)


def _result(item: str, kind: str, verdict: Verdict, **fields: Any) -> OverlapResult:
    expected: Action = EXPECTED[kind]
    word_end = fields.pop("word_end_ms", None)
    base: dict[str, Any] = {
        "item": item,
        "variant": f"{item}-v1",
        "split": "dev",
        "kind": kind,
        "language": "saudi",
        "device": "laptop",
        "expected": expected,
        "reply": ("A made-up reply.",),
        "reply_known": False,
        "word_end_ms": word_end,
        "verdict": verdict,
        "judged": judge(expected, verdict, word_end),
    }
    return OverlapResult.model_validate(base | fields)


def test_a_stop_missed_and_a_false_stop_are_wrong() -> None:
    missed = judge("stop", WENT_ON, 1000.0)
    assert (missed.right, missed.stopped, missed.from_mark_ms) == (False, False, None)
    false_stop = judge("go_on", STOP, None)
    assert (false_stop.right, false_stop.stopped) == (False, True)
    unopened = judge("go_on", Verdict(opened=False), None)
    assert (unopened.right, unopened.stopped, unopened.overlap_requests) == (True, False, ())
    only_stopped = judge("repeat", STOP, None)
    assert (only_stopped.right, only_stopped.stopped) == (False, True)


def test_a_stop_is_timed_from_its_marked_end_or_else_from_the_detector() -> None:
    marked = judge("stop", STOP, 1000.0)
    assert (marked.right, marked.from_mark_ms, marked.from_detector_ms) == (True, 600.0, None)
    assert marked.overlap_requests == (2,)  # the turn's own request decides no overlap
    unmarked = judge("stop", STOP, None)
    assert (unmarked.from_mark_ms, unmarked.from_detector_ms) == (None, 500.0)
    at_zero = judge("stop", STOP, 0.0)
    assert at_zero.from_mark_ms == 1600.0
    silent = STOP.model_copy(update={"last_audio_ms": None, "speech_stop_ms": None})
    assert (
        judge("stop", silent, None).from_detector_ms,
        judge("stop", silent, 9.0).from_mark_ms,
    ) == (
        None,
        None,
    )
    no_stop_heard = STOP.model_copy(update={"speech_stop_ms": None})
    assert judge("stop", no_stop_heard, None).from_detector_ms is None


def test_the_overlap_set_holds_clips_over_a_reply_and_those_fed_over_one() -> None:
    assert in_set("request", ("over-assistant", "duck"))
    assert not in_set("request", ("duck",))  # a request recorded alone
    assert in_set("stop_word", ()) and in_set("echo_only", ()) and in_set("correction", ())
    assert not in_set("ticket_number", ()) and not in_set("made_up_kind", ("over-assistant",))


def _set() -> list[OverlapResult]:
    return [
        _result("k1", "stop_word", STOP, word_end_ms=1000.0),  # 600 ms from its mark
        _result("k2", "stop_word", STOP, word_end_ms=1300.0),  # 300 ms
        _result("k3", "stop_word", WENT_ON, word_end_ms=900.0),  # a stop missed
        _result("r1", "request", STOP),  # 500 ms from the detector
        _result("b1", "listening_sound", WENT_ON),
        _result("b2", "listening_sound", STOP),  # a false stop
        _result("e1", "echo_only", Verdict(opened=False)),
        _result("e2", "echo_only", TWICE),
    ]


def test_the_numbers_of_a_set() -> None:
    found = metrics(_set())
    assert found.model_dump() == {
        "items": 8,
        "variants": 8,
        "failed": 0,
        "right": 6,
        "should_stop": 4,
        "stopped": 3,
        "should_go_on": 4,
        "false_stops": 1,
        "requests_max": 2,  # each of the echo's two overlaps, never the clip's four
        "requests_mean": pytest.approx(14 / 8),  # over the 8 overlaps, not the 7 clips
        "marked": 2,
        "marked_median_ms": 450.0,
        "marked_p90_ms": pytest.approx(570.0),
        "marked_max_ms": 600.0,
        "detected": 2,
        "detected_median_ms": 500.0,
        "detected_p90_ms": 500.0,
    }
    empty = metrics([])
    assert (empty.requests_max, empty.requests_mean, empty.marked_median_ms) == (None, None, None)


def test_a_clip_of_two_overlaps_is_counted_by_overlap() -> None:
    judged = judge("go_on", TWICE, None)
    assert (judged.right, judged.overlap_requests) == (True, (2, 2))
    found = metrics([_result("e2", "echo_only", TWICE)])
    assert (found.requests_max, found.requests_mean) == (2, 2.0)
    (requests, *_) = targets([_result("e2", "echo_only", TWICE)], held_out=False)
    assert (requests.name, requests.value, requests.holds) == ("requests_per_overlap", 2.0, True)


def test_a_variant_whose_deciding_request_failed_is_counted_apart() -> None:
    """The whole overlap's request timed out, so the rule heard no words and went on: no
    answer of the rule's, left out of the rates and stop times, its requests still counted."""
    timed_out = _heard(0, "overlap", 900.0, answered_ms=None, text=None, failure="timeout")
    lost = WENT_ON.model_copy(update={"reason": "no_words", "requests": (timed_out,)})
    assert judge("stop", lost, 1000.0).failed and not judge("stop", WENT_ON, 1000.0).failed
    window_failed = STOP.model_copy(
        update={"requests": (_heard(0, "window", 500.0, failure="timeout"), *STOP.requests[1:])}
    )
    assert not judge("stop", window_failed, None).failed  # the whole overlap decided
    results = [*_set(), _result("k4", "stop_word", lost, word_end_ms=1000.0)]
    found = metrics(results)
    assert (found.variants, found.failed, found.right, found.should_stop) == (9, 1, 6, 4)
    assert found.requests_max == 2 and found.requests_mean == pytest.approx(15 / 9)
    words = {t.name: t for t in targets(results, held_out=False)}["stop_words_heard"]
    assert words.items == 3 and words.value == pytest.approx(2 / 3)  # k4 left out
    pooled = breakdowns(results, held_out=True)["kind"]["stop_word"]
    assert (pooled.variants, pooled.failed, pooled.should_stop) == (4, 1, 3)


def test_the_registrations_targets() -> None:
    found = {t.name: t for t in targets(_set(), held_out=False)}
    assert [(t.value, t.holds) for t in found.values()] == [
        (2.0, True),
        (450.0, True),
        (pytest.approx(570.0), True),
        (600.0, True),
        (pytest.approx(2 / 3), False),
        (1.0, True),
        (0.5, False),
        (0.0, True),
    ]
    assert (found["stop_words_heard"].items, found["stop_words_heard"].at_most) == (3, False)
    none = {
        t.name: t
        for t in targets([_result("e1", "echo_only", Verdict(opened=False))], held_out=False)
    }
    assert (none["requests_per_overlap"].value, none["requests_heard"].holds) == (None, None)
    withheld = {t.name: t for t in targets(_set(), held_out=True)}
    assert withheld["stop_words_heard"].value is not None  # three items
    assert (withheld["requests_heard"].value, withheld["requests_heard"].items) == (None, 1)


def _card(split: str, results: list[OverlapResult], **fields: Any) -> dict[str, Any]:
    held_out = split == "held-out"
    run = OverlapRun(
        name="o1",
        started_at=samples.WHEN,
        commit="0f44056",
        answerer="pipeline",
        split=split,  # type: ignore[arg-type]
        settings={},
        data_digest=samples.SHA,
        at_s=1.0,
        tail_s=4.5,
        stt_rpm=10,
        note="O1",
    )
    return {
        "run": run,
        "complete": True,
        "totals": metrics(results),
        "breakdowns": breakdowns(results, held_out=held_out),
        "targets": targets(results, held_out=held_out),
        "requests": 0,
        "billed_seconds": 0.0,
        "cost_usd": 0.0,
    } | fields


def test_a_held_out_run_writes_aggregates_only() -> None:
    results = _set()
    pooled = breakdowns(results, held_out=True)
    assert "item" not in pooled
    assert set(pooled["kind"]) == {"stop_word", "other"} and set(pooled["device"]) == {"laptop"}
    assert breakdowns(results[:2], held_out=True)["kind"] == {}  # two items: nothing shown
    card = OverlapScorecard.model_validate(_card("held-out", results))
    assert card.variants == () and card.totals.variants == 8
    with pytest.raises(ValidationError, match="aggregates only"):
        OverlapScorecard.model_validate(_card("held-out", results, variants=tuple(results)))
    dev = breakdowns(results, held_out=False)
    with pytest.raises(ValidationError, match="aggregates only"):
        OverlapScorecard.model_validate(_card("held-out", results, breakdowns=dev))
    small = {"kind": {"request": metrics(results[3:4])}}
    with pytest.raises(ValidationError, match="at least 3 items"):
        OverlapScorecard.model_validate(_card("held-out", results, breakdowns=small))
    shown = OverlapScorecard.model_validate(_card("dev", results, variants=tuple(results)))
    assert len(shown.variants) == 8 and "item" in shown.breakdowns

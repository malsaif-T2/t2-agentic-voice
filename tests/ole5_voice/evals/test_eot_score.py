"""The scorer of `poe eot` (eot_score.py) on hand-made decision sequences: a cut-off, a miss, a
late end, a variant cut into two turns, the secondary set's proxy, the numbers' type 7
quantiles, and a held-out set's pooled groups; and the checks a scorecard and a history line
are read with."""

from __future__ import annotations

from typing import Any

from ole5_voice.evals.eot_score import (
    Decision,
    EotResult,
    Judged,
    judge,
    metrics,
    proxy_end,
    set_card,
)


def _ends(*pairs: tuple[float, float]) -> list[Decision]:
    return [Decision(speech_stop_ms=stop, end_ms=end) for stop, end in pairs]


def test_a_variant_is_cut_off_missed_or_timed_by_its_first_turn_end() -> None:
    timed = judge(_ends((1700.0, 2100.0)), 1500.0, labelled=True)
    assert timed == Judged(
        true_end_ms=1500.0,
        verdict="timed",
        early=0,
        delay_ms=600.0,
        vad_stop_ms=200.0,
        decision_ms=400.0,
    )
    # A turn end up to 300 ms early still counts as on the mark: a negative delay.
    early = judge(_ends((1150.0, 1250.0)), 1500.0, labelled=True)
    assert (early.verdict, early.delay_ms) == ("timed", -250.0)
    # More than 300 ms early is a cut-off, the variant cut into two turns.
    cut = judge(_ends((900.0, 1199.0), (1600.0, 1800.0)), 1500.0, labelled=True)
    assert (cut.verdict, cut.early, cut.delay_ms) == ("cut_off", 1, None)
    # A late end within 4 s is timed; one past it, or none at all, is a miss.
    late = judge(_ends((1700.0, 5500.0)), 1500.0, labelled=True)
    assert (late.verdict, late.delay_ms, late.decision_ms) == ("timed", 4000.0, 3800.0)
    assert judge(_ends((1700.0, 5500.1)), 1500.0, labelled=True).verdict == "miss"
    assert judge([], 1500.0, labelled=True) == Judged(true_end_ms=1500.0, verdict="miss", early=0)
    # Ends given out of order are judged by the first.
    shuffled = judge(_ends((1600.0, 1800.0), (900.0, 1000.0)), 1500.0, labelled=True)
    assert shuffled.verdict == "cut_off"


def test_the_secondary_sets_true_end_is_silero_s_last_stop() -> None:
    ends = _ends((800.0, 1000.0), (2400.0, 2700.0))
    assert proxy_end(ends) == 2400.0 and proxy_end([]) is None
    split = judge(ends, proxy_end(ends), labelled=False)
    assert (split.verdict, split.early) == ("cut_off", 1)
    whole = judge(_ends((2400.0, 2700.0)), 2400.0, labelled=False)
    assert (whole.verdict, whole.delay_ms, whole.vad_stop_ms, whole.decision_ms) == (
        "timed",
        300.0,
        None,
        300.0,
    )
    assert judge([], None, labelled=False) == Judged(true_end_ms=None, verdict="miss", early=0)


def _result(
    item: str, judged: Judged, *, language: Any = "saudi", device: Any = "laptop"
) -> EotResult:
    return EotResult(
        item=item,
        variant=f"{item}-v",
        split="dev",
        kind="paused_request",
        language=language,
        device=device,
        set="paused",
        ends=(),
        judged=judged,
    )


def _timed(delay: float) -> Judged:
    return Judged(
        true_end_ms=0.0,
        verdict="timed",
        early=0,
        delay_ms=delay,
        vad_stop_ms=delay / 2,
        decision_ms=delay / 2,
    )


def test_the_numbers_count_each_verdict_and_take_type_7_quantiles() -> None:
    cut = Judged(true_end_ms=0.0, verdict="cut_off", early=1)
    miss = Judged(true_end_ms=0.0, verdict="miss", early=0)
    results = [
        _result("a", _timed(100.0)),
        _result("a", _timed(300.0)),
        _result("b", _timed(200.0)),
        _result("b", _timed(400.0)),
        _result("c", cut),
        _result("d", miss),
    ]
    found = metrics(results)
    assert (found.items, found.variants, found.cut_offs, found.misses) == (4, 6, 1, 1)
    assert (found.delay_median_ms, found.delay_p90_ms) == (250.0, 370.0)
    assert (found.vad_stop_median_ms, found.decision_p90_ms) == (125.0, 185.0)
    assert metrics([]).delay_median_ms is None
    card = set_card(results, held_out=False)
    assert set(card.breakdowns) == {"language", "device", "item"}
    assert card.breakdowns["item"]["c"].cut_offs == 1


def test_a_held_out_set_pools_its_small_groups_and_names_no_item() -> None:
    results = [_result(f"i{n}", _timed(100.0), language="saudi") for n in range(3)]
    results += [
        _result("e1", _timed(100.0), language="english"),
        _result("m1", _timed(100.0), language="mixed", device="wired"),
    ]
    card = set_card(results, held_out=True)
    assert "item" not in card.breakdowns
    assert set(card.breakdowns["language"]) == {"saudi"}  # english and mixed, 2 items: dropped
    assert card.breakdowns["device"]["laptop"].items == 4  # wired, 1 item, pooled and dropped
    lone = set_card(
        [
            *results,
            _result("w1", _timed(1.0), device="wired"),
            _result("w2", _timed(1.0), device="bluetooth"),
        ],
        held_out=True,
    )
    assert lone.breakdowns["device"]["other"].items == 3

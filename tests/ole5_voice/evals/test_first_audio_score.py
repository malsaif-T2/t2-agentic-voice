"""Run T's scoring (plan 006's registration, T): each recording's timed turn, the numbers by path
(a reply with a search, and with none), a reply never heard by the call's end counted and ranked
slowest, the progress line begun by 2 s, the registered targets, a held-out run's withheld ones,
and the breakdowns by where the time starts and by language."""

from __future__ import annotations

from typing import Any

import pytest
from ole5_voice.evals.first_audio_score import (
    AudioResult,
    ChatSpend,
    ReplayedCall,
    ReplayedTurn,
    breakdowns,
    metrics,
    result_of,
    targets,
)
from pydantic import ValidationError

TAIL = 47.0  # the run's tail: the talker's worst case at the tests' time limits


def _result(
    item: str, *turns: ReplayedTurn, language: str = "saudi", end: str = "label"
) -> AudioResult:
    base: dict[str, Any] = {
        "item": item,
        "variant": f"{item}-laptop",
        "split": "dev",
        "language": language,
        "device": "laptop",
        "end": end,
    }
    call = ReplayedCall(turns=turns, openings=(), usage=(), chat=ChatSpend())
    return result_of(base, call, 1, ())


def _search(ms: float, progress: float | None = None) -> ReplayedTurn:
    return ReplayedTurn(ttfa_ms=ms, searched=True, progress_ms=progress)


def test_a_call_of_one_answered_turn_is_timed_and_others_are_not() -> None:
    one = _result("a", ReplayedTurn(ttfa_ms=900.0))
    cut = _result("b", ReplayedTurn(ttfa_ms=900.0), ReplayedTurn(ttfa_ms=950.0))
    failed = _result("c", ReplayedTurn(failure="rate_limited"))
    none = _result("d")
    assert one.timed is not None and not one.cut and one.failure is None
    assert cut.timed is None and cut.cut
    assert failed.timed is None and failed.failure == "rate_limited"
    found = metrics([one, cut, failed, none])
    assert (found.variants, found.items, found.cut, found.failures, found.unanswered) == (
        4,
        4,
        1,
        1,
        1,
    )
    assert found.paths["no_search"].turns == 1 and found.paths["search"].turns == 0


def test_each_path_has_its_own_spread_and_a_late_search_needs_its_progress_line() -> None:
    results = [
        _result("a", _search(3500.0, 2500.0)),  # late, its progress line in time
        _result("b", _search(4500.0)),  # late, with none
        _result("c", _search(3600.0, 3100.0)),  # late, its line too late
        _result("d", _search(2800.0)),  # in time: needs none
        _result("e", ReplayedTurn(ttfa_ms=1000.0)),
        _result("f", ReplayedTurn(ttfa_ms=2000.0)),
    ]
    found = metrics(results)
    search, plain = found.paths["search"], found.paths["no_search"]
    assert (search.turns, search.items, search.median_ms) == (4, 4, 3550.0)
    assert search.p90_ms == pytest.approx(4230.0)
    assert (plain.median_ms, plain.p90_ms) == (1500.0, 1900.0)
    assert (found.progress_lines, found.progress_median_ms, found.progress_late) == (2, 2800.0, 2)
    held = {t.name: (t.value, t.holds) for t in targets(results, held_out=False, tail_s=TAIL)}
    assert held == {
        "no_search_median_ms": (1500.0, True),
        "no_search_p90_ms": (1900.0, True),
        "search_median_ms": (3550.0, False),
        "search_p90_ms": (pytest.approx(4230.0), False),
        "progress_late": (2.0, False),
    }


def test_a_reply_never_heard_by_the_calls_end_is_counted_and_ranked_slowest() -> None:
    """A timed turn whose reply sent no audio before the call ended took longer than the call's
    tail: it is counted (`no_audio`) and ranked after every reply heard, so a quantile that
    reaches it has no value, and its target fails; it began nothing by 3 s either."""
    heard = [_result(f"s{k}", _search(2100.0 + 100.0 * k, 1500.0)) for k in range(7)]
    silent = [_result(f"x{k}", ReplayedTurn(searched=True)) for k in range(2)]
    found = metrics([*heard, *silent])
    search = found.paths["search"]
    assert (search.turns, search.items, search.no_audio, found.no_audio) == (9, 9, 2, 2)
    assert (search.median_ms, search.p90_ms) == (2500.0, None)
    assert (found.unanswered, found.progress_late) == (0, 2)
    held = {
        t.name: (t.value, t.holds) for t in targets([*heard, *silent], held_out=False, tail_s=TAIL)
    }
    assert held["search_median_ms"] == (2500.0, True)
    assert held["search_p90_ms"] == (None, False)
    assert held["progress_late"] == (2.0, False)


def test_a_quantile_that_reaches_an_unheard_reply_fails_when_even_the_tail_breaks_its_bound() -> (
    None
):
    """An unheard reply's time is at least the call's tail: a quantile weighted toward it fails
    when the tail's time alone would break its bound, and is unknown otherwise."""
    results = [_result(f"s{k}", _search(1000.0, 900.0)) for k in range(18)]
    results += [_result(f"x{k}", ReplayedTurn(searched=True)) for k in range(2)]

    def p90(tail_s: float) -> tuple[float | None, bool | None]:
        shown = {t.name: t for t in targets(results, held_out=False, tail_s=tail_s)}
        return shown["search_p90_ms"].value, shown["search_p90_ms"].holds

    assert p90(TAIL) == (None, False)  # at least 1000 + 0.1 x (47000 - 1000) ms: past 4000
    assert p90(6.0) == (None, None)  # at least 1500 ms: it may still hold
    none_heard = {t.name: t for t in targets(results[18:], held_out=False, tail_s=TAIL)}
    assert (none_heard["search_median_ms"].value, none_heard["search_median_ms"].holds) == (
        None,
        False,
    )


def test_a_target_over_too_few_held_out_items_or_none_is_withheld() -> None:
    results = [_result("a", ReplayedTurn(ttfa_ms=900.0)), _result("b", _search(2000.0))]
    shown = {t.name: t.value for t in targets(results, held_out=True, tail_s=TAIL)}
    assert set(shown.values()) == {None}
    dev = {t.name: t.value for t in targets(results[:1], held_out=False, tail_s=TAIL)}
    assert dev["no_search_median_ms"] == 900.0 and dev["search_median_ms"] is None
    assert dev["progress_late"] is None


def test_the_breakdowns_are_by_where_the_time_starts_and_by_language() -> None:
    results = [
        _result("a", ReplayedTurn(ttfa_ms=900.0)),
        _result("b", ReplayedTurn(ttfa_ms=1100.0), language="english", end="detector"),
    ]
    found = breakdowns(results)
    assert set(found) == {"end", "language"}
    assert {k: v.variants for k, v in found["end"].items()} == {"detector": 1, "label": 1}
    assert found["language"]["english"].paths["no_search"].median_ms == 1100.0


def test_a_reply_opening_names_a_file_of_the_runs_replies_only() -> None:
    base: dict[str, Any] = {
        "item": "a",
        "variant": "a-laptop",
        "split": "dev",
        "language": "saudi",
        "device": "laptop",
        "end": "label",
    }
    assert AudioResult.model_validate(base | {"openings": ("replies/a-laptop-0.wav", None)})
    for path in ("../secret.wav", "replies/../x.wav", "/var/a.wav", "replies/a.txt"):
        with pytest.raises(ValidationError):
            AudioResult.model_validate(base | {"openings": (path,)})


def test_the_targets_read_both_starts_of_time_together_the_breakdown_each_apart() -> None:
    """Q18: the replies timed from the owner's marked end (`n19` to `n28`) and those timed from
    the speech detector's stop (`n01` to `n18`) are read together by the targets, and apart by
    the breakdown by where the time starts."""
    marked = [_result(f"n2{n}", _search(2000.0 + 100 * n)) for n in range(3)]
    detected = [_result(f"n0{n}", _search(3500.0 + 100 * n), end="detector") for n in range(3)]
    results = [*marked, *detected]
    median = {t.name: t.value for t in targets(results, held_out=False, tail_s=TAIL)}
    assert median["search_median_ms"] == pytest.approx(2850.0)  # the six together
    ends = breakdowns(results)["end"]
    assert ends["label"].paths["search"].median_ms == pytest.approx(2100.0)
    assert ends["detector"].paths["search"].median_ms == pytest.approx(3600.0)

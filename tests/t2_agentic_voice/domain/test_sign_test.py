"""sign_test: the two-sided sign test by item of evaluation.md's "Judging a change",
p = min(1, 2 * sum over i <= min(b, w) of C(b + w, i) / 2^(b + w)), against hand-computed cases
and against that formula written out with exact fractions."""

from __future__ import annotations

from fractions import Fraction
from math import comb

import pytest
from t2_agentic_voice.domain.sign_test import sign_test


def formula(better: int, worse: int) -> Fraction:
    """evaluation.md's formula, term by term, in exact fractions."""
    n = better + worse
    tail = sum((Fraction(comb(n, i), 2**n) for i in range(min(better, worse) + 1)), Fraction(0))
    return min(Fraction(1), 2 * tail)


@pytest.mark.parametrize(
    ("better", "worse", "p"),
    [
        (6, 0, 2 / 64),  # the plan's registration: 2/64 = 0.03125, beyond the noise
        (5, 0, 0.0625),  # and 2/32, not
        (0, 6, 0.03125),  # two-sided: the same either way round
        (7, 1, 18 / 256),  # 2 * (1 + 8) / 2^8
        (8, 1, 20 / 512),  # 2 * (1 + 9) / 2^9
        (9, 2, 134 / 2048),  # 2 * (1 + 11 + 55) / 2^11
        (10, 2, 158 / 4096),  # 2 * (1 + 12 + 66) / 2^12
        (1, 0, 1.0),  # 2 * 1 / 2 = 1
        (2, 0, 0.5),
    ],
)
def test_the_hand_computed_cases(better: int, worse: int, p: float) -> None:
    assert sign_test(better, worse) == p


@pytest.mark.parametrize("count", [0, 1, 2, 5, 17, 300])
def test_as_many_better_as_worse_gives_1(count: int) -> None:
    assert sign_test(count, count) == 1.0


def test_nothing_changed_gives_1() -> None:
    assert sign_test(0, 0) == 1.0


def test_every_small_case_matches_the_formula_rounded_once() -> None:
    for better in range(41):
        for worse in range(41):
            assert sign_test(better, worse) == float(formula(better, worse)), (better, worse)


def test_six_items_is_the_smallest_change_one_run_can_detect_with_no_noise() -> None:
    # The registration's c: the fewest items on one side that give p < 0.05 by themselves.
    assert min(c for c in range(1, 50) if sign_test(c, 0) < 0.05) == 6


def test_the_p_value_falls_as_the_split_grows_more_lopsided() -> None:
    values = [sign_test(20 - worse, worse) for worse in range(11)]
    assert values == sorted(values)
    assert values[0] < values[-1] == 1.0


def test_large_counts_neither_overflow_nor_lose_the_answer() -> None:
    assert sign_test(1500, 1500) == 1.0
    assert 0.0 < sign_test(600, 400) < 1e-9
    assert sign_test(5000, 0) == 0.0  # 2 / 2^5000 is below the smallest float
    assert isinstance(sign_test(600, 400), float)


@pytest.mark.parametrize(
    ("better", "worse"),
    [(6.0, 0), (6, 0.0), ("6", 0), (True, 0), (0, False), (None, 1)],
)
def test_a_count_that_is_not_an_int_is_refused(better: object, worse: object) -> None:
    with pytest.raises(TypeError, match="a count of items, an int"):
        sign_test(better, worse)  # type: ignore[arg-type]


@pytest.mark.parametrize(("better", "worse"), [(-1, 0), (0, -1), (-6, -6)])
def test_a_negative_count_is_refused(better: int, worse: int) -> None:
    with pytest.raises(ValueError, match="never negative"):
        sign_test(better, worse)

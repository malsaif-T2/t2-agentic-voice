"""The paired sign test by item, which judges one run against another (evaluation.md, "Judging
a change"). Public through the `evals` facade (D-021).
"""

from __future__ import annotations


def _count(name: str, value: int) -> int:
    """`value` checked as a count of items: an int (never a bool), never negative."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} is a count of items, an int")
    if value < 0:
        raise ValueError(f"{name} is a count of items, never negative")
    return value


def sign_test(better: int, worse: int) -> float:
    """The two-sided p-value of `better` items better and `worse` items worse (unchanged items
    left out): p = min(1, 2 * sum over i <= min(b, w) of C(b + w, i) / 2^(b + w)), so 1 when
    nothing changed or when b = w, and 2/64 for 6 better and none worse. Computed exactly in
    integers and rounded once. TypeError for a count that is not an int; ValueError for a
    negative one."""
    better, worse = _count("better", better), _count("worse", worse)
    n = better + worse
    term = tail = 1  # C(n, 0), and the sum so far
    for i in range(min(better, worse)):
        term = term * (n - i) // (i + 1)  # C(n, i + 1), exact
        tail += term
    twice, outcomes = 2 * tail, 2**n
    return 1.0 if twice >= outcomes else twice / outcomes

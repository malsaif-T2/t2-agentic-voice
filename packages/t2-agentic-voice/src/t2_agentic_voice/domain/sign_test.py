"""The paired sign test by item, which judges one run against another (evaluation.md, "Judging
a change").

Built by plan 002's Track A; until then a stub. Public through the `evals` facade (D-021).
"""

from __future__ import annotations


def sign_test(better: int, worse: int) -> float:
    """The two-sided p-value of `better` items better and `worse` items worse (unchanged items
    left out): p = min(1, 2 * sum over i <= min(b, w) of C(b + w, i) / 2^(b + w)), so 1 when
    nothing changed, and 2/64 for 6 better and none worse. Not built yet."""
    raise NotImplementedError("sign_test is built by plan 002's Track A")

"""Word and character error rates, on jiwer, after the canonical normalization.

Built by plan 002's Track A; until then stubs. Pooled over many pairs, as a stratum's rate is:
the errors of every pair over the words (or characters) of every reference. Public through the
`evals` facade (D-021).
"""

from __future__ import annotations

from collections.abc import Sequence


def wer(references: Sequence[str], outputs: Sequence[str]) -> float:
    """The word error rate of `outputs` against `references`, pair by pair and pooled:
    substitutions, deletions and insertions over the references' words, both sides normalized
    (`normalize_arabic`, `normalize_digits`). ValueError when the two differ in length, or when
    a reference is empty after normalization. Not built yet."""
    raise NotImplementedError("wer is built by plan 002's Track A")


def cer(references: Sequence[str], outputs: Sequence[str]) -> float:
    """The character error rate, pooled as `wer` is, with every space removed first, so a word
    split differently is not counted twice. ValueError as for `wer`. Not built yet."""
    raise NotImplementedError("cer is built by plan 002's Track A")

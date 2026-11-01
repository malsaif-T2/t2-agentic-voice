"""The evaluation scorers' pure parts: recall of product terms and IDs, and text from silence.

Ported from the prototype's scorer (D-010, D-022) by plan 002's Track A; until then stubs. Each
scores one output against its reference; a caller pools the counts over a stratum. Public
through the `evals` facade (D-021).
"""

from __future__ import annotations

from collections.abc import Sequence

from t2_agentic_voice.domain.recall import Recall


def term_recall(reference: str, output: str, terms: Sequence[str]) -> Recall:
    """Of `terms` that `reference` holds, how many `output` holds too: each a whole word or
    phrase, both texts normalized (`normalize_arabic`, `normalize_digits`). Not built yet."""
    raise NotImplementedError("term_recall is built by plan 002's Track A")


def id_recall(reference: str, output: str) -> Recall:
    """Of the IDs `reference` holds (its runs of digits, after `normalize_digits`), how many
    `output` holds too. Not built yet."""
    raise NotImplementedError("id_recall is built by plan 002's Track A")


def silence_output(output: str) -> int:
    """How much text a provider produced where nothing was said (silence, a noise, or only the
    agent's own echo): the characters of `output` after normalization, spaces removed; 0 when
    it produced none. Not built yet."""
    raise NotImplementedError("silence_output is built by plan 002's Track A")

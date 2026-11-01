"""Word and character error rates, on jiwer, after the canonical normalization.

Pooled over many pairs, as a stratum's rate is: the errors of every pair over the words (or
characters) of every reference. Both sides are first put in the scorers' form (`scored_form`:
`normalize_arabic`, then `normalize_digits`), so jiwer only aligns words that are already
compared alike. Public through the `evals` facade (D-021).
"""

from __future__ import annotations

from collections.abc import Sequence

import jiwer

from t2_agentic_voice.domain.scoring import scored_form


def _pairs(references: Sequence[str], outputs: Sequence[str]) -> tuple[list[str], list[str]]:
    """The pairs in their scored form, checked: TypeError for a bare str or anything but str
    inside; ValueError for no pairs, a length that differs, or a reference with no words."""
    for name, texts in (("references", references), ("outputs", outputs)):
        if isinstance(texts, str):
            raise TypeError(f"{name} is a sequence of texts, not one str: put one text in a list")
    refs, outs = list(references), list(outputs)
    if not all(isinstance(text, str) for text in refs + outs):
        raise TypeError("every reference and every output is a str")
    if len(refs) != len(outs):
        raise ValueError(
            f"{len(refs)} references and {len(outs)} outputs: each output is scored against "
            "the reference at its place"
        )
    if not refs:
        raise ValueError("no pairs to score: an error rate needs at least one reference")
    refs, outs = [scored_form(text) for text in refs], [scored_form(text) for text in outs]
    for place, reference in enumerate(refs):
        if not reference:
            raise ValueError(
                f"reference {place} is empty after normalization: an error rate needs words "
                "to compare with, so score text from silence with silence_output instead"
            )
    return refs, outs


def wer(references: Sequence[str], outputs: Sequence[str]) -> float:
    """The word error rate of `outputs` against `references`, pair by pair and pooled:
    substitutions, deletions and insertions over the references' words, both sides normalized
    (`normalize_arabic`, `normalize_digits`). An empty output is all deletions; insertions can
    take the rate above 1. ValueError when the two differ in length, when there is no pair, or
    when a reference is empty after normalization (jiwer would give the insertions' count);
    TypeError when `references` or `outputs` is a str rather than a sequence of texts (a str is
    a sequence of characters, so a single pair would otherwise be scored letter by letter)."""
    refs, outs = _pairs(references, outputs)
    return float(jiwer.process_words(refs, outs).wer)


def cer(references: Sequence[str], outputs: Sequence[str]) -> float:
    """The character error rate, pooled as `wer` is, with every space removed first, so a word
    split differently is not counted twice. ValueError and TypeError as for `wer`."""
    refs, outs = _pairs(references, outputs)
    refs, outs = [r.replace(" ", "") for r in refs], [o.replace(" ", "") for o in outs]
    return float(jiwer.process_characters(refs, outs).cer)

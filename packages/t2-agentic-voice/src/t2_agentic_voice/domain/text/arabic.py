"""The canonical Arabic normalizer: one spelling of a text, so two texts can be compared.

Ported from the prototype's normalizer (D-010) by plan 002's Track A, which names the source in
the plan's progress log; until then a stub. Public through the `languages` facade (D-021).
"""

from __future__ import annotations


def normalize_arabic(text: str) -> str:
    """`text` in its canonical form for comparison: no diacritics and no tatweel; the alef,
    hamza, teh marbuta and alef maksura forms folded; Latin letters in lower case; punctuation
    dropped; runs of space made one. Not built yet."""
    raise NotImplementedError("normalize_arabic is built by plan 002's Track A")

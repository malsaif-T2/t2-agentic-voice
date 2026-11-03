"""Whole-word matching of normalized texts, which the scorers and the spelling-guide check share,
so a change to what counts as a whole word reaches both (TD-009 asks one for term recall); the
Arabic prefixes a word may be written with; and whether two words are one edit apart, which the
interruption rule's test of the agent's own words reads (domain/interruptions.py)."""

from __future__ import annotations

_CONJUNCTIONS = ("", "\u0648", "\u0641")  # none, waw, feh
_PREPOSITIONS = ("", "\u0628", "\u0644", "\u0643")  # none, beh, lam, kaf
_ARTICLE = ("", "\u0627\u0644")  # none, alef lam
_LAM_ARTICLE, _LAM_LAM = "\u0644\u0627\u0644", "\u0644\u0644"  # lam alef lam is written lam lam


def _arabic_prefixes() -> tuple[str, ...]:
    """Each prefix written onto an Arabic word, in `normalize_arabic`'s form: a conjunction, then
    a preposition, then the article, each one or none (lam with the article written lam lam)."""
    joined = (c + p + a for c in _CONJUNCTIONS for p in _PREPOSITIONS for a in _ARTICLE)
    return tuple(prefix.replace(_LAM_ARTICLE, _LAM_LAM) for prefix in joined if prefix)


# The 23 prefixes: the article (ال), the conjunctions (و، ف) and the prepositions (ب، ل، ك)
# alone; a conjunction before a preposition or the article (وب، وال), beh or kaf before the
# article (بال، كال), lam with it (لل); and a conjunction before those last three (وبال، ولل).
ARABIC_PREFIXES = _arabic_prefixes()


def holds_words(text: str, phrase: str) -> bool:
    """Whether `text` holds `phrase` as whole words, both already normalized (words separated by
    one space, none at the ends): a word or a phrase, never a part of a longer word."""
    return f" {phrase} " in f" {text} "


def one_edit(first: str, second: str) -> bool:
    """Whether `first` becomes `second` by one letter changed, added or removed, or none."""
    if len(first) == len(second):
        return sum(a != b for a, b in zip(first, second, strict=True)) <= 1
    shorter, longer = sorted((first, second), key=len)
    if len(longer) - len(shorter) != 1:
        return False
    at = 0
    while at < len(shorter) and shorter[at] == longer[at]:
        at += 1
    return shorter[at:] == longer[at + 1 :]

"""Whole-word matching of normalized texts, which the scorers and the spelling-guide check share,
so a change to what counts as a whole word reaches both (TD-009 asks one for term recall)."""

from __future__ import annotations


def holds_words(text: str, phrase: str) -> bool:
    """Whether `text` holds `phrase` as whole words, both already normalized (words separated by
    one space, none at the ends): a word or a phrase, never a part of a longer word."""
    return f" {phrase} " in f" {text} "

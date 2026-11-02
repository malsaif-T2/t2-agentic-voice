"""The spelling-guide check: where a reference breaks a team's spelling guide.

The guide is data the team passes in (`SpellingRule`, in `rulings.py`), never a list in the
library. Public through the `languages` facade (D-021).
"""

from __future__ import annotations

from collections.abc import Sequence

from t2_agentic_voice.domain.text.arabic import normalize_arabic
from t2_agentic_voice.domain.text.rulings import SpellingIssue, SpellingRule
from t2_agentic_voice.domain.text.words import ARABIC_PREFIXES, holds_words


def _holds(text: str, form: str) -> bool:
    """Whether the normalized `text` holds the avoided spelling's `form` as whole words, bare or
    with one of the Arabic prefixes written onto its first word."""
    return holds_words(text, form, prefixes=ARABIC_PREFIXES)


def _avoided(rule: SpellingRule) -> list[tuple[str, str]]:
    """Each spelling `rule` avoids with its normalized form, the first of each form only.
    ValueError when one can never be found, or when writing what the rule says would break
    it (its `write` holds one, with a prefix or without): either is a ruling no reference can
    follow as written."""
    write = normalize_arabic(rule.write)
    forms: dict[str, str] = {}
    for spelling in rule.avoid:
        form = normalize_arabic(spelling)
        if not form:
            raise ValueError(
                f"spelling rule {rule.id!r} avoids a spelling that is empty after "
                "normalization, so no reference could hold it"
            )
        if _holds(write, form):
            raise ValueError(
                f"spelling rule {rule.id!r} avoids a spelling that what it says to write "
                "holds after normalization, so a reference that follows it would break it"
            )
        forms.setdefault(form, spelling)
    return [(spelling, form) for form, spelling in forms.items()]


def spelling_issues(reference: str, rules: Sequence[SpellingRule]) -> list[SpellingIssue]:
    """Every spelling of `rules` that `reference` holds, as a whole word or phrase, bare or
    with an Arabic prefix written onto its first word (the article, a conjunction, a
    preposition, or two or three of them in order: `ARABIC_PREFIXES` in `words.py`), both
    compared after `normalize_arabic`; empty when it follows them all. One issue per avoided
    spelling found, however often the reference holds it, in the order of the rules and of
    their spellings; `found` is the spelling as the rule writes it, the first of those that
    normalize alike. Every rule is checked whatever the reference: ValueError for one with a
    spelling that is empty after normalization, or that its own `write` holds."""
    held = normalize_arabic(reference)
    return [
        SpellingIssue(rule=rule.id, found=spelling, write=rule.write)
        for rule in rules
        for spelling, form in _avoided(rule)
        if _holds(held, form)
    ]

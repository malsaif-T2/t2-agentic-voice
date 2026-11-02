"""The spelling-guide check: where a reference breaks a team's spelling guide.

The guide is data the team passes in (`SpellingRule`, in `rulings.py`), never a list in the
library. Public through the `languages` facade (D-021).
"""

from __future__ import annotations

from collections.abc import Sequence

from t2_agentic_voice.domain.text.arabic import normalize_arabic
from t2_agentic_voice.domain.text.rulings import SpellingIssue, SpellingRule
from t2_agentic_voice.domain.text.words import ARABIC_PREFIXES, holds_words

# The bare spelling first, then the prefixes from the shortest: a word is read with the shortest.
_SHORTEST_FIRST = ("", *sorted(ARABIC_PREFIXES, key=len))


def _read_as(forms: Sequence[str]) -> dict[str, str]:
    """Each way a reference may write one of a rule's avoided `forms` (normalized), bare or with
    an Arabic prefix written onto its first word, mapped to the form a word so written is read
    as: the one it holds with the shortest prefix, so one word breaks a rule once (الاوتلوك is
    a rule's الاوتلوك when it lists one, not its اوتلوك with ال). A form is never taken apart:
    after normalization its article cannot be told from a word's own first letters (ألف and
    إله become الف and اله, and لل written for ل before اله would read as لله)."""
    read_as: dict[str, str] = {}
    for prefix in _SHORTEST_FIRST:
        for form in forms:
            read_as.setdefault(prefix + form, form)
    return read_as


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
        if any(holds_words(write, writing) for writing in _read_as([form])):
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
    compared after `normalize_arabic`; empty when it follows them all. A word counts for the
    rule's spelling it holds with the shortest prefix: where a rule lists a spelling both bare
    and with the article, a word written with the article is named once, as the spelling with
    the article. A spelling listed with the article is found with a prefix before it (بال,
    وال), never with its article taken apart (لل is found only before a bare spelling). One
    issue per avoided
    spelling found, however often the reference holds it, in the order of the rules and of
    their spellings; `found` is the spelling as the rule writes it, the first of those that
    normalize alike. Every rule is checked whatever the reference: ValueError for one with a
    spelling that is empty after normalization, or that its own `write` holds."""
    held = normalize_arabic(reference)
    issues: list[SpellingIssue] = []
    for rule in rules:
        avoided = _avoided(rule)
        read_as = _read_as([form for _, form in avoided])
        found = {form for writing, form in read_as.items() if holds_words(held, writing)}
        issues += [
            SpellingIssue(rule=rule.id, found=spelling, write=rule.write)
            for spelling, form in avoided
            if form in found
        ]
    return issues

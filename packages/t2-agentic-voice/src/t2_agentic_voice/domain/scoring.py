"""The evaluation scorers' pure parts: recall of product terms and IDs, and text from silence.

Each scores one output against its reference, both in the form `scored_form` gives (the
canonical normalizer, then digit normalization: what the prototype's scorer compared, D-010,
D-022, with the spelling guide's digits); a caller pools the counts over a stratum. Public
through the `evals` facade (D-021).
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Sequence

from t2_agentic_voice.domain.recall import Recall
from t2_agentic_voice.domain.text.arabic import normalize_arabic
from t2_agentic_voice.domain.text.digits import normalize_digits

_DIGITS = re.compile(r"[0-9]+")


def scored_form(text: str) -> str:
    """`text` as every scorer compares it: `normalize_arabic`, then `normalize_digits`. Words
    are separated by one space, with none at the ends; the verdict and the character error rate
    also remove those spaces."""
    return normalize_digits(normalize_arabic(text))


def _holds(text: str, phrase: str) -> bool:
    """Whether `text` holds `phrase` as whole words, both in their scored form."""
    return f" {phrase} " in f" {text} "


def term_recall(reference: str, output: str, terms: Sequence[str]) -> Recall:
    """Of `terms` that `reference` holds, how many `output` holds too: each a whole word or
    phrase, both texts and every term in their scored form (`normalize_arabic`, then
    `normalize_digits`), and each term counted once, however often a text holds it, and
    however many of `terms` normalize to it. TypeError when `terms` is a str rather than a
    sequence of terms, which would count its letters, or holds anything but a str; ValueError
    when a term is empty after normalization, since no text could hold it."""
    if isinstance(terms, str):
        raise TypeError("terms is a sequence of terms, not one str: put a single term in a list")
    wanted: dict[str, None] = {}  # the terms' scored forms, in order, each once
    for term in terms:
        if not isinstance(term, str):
            raise TypeError("every term is a str")
        form = scored_form(term)
        if not form:
            raise ValueError("a term is empty after normalization, so no text could hold it")
        wanted[form] = None
    held, heard = scored_form(reference), scored_form(output)
    expected = [form for form in wanted if _holds(held, form)]
    return Recall(expected=len(expected), found=sum(_holds(heard, form) for form in expected))


def id_recall(reference: str, output: str) -> Recall:
    """Of the IDs `reference` holds (its runs of digits, in its scored form, so digits said
    one at a time are one ID), how many `output` holds too, each run compared whole. An ID the
    reference holds twice is expected twice, and found as often as the output holds it, up to
    that."""
    expected = Counter(_DIGITS.findall(scored_form(reference)))
    heard = Counter(_DIGITS.findall(scored_form(output)))
    return Recall(expected=expected.total(), found=(expected & heard).total())


def silence_output(output: str) -> int:
    """How much text a provider produced where nothing was said (silence, a noise, or only the
    agent's own echo): the characters of `output` in its scored form, spaces removed; 0 when
    it produced none, or only punctuation."""
    return len(scored_form(output).replace(" ", ""))

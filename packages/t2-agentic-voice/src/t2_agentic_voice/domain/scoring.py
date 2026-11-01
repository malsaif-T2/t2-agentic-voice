"""The evaluation scorers' pure parts: recall of product terms and IDs, and text from silence.

Each recall scores one output against its reference, both in the form `scored_form` gives (the
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


def _stretches(text: str) -> list[list[str]]:
    """The runs of digits `text` holds, in order, in stretches that may join: the words made
    only of digits that stand next to each other are one stretch, and a run inside a word with
    other characters (t1234) is a stretch of its own."""
    stretches: list[list[str]] = [[]]
    for word in text.split():
        if _DIGITS.fullmatch(word):
            stretches[-1].append(word)
        else:
            stretches += [[run] for run in _DIGITS.findall(word)]
            stretches.append([])
    return [stretch for stretch in stretches if stretch]


def _take(groups: list[str], wanted: Counter[str]) -> int:
    """How many IDs of `wanted` the adjacent `groups` write, read from the first group: at each
    group, the longest run of groups from it whose digits, joined, are an ID still wanted is
    taken, that ID is wanted once less, and the reading goes on after it; a group that starts
    no such run is passed."""
    longest = max(map(len, wanted), default=0)  # no ID is longer, so no join need be either
    taken = start = 0
    while start < len(groups):
        number, end = "", start  # the digits joined from `start`, and where the longest ID ends
        for stop in range(start, len(groups)):
            number += groups[stop]
            if len(number) > longest:
                break
            if wanted[number]:
                end = stop + 1
        if end == start:
            start += 1
            continue
        wanted["".join(groups[start:end])] -= 1
        taken += 1
        start = end
    return taken


def id_recall(reference: str, output: str) -> Recall:
    """Of the IDs `reference` holds (its runs of digits, in its scored form, so digits said
    one at a time are one ID), how many `output` holds too, in its scored form: as a run of
    digits, or as words made only of digits that stand next to each other, with no other word
    between them, whose digits joined in order are the ID. So a number written in groups
    ("48 21", "48-21") or with a thousands separator ("4,821", «٤٬٨٢١») holds 4821: the
    normalizer reads every punctuation mark between digits as a space, "." and "/" too.
    Groups in another order, or with a word between them, do not. An ID the reference
    holds twice is expected twice, and found as often as the output holds it, up to that. No
    digit of the output counts for two IDs: the output is read from its start, and at each
    point the longest ID still expected that starts there is taken."""
    wanted = Counter(_DIGITS.findall(scored_form(reference)))  # each taken ID is wanted once less
    expected, found = wanted.total(), 0
    for groups in _stretches(scored_form(output)):
        found += _take(groups, wanted)
    return Recall(expected=expected, found=found)


def silence_output(output: str) -> int:
    """How much text a provider produced where nothing was said (silence, a noise, or only the
    agent's own echo): the characters of `output` after `normalize_arabic`, spaces removed, so a
    digit's name counts its letters as written, not one digit; 0 when it produced none, or only
    punctuation (empty exactly when the scored form is)."""
    return len(normalize_arabic(output).replace(" ", ""))

"""The evaluation scorers' pure parts: recall of product terms and IDs, and text from silence.

Each recall scores one output against its reference, both in the form `scored_form` gives (the
canonical normalizer, then digit normalization: what the prototype's scorer compared, D-010,
D-022, with the spelling guide's digits); a caller pools the counts over a stratum. Public
through the `evals` facade (D-021).
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Collection, Sequence

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


def _occurrences(stretches: list[list[str]], ids: Collection[str]) -> list[list[tuple[str, int]]]:
    """Where `stretches` write each of `ids`: for each group, numbered in order across the
    stretches, the IDs that start at it, each with the number of the group after its end. An ID
    is written by one group, or by a group and those after it in its stretch, whose digits
    joined in order are the ID; two occurrences may share a group."""
    longest = max(map(len, ids), default=0)  # no ID is longer, so no join need be either
    occurrences: list[list[tuple[str, int]]] = []
    for groups in stretches:
        first = len(occurrences)  # the number of the stretch's first group
        for start in range(len(groups)):
            number, here = "", []  # the digits joined from `start`, and the IDs among them
            for stop in range(start, len(groups)):
                number += groups[stop]
                if len(number) > longest:
                    break
                if number in ids:
                    here.append((number, first + stop + 1))
            occurrences.append(here)
    return occurrences


def _worth_going_on(readings: set[tuple[str, ...]]) -> list[tuple[str, ...]]:
    """The readings that reach a group, less each one whose IDs another took too, and more: that
    other can follow it to the end, losing at most the IDs it took beyond, so it finds no fewer."""
    took = {taken: Counter(taken) for taken in readings}
    return [taken for taken in readings if not any(took[taken] < took[other] for other in took)]


def _most_found(occurrences: list[list[tuple[str, int]]], expected: Counter[str]) -> int:
    """The most IDs one reading of the groups finds, no group counting for two IDs and no ID
    found more often than `expected` holds it. At each group a reading passes on, or takes an
    ID that starts there and goes on after its end; every reading worth going on with is
    tried."""
    # For each group, the readings that reach it, each the IDs it took, sorted.
    readings: list[set[tuple[str, ...]]] = [set() for _ in range(len(occurrences) + 1)]
    readings[0].add(())
    for group, here in enumerate(occurrences):
        for taken in _worth_going_on(readings[group]):
            readings[group + 1].add(taken)  # the group is passed
            for number, end in here:
                if taken.count(number) < expected[number]:
                    readings[end].add(tuple(sorted((*taken, number))))
    return max(map(len, readings[-1]))


def id_recall(reference: str, output: str) -> Recall:
    """Of the IDs `reference` holds (its runs of digits, in its scored form, so digits said
    one at a time are one ID), how many `output` holds too, in its scored form: as a run of
    digits, or as words made only of digits that stand next to each other, with no other word
    between them, whose digits joined in order are the ID. So a number written in groups
    ("48 21", "48-21") or with a thousands separator ("4,821", «٤٬٨٢١») holds 4821: the
    normalizer reads every punctuation mark between digits as a space, "." and "/" too.
    Groups in another order, or with a word between them, do not; nor does a group with a
    letter written onto it ("و48 21"), whose digits count only on their own. An ID the
    reference holds twice is expected twice, and found as often as the output holds it, up to
    that. Found is the most IDs one reading of the output finds, no digit of the output
    counting for two, so it is never less than comparing whole runs gives."""
    expected = Counter(_DIGITS.findall(scored_form(reference)))
    occurrences = _occurrences(_stretches(scored_form(output)), expected)
    return Recall(expected=expected.total(), found=_most_found(occurrences, expected))


def silence_output(output: str) -> int:
    """How much text a provider produced where nothing was said (silence, a noise, or only the
    agent's own echo): the characters of `output` after `normalize_arabic`, spaces removed, so a
    digit's name counts its letters as written, not one digit; 0 when it produced none, or only
    punctuation (empty exactly when the scored form is)."""
    return len(normalize_arabic(output).replace(" ", ""))

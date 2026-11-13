"""The output guard's ID rule (the design's 8.2, rule B; plan 006): a pure function with no IO,
run on every clause the talker writes before it goes to text-to-speech, and on a card's text
before it is shown. The runtime's own templates (greetings, notices, progress lines, fixed
phrases) are never checked. The guard (domain/guard.py) runs it after the claim rule
(domain/claims.py), which reads a claim's numbers with it too, against the claimed action's
evidence alone.

What `check_ids` does:

- **Normalize first**, the clause and every evidence text alike: Arabic-Indic and Persian digits
  made ASCII (domain/text/digits.py), the canonical Arabic normalizer (domain/text/arabic.py),
  which reads punctuation as a space, then digits said or written one at a time collapsed into
  one number («أربعة خمسة اثنين واحد», "four five two one", "4 5 2 1" all read "4521"). The
  prompt tells the talker to write numbers as digits, and the speaking rules turn them into
  words after the guard, so the guard sees digits.
- **Digits in groups.** Numbers that stand next to each other as whole words, with only a space
  (or, before normalizing, a mark) between them, are one group, read as their digits joined:
  "4521 3390", "45-21-33" and "1,234" are each one token, a ticket number read in groups. But
  numbers joined by a colon, a point or a slash (a time, "16:00"; a decimal, "12.75"; "24/7";
  "7/11/2026"), or by the hyphens of a date around a year ("7-11-2026", or the prompt's own
  date, "2026-11-07"; the non-breaking hyphen, the en dash or the minus a model writes for '-'
  alike), are each read alone, joined to no number beside them. The current year and the next
  (`year`, `year + 1`) pass with no evidence, since the prompt holds the current date, and each
  ends a group, so "6 2026" is a day and a year, not a number of five digits.
- **ID-shaped** is a group of `guard.min_id_digits` digits or more, a run of digits that long
  inside a word ("lt00423"), or a match of one of `guard.id_patterns`, read on the clause as
  written with its digits made ASCII.
- **Evidence:** a group passes when its digits joined are a number of the evidence seen this
  call, normalized the same way (a run, or a group joined), or when each of its numbers is one
  and ID-shaped itself ("3390 7788" said from "4521 3390 7788"); short numbers never vouch for
  a group, so an ID read in pairs ("45 21 33") is checked whole. A pattern's match passes when
  the evidence holds it as whole words, normalized. The evidence is the call's record, the
  results of its tools (passages included) and the caller's own heard words.
- **The verdict:** `IdVerdict(passed=True)` when every token passes; otherwise not passed, with
  the tokens that had no evidence, normalized, each once, which go to the talker's history as a
  developer note and never to the caller. What a blocked clause drops is `guard.on_block`'s, and
  the session's (a fixed phrase, a `GuardBlocked` event).

Numbers said as number words ("twenty-one") are not read (domain/text/digits.py says why), so
one said so passes unseen: the prompt asks for digits. The text after an action call (rule C)
is the talker's turn's (agent/turn.py).
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from functools import lru_cache

from pydantic import BaseModel, ConfigDict

from t2_agentic_voice.core.settings.guard import GuardSettings
from t2_agentic_voice.domain.text.arabic import normalize_arabic
from t2_agentic_voice.domain.text.digits import DIGIT_CHARACTERS, normalize_digits
from t2_agentic_voice.domain.text.words import holds_words

# A word of ASCII digits only, as normalizing leaves a number; and a run of them in a word.
_NUMBER = re.compile("[0-9]+")
# The forms whose numbers are each read alone, in a text with its digits made ASCII (the module's
# docstring): numbers joined by a colon, a point (the Arabic decimal one too) or a slash, the
# first one's thousands kept whole ("1,234.50"), and a date with hyphens around a year, the day
# and the month either way round, or the year first. A hyphen is '-' or one a model writes for
# it: the hyphen, the non-breaking hyphen (the OpenAI family's), the figure dash, the en dash
# (U+2010 to U+2013) and the minus sign. `_APART_MARK` is what cuts each form.
_DAY, _MONTH, _YEAR = "(?:0?[1-9]|[12][0-9]|3[01])", "(?:0?[1-9]|1[0-2])", "(?:19|20)[0-9]{2}"
_HYPHEN = "[-\u2010-\u2013\u2212]"
_APART = re.compile(
    "[0-9]+(?:[,\u066c][0-9]{3})*(?:[:./\u066b][0-9]+)+"
    f"|(?<![0-9])(?:(?:{_DAY}{_HYPHEN}{_MONTH}|{_MONTH}{_HYPHEN}{_DAY}){_HYPHEN}{_YEAR}"
    f"|{_YEAR}{_HYPHEN}{_MONTH}{_HYPHEN}{_DAY})(?![0-9])"
)
_APART_MARK = re.compile("[-\u2010-\u2013\u2212:./\u066b]")


class IdVerdict(BaseModel):
    """What rule B made of a clause: whether it `passed`, and when not, the ID-shaped tokens it
    holds with no evidence (`unsupported`), as normalized."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    passed: bool
    unsupported: tuple[str, ...] = ()


@lru_cache(maxsize=4096)
def guard_form(text: str) -> str:
    """`text` as the guard reads it (the module's docstring): ASCII digits, the canonical
    normalizer's form, digits said one at a time joined."""
    return normalize_digits(normalize_arabic(text.translate(DIGIT_CHARACTERS)))


def _pieces(text: str) -> list[str]:
    """`text` as the guard reads it (`guard_form`), cut around each number of an `_APART` form, at
    a NUL, which no clause holds, put on each side of it."""
    written = text.translate(DIGIT_CHARACTERS)
    cut = _APART.sub(lambda apart: "\0" + _APART_MARK.sub("\0", apart.group()) + "\0", written)
    return [guard_form(piece) for piece in cut.split("\0")]


def _groups(text: str, year: int) -> tuple[list[list[str]], list[str]]:
    """The groups of numbers standing next to each other as whole words in `text` as the guard
    reads it (each the list of its numbers), and the runs of digits inside other words; an
    exempt year (`year`, the next) is in neither, and ends a group, as a cut of `_pieces`
    does."""
    exempt = (str(year), str(year + 1))
    groups: list[list[str]] = []
    inside: list[str] = []
    for piece in _pieces(text):
        group: list[str] = []
        for word in piece.split():
            if _NUMBER.fullmatch(word) and word not in exempt:
                group.append(word)
                continue
            if group:
                groups.append(group)
                group = []
            inside += [run for run in _NUMBER.findall(word) if run not in exempt]
        if group:
            groups.append(group)
    return groups, inside


@lru_cache(maxsize=4096)
def _numbers(text: str, year: int) -> frozenset[str]:
    """Every number an evidence `text` holds, normalized: each run, and each group joined."""
    groups, inside = _groups(text, year)
    return frozenset(
        [*inside, *(number for group in groups for number in group)]
        + ["".join(group) for group in groups]
    )


def _supported(group: list[str], known: frozenset[str], shortest: int) -> bool:
    """Whether the evidence's numbers (`known`) hold `group`: its digits joined, or, for a
    group of more than one number, each of its numbers, each ID-shaped itself (`shortest`
    digits or more), so short numbers never vouch for an ID read in pairs."""
    if "".join(group) in known:
        return True
    return len(group) > 1 and all(len(n) >= shortest and n in known for n in group)


def check_ids(
    clause: str, *, evidence: Iterable[str], settings: GuardSettings, year: int
) -> IdVerdict:
    """Rule B on `clause`: every ID-shaped token in it must appear in `evidence`, the texts seen
    this call that may hold one (the record, the tools' results, the caller's heard words), or
    be `year` or the next (the module's docstring)."""
    texts = tuple(evidence)
    known = frozenset().union(*(_numbers(text, year) for text in texts))
    groups, inside = _groups(clause, year)
    shortest = settings.min_id_digits
    unsupported = [
        "".join(group)
        for group in groups
        if len("".join(group)) >= shortest and not _supported(group, known, shortest)
    ]
    unsupported += [run for run in inside if len(run) >= shortest and run not in known]
    if settings.id_patterns:
        written = clause.translate(DIGIT_CHARACTERS)
        normals = [guard_form(text) for text in texts]
        for pattern in settings.id_patterns:
            for match in re.finditer(pattern, written):
                token = guard_form(match.group())
                if token and not any(holds_words(normal, token) for normal in normals):
                    unsupported.append(token)
    found = tuple(dict.fromkeys(unsupported))
    return IdVerdict(passed=not found, unsupported=found)

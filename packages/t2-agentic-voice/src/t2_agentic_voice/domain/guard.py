"""The output guard's ID rule (the design's 8.2, rule B; plan 006): a pure function with no IO,
run on every clause the talker writes before it goes to text-to-speech, and on a card's text
before it is shown. The runtime's own templates (greetings, notices, progress lines, fixed
phrases) are never checked.

What `check_ids` does:

- **Normalize first**, the clause and every evidence text alike: Arabic-Indic and Persian digits
  made ASCII (domain/text/digits.py), the canonical Arabic normalizer (domain/text/arabic.py),
  which reads punctuation as a space, then digits said or written one at a time collapsed into
  one number («أربعة خمسة اثنين واحد», "four five two one", "4 5 2 1" all read "4521"). The
  prompt tells the talker to write numbers as digits, and the speaking rules turn them into
  words after the guard, so the guard sees digits.
- **Digits in groups.** Numbers that stand next to each other as whole words, with only a space
  (or, before normalizing, a mark) between them, are one group, read as their digits joined:
  "4521 3390", "45-21-33", "1,234" and "12.75" are each one token. The current year and the next
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
one said so passes unseen: the prompt asks for digits. Claims (rule A) and the text after an
action call (rule C) come with the actions.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from functools import lru_cache

from pydantic import BaseModel, ConfigDict

from t2_agentic_voice.core.settings.guard import GuardSettings
from t2_agentic_voice.domain.text.arabic import normalize_arabic
from t2_agentic_voice.domain.text.digits import _DIGIT_CHARACTERS, normalize_digits
from t2_agentic_voice.domain.text.words import holds_words

# A word of ASCII digits only, as normalizing leaves a number; and a run of them in a word.
_NUMBER = re.compile("[0-9]+")


class IdVerdict(BaseModel):
    """What rule B made of a clause: whether it `passed`, and when not, the ID-shaped tokens it
    holds with no evidence (`unsupported`), as normalized."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    passed: bool
    unsupported: tuple[str, ...] = ()


@lru_cache(maxsize=4096)
def _normal(text: str) -> str:
    """`text` as the guard reads it (the module's docstring): ASCII digits, the canonical
    normalizer's form, digits said one at a time joined."""
    return normalize_digits(normalize_arabic(text.translate(_DIGIT_CHARACTERS)))


def _groups(normal: str, year: int) -> tuple[list[list[str]], list[str]]:
    """The groups of numbers standing next to each other as whole words in `normal` (each the
    list of its numbers), and the runs of digits inside other words; an exempt year (`year`,
    the next) is in neither, and ends a group."""
    groups: list[list[str]] = []
    inside: list[str] = []
    group: list[str] = []
    for word in normal.split():
        if _NUMBER.fullmatch(word) and word not in (str(year), str(year + 1)):
            group.append(word)
            continue
        if group:
            groups.append(group)
            group = []
        inside += [run for run in _NUMBER.findall(word) if run not in (str(year), str(year + 1))]
    if group:
        groups.append(group)
    return groups, inside


@lru_cache(maxsize=4096)
def _numbers(text: str, year: int) -> frozenset[str]:
    """Every number an evidence `text` holds, normalized: each run, and each group joined."""
    groups, inside = _groups(_normal(text), year)
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
    groups, inside = _groups(_normal(clause), year)
    shortest = settings.min_id_digits
    unsupported = [
        "".join(group)
        for group in groups
        if len("".join(group)) >= shortest and not _supported(group, known, shortest)
    ]
    unsupported += [run for run in inside if len(run) >= shortest and run not in known]
    if settings.id_patterns:
        written = clause.translate(_DIGIT_CHARACTERS)
        normals = [_normal(text) for text in texts]
        for pattern in settings.id_patterns:
            for match in re.finditer(pattern, written):
                token = _normal(match.group())
                if token and not any(holds_words(normal, token) for normal in normals):
                    unsupported.append(token)
    found = tuple(dict.fromkeys(unsupported))
    return IdVerdict(passed=not found, unsupported=found)

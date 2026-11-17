"""Run F's lean outcome mode's `repeat` (lean_checks.py; the lead's amendments of 2026-11-18, the
flight spec's 13): the library's repeat measures (`find_repeat`, D-101, never a copy), each earlier
reply read on its own, and two exceptions, since the lean agent's read-back is its own words where
the scripted agent's was the runtime's line, which no repeat check reads:

- **A reply with new facts.** A near repeat counts unless the later reply states a fact the
  earlier one did not (`Facts.beyond`): a number token once `normalize_digits` has read it
  (days, times, fares, totals, travelers), a weekday or a city. A read-back after a change
  (f14's «مسافر واحد ... 260» made «مسافرين اثنين ... 520») or another day's listing in the same
  frame (f25's) is no repeat; a reply that only leaves a fact out (f22's booked trip said again
  without its arrival) still is, and an identical repeat always is. The word one, «واحد», is no
  fact: mostly a pronoun ("Which one", "one-way", «أي واحد»), and a change of travelers moves
  the total.
- **The first clause alone.** A near repeat found by its first clause (of 3 words or more) whose
  whole overlap is under the near-repeat threshold is no repeat (f19's required «ما أقدر أأكد إذا
  تم الحجز ولا لا» said again with a new sentence).

A reply's facts are read from its words as written (`TurnRead.written`: digits and all, where a
long English clause is heard with its numbers in words), or from what was heard when none was kept.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import Final

from t2_agentic_voice.evals import Repeat, find_repeat
from t2_agentic_voice.languages import normalize_digits

from flight_voice.airline.airports import find_airport
from flight_voice.evals.spoken import form

# The library's near-repeat threshold (testing/repeats.py's NEAR_REPEAT_OVERLAP, which the
# `evals` facade does not give), held equal to it by a test.
NEAR_REPEAT_OVERLAP: Final = 0.8
WEEKDAYS: Final = frozenset(
    form(day)
    for day in (
        *("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"),
        *("الاثنين", "الإثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"),
    )
)
_NUMBER: Final = re.compile(r"[0-9]+(?:[:.][0-9]+)*")
_THOUSANDS: Final = re.compile(r"(?<=[0-9]),(?=[0-9]{3}(?![0-9]))")  # "2,290" is 2290
_PARTS: Final = re.compile(r"[:.]")
_ONE: Final = re.compile(r"\b(?:one|واحد)\b", re.IGNORECASE)  # no fact (the module's docstring)
_AND: Final = "و"  # wa, "and", written on the word it joins: «والخميس»


@dataclass(frozen=True)
class Facts:
    """What a reply states: its number tokens (without their leading zeros, a time's point
    a colon, so "09:10", "9:10" and "9.10" are one; never the word one), and its weekday and
    city words (a city by its airport's code)."""

    numbers: frozenset[str]
    weekdays: frozenset[str]
    cities: frozenset[str]

    def beyond(self, other: Facts) -> bool:
        """Whether these facts hold one that `other` does not: a number, a weekday or a city."""
        return bool(
            self.numbers - other.numbers
            or self.weekdays - other.weekdays
            or self.cities - other.cities
        )


@dataclass(frozen=True)
class Said:
    """One reply of the talker's: what the caller heard of its own words, which the repeat
    measures read, and its words as written, which its facts are read from."""

    heard: str
    written: str


def facts(text: str) -> Facts:
    """The facts `text` states (the module's docstring)."""
    plain = _THOUSANDS.sub("", normalize_digits(_ONE.sub(" ", text)))
    numbers = frozenset(
        _PARTS.sub(":", number.lstrip("0") or "0") for number in _NUMBER.findall(plain)
    )
    words = form(text).split()
    words += [w.removeprefix(_AND) for w in words if w.startswith(_AND) and len(w) > 2]
    cities = frozenset(place.code for w in words if (place := find_airport(w)) is not None)
    return Facts(numbers, frozenset(w for w in words if w in WEEKDAYS), cities)


def lean_repeat(reply: Said, earlier: Sequence[Said], *, asks_repeat: bool) -> Repeat | None:
    """The repeat `reply` makes of one of the replies before it, `earlier` in the order they
    were said, or None (the module's docstring); the latest is named."""
    if asks_repeat:
        return None
    for place in range(len(earlier) - 1, -1, -1):
        before = earlier[place]
        found = find_repeat(reply.heard, [before.heard])
        if found is None:
            continue
        if found.kind == "near":
            if found.by == "first_clause" and found.overlap < NEAR_REPEAT_OVERLAP:
                continue
            if facts(reply.written).beyond(facts(before.written)):
                continue
        return replace(found, earlier=place)
    return None

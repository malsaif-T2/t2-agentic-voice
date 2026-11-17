"""Run F's outcome mode, for the lean agent (`poe eval-flights --agent lean`; D-113): what a play
did is scored by its outcomes, never by the script of tools and lines the scripted agent keeps.

**Kept checks** (checks.py's, the same code): `failure`; `violations`, which here also count
each model reply the plain-speech rule drops (lean_call.py) and each turn whose words claim a
booking («تم الحجز», "booked", "is all set" and the like: the booking's claim phrases and a few
more; never one negated, asked, or put ahead or under a condition, "It will be booked once you
say yes") before the store held one (`lean_violations`); `booked`, one booking exactly when the
scenario books (a turn whose outcome is `done`), holding its read-back's flights, days,
travelers and cabin, for the demo traveler alone, and none otherwise; `reference`; and on each
turn `language`, `register`, `stage_note`, `notice`, `max_words` and `repeat`.

**Not used:** `calls`, `args`, `outcome` (its read-back and ask-again; a scenario whose
`asked_again` only makes sense for the library's read-back counts on its booking alone),
`own_summary`, `said_any`, `said_none`, `max_options`, `card`, `progress` and `cut_repeat`.

**New measures, reported, never pass or fail** (`Measures`): the caller turns until the booking,
the seconds until it, and the words the agent said in the call (its own, heard).
"""

from __future__ import annotations

import re
from collections.abc import Iterator, Sequence
from statistics import mean
from typing import Final

from pydantic import BaseModel, ConfigDict
from t2_agentic_voice.evals import find_repeat
from t2_agentic_voice.languages import split_clauses

from flight_voice.booking import lines
from flight_voice.evals.call import PlayRead, TurnRead
from flight_voice.evals.checks import (
    Failed,
    booking_checks,
    language_checks,
    own,
    reference_checks,
    said,
)
from flight_voice.evals.lean_call import LeanRead
from flight_voice.evals.scenarios import Scenario
from flight_voice.evals.spoken import failure_notices, form, stage_note

# Phrases that claim a booking beside the booking's own claims (booking/lines.py).
MORE_CLAIMS: Final = ("is all set", "all booked", "تم حجز رحلتك", "حجزتها")
# "booked" alone claims one in a clause that is no question and holds no negation.
_BOOKED: Final = re.compile(r"\bbooked\b")
_NEGATION: Final = re.compile(r"\b(not|nothing|never|no|yet)\b|n['\u2019]t\b")
# A word that puts the booking ahead or under a condition ("It will be booked once you say
# yes", "I can get that booked"), in the scorers' form ("I'll" is "i ll"): before a claim in its
# sentence, the claim is no claim yet.
_NOT_YET: Final = re.compile(
    r"\b(will|ll|d|can|could|would|shall|should|may|might|get|once|when|if|before|after"
    r"|until|unless|soon)\b|\bsay (yes|the word)\b"
)
_SENTENCE_END: Final = (".", "!", "?", "؟")
# The Arabic negations (ma, lam, lan, mu, laysa), in the scorers' form.
_NOT_AR: Final = frozenset(form(w) for w in ("ما", "لم", "لن", "مو", "ليس", "ماتم"))


class Measures(BaseModel):
    """A lean play's measures (the module's docstring); none of the booking's when none was
    made."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    turns_to_booking: int | None = None
    seconds_to_booking: float | None = None
    words: int = 0


def _phrases() -> tuple[str, ...]:
    claims = [p for tag in lines.CLAIMS.phrases for p in lines.CLAIMS.for_language(tag)]
    return tuple(" ".join(form(p).lower().split()) for p in (*claims, *MORE_CLAIMS))


def claims_booking(text: str) -> bool:
    """Whether `text`, the agent's own words, claims a booking (the module's docstring): a clause
    that holds a claim's phrase as whole words, or "booked" in a clause that is no question,
    with no negation in either («ما تم الحجز», "nothing is booked yet"), and no word before
    the claim in its sentence that puts it ahead or under a condition (`_NOT_YET`: "will",
    "can", "once", "if" and the like; "Once you agree, you're booked")."""
    ahead = False  # a word of `_NOT_YET` in the sentence's clauses before this one
    for clause in split_clauses(text, max_chars=None):
        plain = f" {' '.join(form(clause).lower().split())} "
        hits = [plain.find(f" {phrase} ") for phrase in _phrases()]
        bare = _BOOKED.search(plain)
        if bare is not None and "?" not in clause and "؟" not in clause:
            hits.append(bare.start())
        first = min((at for at in hits if at >= 0), default=None)
        negated = _NEGATION.search(clause.lower()) or set(plain.split()) & _NOT_AR
        if first is not None and not negated and not ahead and not _NOT_YET.search(plain[:first]):
            return True
        ended = clause.rstrip().endswith(_SENTENCE_END)
        ahead = not ended and (ahead or _NOT_YET.search(plain) is not None)
    return False


def lean_violations(read: PlayRead) -> tuple[str, ...]:
    """What a lean play broke beyond the call's own checks: each reply the plain-speech rule
    drops, and each turn that claims a booking before the store held one."""
    lean = read if isinstance(read, LeanRead) else None
    drops = 0 if lean is None else lean.drops
    found = [f"plain speech: a reply dropped as no speech ({n} of {drops})" for n in range(drops)]
    first = None if lean is None else lean.booked_index
    for turn in read.turns:
        if turn is None or not claims_booking(said(own(turn.heard))):
            continue
        if first is None and read.made:
            continue  # booked at a turn not read: its claims are not held against it
        if first is None or turn.index < first:
            found.append(f"turn {turn.index + 1}: a booking claimed before the store held one")
    return tuple(found)


def lean_turn_checks(scenario: Scenario, n: int, reads: Sequence[TurnRead | None]) -> Iterator[str]:
    """The kept checks turn `n` of `scenario` fails (the module's docstring)."""
    turn, read = scenario.turns[n], reads[n]
    if turn.stop:
        return
    if read is None:
        yield "said"
        return
    words = own(read.heard)
    text = said(words)
    yield from language_checks(scenario, turn, words)
    if len(text.split()) > turn.max_words:
        yield "max_words"
    earlier = [said(own(r.heard)) for r in reads[:n] if r is not None]
    if find_repeat(text, earlier, asks_repeat=turn.asks_repeat) is not None:
        yield "repeat"
    if read.blocked or any(c.phrase and form(c.text) in failure_notices() for c in read.heard):
        yield "notice"
    if stage_note(said(read.heard)):
        yield "stage_note"


def lean_failures(scenario: Scenario, read: PlayRead) -> tuple[Failed, ...]:
    """Every kept check one lean play of `scenario` failed (the module's docstring)."""
    found: list[Failed] = []
    if read.failure is not None:
        found.append(Failed("failure"))
    if read.violations or lean_violations(read):
        found.append(Failed("violations"))
    found += [Failed(name) for name in booking_checks(scenario, read)]
    found += reference_checks(scenario, read)
    for n in range(len(scenario.turns)):
        found += [Failed(name, n + 1) for name in lean_turn_checks(scenario, n, read.turns)]
    return tuple(found)


def measures(read: PlayRead) -> Measures:
    """A lean play's measures (the module's docstring)."""
    words = sum(len(said(own(t.heard)).split()) for t in read.turns if t is not None)
    if not isinstance(read, LeanRead):
        return Measures(words=words)
    return Measures(
        turns_to_booking=read.booked_turns, seconds_to_booking=read.booked_s, words=words
    )


def mean_measures(each: Sequence[Measures | None]) -> dict[str, float]:
    """Each measure's mean over the plays that have it, rounded; none with no play."""
    found: dict[str, float] = {}
    for name in Measures.model_fields:
        values = [v for m in each if m is not None and (v := getattr(m, name)) is not None]
        if values:
            found[name] = round(mean(values), 2)
    return found

"""Run F's outcome mode, for the lean agent (`poe eval-flights --agent lean`; D-113): what a play
did is scored by its outcomes, never by the script of tools and lines the scripted agent keeps.

**Kept checks** (checks.py's, the same code, but where the lead's amendments of 2026-11-18 say
otherwise): `failure`; `violations`, which here also count each model reply the plain-speech
rule drops (lean_call.py) and each turn whose words claim a booking («تم الحجز», "booked", "is
all set" and the like: the booking's claim phrases and a few more; never one negated, asked, or
put ahead or under a condition, "It will be booked once you say yes") before the store held one
(`lean_violations`); `booked`, one booking exactly when the
scenario books (a turn whose outcome is `done`), holding its read-back's flights, days,
travelers and cabin, for the demo traveler alone, and none otherwise; `reference`; and on each
turn `language`, `register`, `stage_note`, `notice`, `max_words` and `repeat`.

**The amendments** (the flight spec's 13): `booked` takes a leg picked by fare (the scenario's
`cheapest`, `dearest` or `fare` pick for it) whose read-back flight ties another of its route
that day at its price in the cabin for the travelers, by what the flight source answered in the
play (the airline's own fares when the play kept none), as either flight (f30's "the
dearest" on 19 Nov, T2 102 and T2 106 at 470), all else held as before; `repeat` is
lean_repeats.py's, a near repeat counting unless the later reply states a new fact, and never
on a first clause alone; `max_words` counts the reply as written (`TurnRead.written`, the
guard's text, digits one word each), in every language, where the caller hears an English
clause cut into several requests with its numbers in words; the cap is the scenario's.

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
from t2_agentic_voice.languages import split_clauses

from flight_voice.airline.fares import fare
from flight_voice.airline.profile import TRAVELER
from flight_voice.airline.schedule import Cabin, departure, departures, find_flight
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
from flight_voice.evals.lean_repeats import Said, lean_repeat
from flight_voice.evals.scenarios import FlightOn, Scenario
from flight_voice.evals.spoken import failure_notices, form, stage_note
from flight_voice.flight_data.queries import DayOffers
from flight_voice.trip import LegKind

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
# The picks by fare, where two flights at one fare fit the pick alike.
BY_FARE: Final = frozenset({"cheapest", "dearest", "fare"})


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


def tied(
    leg: FlightOn, cabin: Cabin, answered: Sequence[DayOffers] = (), *, travelers: int = 1
) -> frozenset[int]:
    """`leg`'s flight and each flight of its route that day at its price in `cabin` for
    `travelers`, by the answers the play's source gave (`answered`: the one whose query has the
    leg's day, the cabin and the travelers and holds the leg's flight); by the airline's own
    fares when the play kept no answer; its flight alone when none holds it."""
    if answered:
        return _tied_in(leg, cabin, answered, travelers)
    flight = find_flight(leg.number)
    wanted = None if flight is None else fare(departure(flight, leg.day), cabin)
    if flight is None or wanted is None:
        return frozenset({leg.number})
    same_day = departures(flight.origin, flight.destination, leg.day)
    return frozenset({leg.number, *(d.flight.number for d in same_day if fare(d, cabin) == wanted)})


def _tied_in(
    leg: FlightOn, cabin: Cabin, answered: Sequence[DayOffers], travelers: int
) -> frozenset[int]:
    number = str(leg.number)
    for answer in answered:
        q = answer.query
        if (q.day, q.cabin, q.adults) != (leg.day, cabin, travelers):
            continue
        own = next((o for o in answer.offers if o.segments[0].number == number), None)
        if own is None:
            continue
        same = (o.segments[0].number for o in answer.offers if o.price == own.price)
        return frozenset({leg.number, *(int(n) for n in same if n.isdigit())})
    return frozenset({leg.number})


def _by_fare(scenario: Scenario, leg: LegKind) -> bool:
    """Whether the scenario's last pick of `leg` is by fare (`BY_FARE`)."""
    picks = [t.args.pick for t in scenario.turns if t.args.leg == leg and t.args.pick]
    return bool(picks) and picks[-1] in BY_FARE


def _booked_alike(scenario: Scenario, read: PlayRead) -> bool:
    """Whether the play's one booking, the demo traveler's, holds the last read-back's trip, a
    leg picked by fare as any flight tied with its own (the module's docstring)."""
    backs = [t.read_back for t in scenario.turns if t.read_back is not None]
    mine = [b for b in read.made if b.traveler_id == TRAVELER.id]
    if not backs or len(mine) != 1 or not any(t.outcome == "done" for t in scenario.turns):
        return False
    back, (booking,) = backs[-1], mine
    wanted: list[tuple[LegKind, FlightOn]] = [("outbound", back.outbound)]
    if back.return_ is not None:
        wanted.append(("return", back.return_))
    kept = (booking.travelers, booking.cabin) == (back.travelers, back.cabin)
    answered = read.answered if isinstance(read, LeanRead) else ()
    return (
        kept
        and len(booking.legs) == len(wanted)
        and all(
            leg.day == want.day
            and (
                leg.flight == want.number
                or (
                    _by_fare(scenario, kind)
                    and leg.flight in tied(want, back.cabin, answered, travelers=back.travelers)
                )
            )
            for leg, (kind, want) in zip(booking.legs, wanted, strict=False)
        )
    )


def lean_booking_checks(scenario: Scenario, read: PlayRead) -> Iterator[str]:
    """checks.py's `booking_checks`, a booking of a flight tied with the read-back's on a leg
    picked by fare held as the read-back's (the module's docstring)."""
    for name in booking_checks(scenario, read):
        if name != "booked" or not _booked_alike(scenario, read):
            yield name


def _said(read: TurnRead) -> Said:
    """A turn's reply as lean_repeats.py reads it: its own words heard, and as written (what
    was heard when the play kept none)."""
    heard = said(own(read.heard))
    return Said(heard=heard, written=" ".join(read.written) if read.written else heard)


def lean_turn_checks(scenario: Scenario, n: int, reads: Sequence[TurnRead | None]) -> Iterator[str]:
    """The kept checks turn `n` of `scenario` fails (the module's docstring)."""
    turn, read = scenario.turns[n], reads[n]
    if turn.stop:
        return
    if read is None:
        yield "said"
        return
    words = own(read.heard)
    reply = _said(read)
    yield from language_checks(scenario, turn, words)
    if len(reply.written.split()) > turn.max_words:
        yield "max_words"
    earlier = [_said(r) for r in reads[:n] if r is not None]
    if lean_repeat(reply, earlier, asks_repeat=turn.asks_repeat) is not None:
        yield "repeat"
    if read.blocked or any(c.phrase and form(c.text) in failure_notices() for c in read.heard):
        yield "notice"
    if stage_note(said(read.heard)):
        yield "stage_note"


def lean_reference_checks(scenario: Scenario, read: PlayRead) -> list[Failed]:
    """`reference` for the lean agent: a turn that asks for the booking's reference and is not
    answered with it fails; a reference said unasked does not (the owner, 2026-11-18: "saying
    the reference unasked is fine, it is not a hard requirement")."""
    found = reference_checks(scenario, read)
    return [f for f in found if f.turn is not None and scenario.turns[f.turn - 1].asks_reference]


def lean_failures(scenario: Scenario, read: PlayRead) -> tuple[Failed, ...]:
    """Every kept check one lean play of `scenario` failed (the module's docstring)."""
    found: list[Failed] = []
    if read.failure is not None:
        found.append(Failed("failure"))
    if read.violations or lean_violations(read):
        found.append(Failed("violations"))
    found += [Failed(name) for name in lean_booking_checks(scenario, read)]
    found += lean_reference_checks(scenario, read)
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

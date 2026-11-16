"""The rules a set of the flight agent's scripted calls keeps (evals/scenarios.py), each broken one
said by `problems` with its fix:

- no id is held twice;
- every kind has a dev scenario and a held-out one;
- a dev scenario and a held-out one never share a leg, the same route on the same day (as a
  date a search held, or a flight a read-back holds);
- every need is on the closed list (`NEEDS`);
- every date a turn's calls held has the form the caller's words name, and that form resolves
  by the airline's own date code against the scenario's today to that date (a return counted
  from the departure the turn, or the last turn before it, held); no form stands without its
  date;
- every flight a read-back holds flies on its day, inside the booking window, sells its cabin
  with a seat for each traveler, on a day a turn's search held; a return flies the outbound's
  route back;
- a `repeat_of_cut` turn comes right after a stop.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterator, Sequence
from datetime import date

from flight_voice.airline.airports import HOME, Code
from flight_voice.airline.dates import DateSpec, Resolved, resolve_departure, resolve_return
from flight_voice.airline.fares import seats_left
from flight_voice.airline.schedule import departures, find_flight, window
from flight_voice.evals.scenarios import NEEDS, FlightOn, ReadBack, Scenario

Leg = tuple[Code, Code, date]


def problems(scenarios: Sequence[Scenario]) -> list[str]:
    """Every rule `scenarios` break (the module's docstring), each said with its fix."""
    found = _twice(scenarios) + _kinds(scenarios) + _shared(scenarios)
    for scenario in scenarios:
        found += [
            f"{scenario.id}: needs '{name}', which is not on the closed list "
            f"({', '.join(NEEDS)}). FIX: name a listed capability, or add it with its docstring."
            for name in scenario.needs
            if name not in NEEDS
        ]
        found += _dates(scenario) + _read_backs(scenario) + _cuts(scenario)
    return found


def _twice(scenarios: Sequence[Scenario]) -> list[str]:
    seen: defaultdict[str, int] = defaultdict(int)
    for scenario in scenarios:
        seen[scenario.id] += 1
    return [
        f"{name}: {count} scenarios hold this id. FIX: give each its own id and file name."
        for name, count in seen.items()
        if count > 1
    ]


def _kinds(scenarios: Sequence[Scenario]) -> list[str]:
    splits: defaultdict[str, set[str]] = defaultdict(set)
    for scenario in scenarios:
        splits[scenario.kind].add(scenario.split)
    return [
        f"the kind '{kind}' has no {split} scenario. FIX: write one, on other routes and words."
        for kind, held in sorted(splits.items())
        for split in ("dev", "held-out")
        if split not in held
    ]


def _shared(scenarios: Sequence[Scenario]) -> list[str]:
    dev = [s for s in scenarios if s.split == "dev"]
    held_out = [s for s in scenarios if s.split == "held-out"]
    return [
        f"{d.id} and {h.id}: a dev and a held-out scenario share the leg {a} to {b} on "
        f"{day.isoformat()}. FIX: move the held-out one to another route or day."
        for d in dev
        for h in held_out
        for a, b, day in sorted(legs(d) & legs(h))
    ]


def legs(scenario: Scenario) -> set[Leg]:
    """Each route on its day that `scenario`'s searches held or its read-backs hold."""
    found: set[Leg] = set()
    for turn in scenario.turns:
        args = turn.args
        if args.destination is not None and args.depart is not None:
            origin = args.origin or HOME
            found.add((origin, args.destination, args.depart))
            if args.return_date is not None:
                found.add((args.destination, origin, args.return_date))
        if turn.read_back is not None:
            for leg in _flights(turn.read_back):
                if (flight := find_flight(leg.number)) is not None:
                    found.add((flight.origin, flight.destination, leg.day))
    return found


def _flights(read_back: ReadBack) -> tuple[FlightOn, ...]:
    back = read_back.return_
    return (read_back.outbound,) if back is None else (read_back.outbound, back)


def _dates(scenario: Scenario) -> list[str]:
    found: list[str] = []
    depart: date | None = None
    for n, turn in enumerate(scenario.turns, 1):
        args, forms = turn.args, turn.forms
        depart = args.depart or depart
        for name, expected, form in (
            ("depart", args.depart, forms.depart),
            ("return_date", args.return_date, forms.return_date),
            ("from_date", args.from_date, forms.from_date),
        ):
            where = f"{scenario.id}, turn {n}, {name}"
            if expected is None and form is None:
                continue
            if expected is None or form is None:
                found.append(f"{where}: a date and its form go together. FIX: give both.")
                continue
            got = _resolved(name, form, depart, scenario.today)
            if got != expected:
                shown = "no date" if got is None else got.isoformat()
                found.append(
                    f"{where}: its form resolves to {shown} against {scenario.today}, not "
                    f"{expected}. FIX: write the day the airline's date code gives."
                )
    return found


def _resolved(name: str, form: DateSpec, depart: date | None, today: date) -> date | None:
    if name == "return_date":
        got = None if depart is None else resolve_return(form, depart, today)
    else:
        got = resolve_departure(form, today)
    return got.day if isinstance(got, Resolved) else None


def _read_backs(scenario: Scenario) -> list[str]:
    searched = {d for t in scenario.turns for d in (t.args.depart, t.args.return_date) if d}
    first, last = window(scenario.today)
    found: list[str] = []
    for n, turn in enumerate(scenario.turns, 1):
        if (read_back := turn.read_back) is None:
            continue
        for leg in _flights(read_back):
            where = f"{scenario.id}, turn {n}: flight {leg.number} on {leg.day.isoformat()}"
            flight = find_flight(leg.number)
            if flight is None or not first <= leg.day <= last:
                found.append(f"{where} is not one the airline sells. FIX: pick a listed one.")
                continue
            flown = {
                d.flight.number for d in departures(flight.origin, flight.destination, leg.day)
            }
            if leg.number not in flown or read_back.cabin not in flight.cabins:
                found.append(f"{where} does not fly that day in {read_back.cabin}. FIX: pick one.")
            elif seats_left(flight, leg.day, read_back.cabin) < read_back.travelers:
                found.append(f"{where} has too few seats. FIX: pick a day it has them.")
            if leg.day not in searched:
                found.append(f"{where}: no search held that day. FIX: read back a searched day.")
        found += _round(scenario.id, n, read_back)
    return found


def _round(name: str, n: int, read_back: ReadBack) -> Iterator[str]:
    out, back = find_flight(read_back.outbound.number), read_back.return_
    if back is None or out is None or (flight := find_flight(back.number)) is None:
        return
    if (flight.origin, flight.destination) != (out.destination, out.origin):
        yield f"{name}, turn {n}: the return does not fly the outbound's route back. FIX: one."


def _cuts(scenario: Scenario) -> list[str]:
    turns = scenario.turns
    return [
        f"{scenario.id}, turn {n}: `repeat_of_cut` is held only right after a stop. FIX: move it."
        for n, turn in enumerate(turns, 1)
        if turn.repeat_of_cut and (n == 1 or not turns[n - 2].stop)
    ]

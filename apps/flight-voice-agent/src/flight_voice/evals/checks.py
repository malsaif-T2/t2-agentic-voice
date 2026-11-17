"""The checks of one play of a scripted flight call (evals/scenarios.py), each in code against
the exact mock airline, read from what the play did (call.py's `PlayRead`); no judge. Each
failed check is named (`Failed`: the check and the turn, from 1), never with a text.

**Each turn's checks**, each only when its turn expects it: `calls`, the tools its reply called
in order; `args`, each value one of its calls held, read as the airline reads it (a city as its
code, a date form resolved against the scenario's today, a return from the departure that call
or the last one before it held, a pick by its kind); `outcome`, what the call did after it (a
read-back said whole, holding the scenario's `read_back` and the total priced from the airline,
checked as `read_back`; an ask-again; the booking confirmed and ended `done`, `failed` or
`unknown`; or, for `declined` and `none`, no read-back, no ask-again and nothing confirmed);
`said_any` and `said_none`, on what the caller heard of its reply, the runtime's lines among it,
in the scorers' form (`normalize_arabic`, then `normalize_digits`); `own_summary`, a turn that
reads the trip back says no number of its own before it (no summary of the agent's own).

On the talker's own words (no fixed phrase, none of the runtime's lines, which code renders):
`language`, every clause in the turn's language and its script (an Arabic reply as many Arabic
letters as Latin ones or more, an English one none); `register`, an Arabic reply in the register
held (`held_register`; rule F's amendment of 2026-11-17): a Saudi one says no form only MSA says
(`MSA_ONLY`, spoken.py), an MSA one no Saudi form (the library's `register_of`, which reads the
caller's words, or the agent's own, `SAUDI_FORMS`); `max_words`; `max_options`, the distinct
departure times of the airline's flights it says; and the long-call checks, the library's repeat
measures (`find_repeat`, `repeats_cut_reply`), never a copy: `repeat`, no identical or near repeat
of an earlier reply unless the turn `asks_repeat` or the reply is a read-back said again;
`cut_repeat`, the turn right after a stop holds 60% of the cut reply's tokens (its whole text,
heard or not). `card`, a card shown (`shows_card`); `progress`, a fixed phrase heard
(`hears_progress`); `notice`, on every turn, no failure notice heard (the error or cut-off line,
`failure_notices`) and no clause the guard blocked (rule F's amendment of 2026-11-17; the flight
spec's f13); `stage_note`, on every turn (rule F's amendment of 2026-11-17 on stage notes),
nothing heard holds a stage note or markup (spoken.py's `stage_note`, never the guard's rule).

**The play's checks:** `failure`, the play ran to its end; `violations`, none (rules A to C and
the yes rule: zero in every play is the hard constraint); `booked`, one booking when a turn's
outcome is `done` and none otherwise, holding the last read-back's flights, travelers and cabin,
for the demo traveler alone (`others`, no booking for anyone else); `reference`, no booking's
reference said but in a turn that `asks_reference`, which says it.
"""

from __future__ import annotations

import re
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Final

from pydantic import JsonValue, TypeAdapter, ValidationError
from t2_agentic_voice.evals import HeardClause, TextToolCall, find_repeat, repeats_cut_reply
from t2_agentic_voice.languages import normalize_digits

from flight_voice.airline.airports import AIRPORTS, HOME, find_airport
from flight_voice.airline.dates import DateSpec, Resolved, resolve_departure, resolve_return
from flight_voice.airline.profile import TRAVELER
from flight_voice.airline.schedule import flights
from flight_voice.evals.call import PlayRead, TurnRead
from flight_voice.evals.scenarios import Args, ReadBack, Scenario, Turn, held_register
from flight_voice.evals.spoken import failure_notices, form, register_held, stage_note

_DATES: Final[TypeAdapter[DateSpec]] = TypeAdapter(DateSpec)
_ARABIC: Final = re.compile(r"[؀-ۿ]")
_LATIN: Final = re.compile(r"[A-Za-z]")
_TIME: Final = re.compile(r"(?<![0-9])([0-9]{1,2})[:.]([0-9]{2})(?![0-9])")
_DIGIT: Final = re.compile(r"[0-9]")
# Every departure time of the airline's flights, as (hour, minute).
DEPARTURES: Final = frozenset(
    (f.departs.hour, f.departs.minute)
    for code in AIRPORTS
    for f in (*flights(HOME, code), *flights(code, HOME))
)
_PICKS: Final = ("pick", "n", "part", "departs")


@dataclass(frozen=True)
class Failed:
    """A check a play failed: its name, and its turn (from 1; None for the play's)."""

    check: str
    turn: int | None = None


def said(clauses: Sequence[HeardClause]) -> str:
    return " ".join(c.text for c in clauses)


def own(clauses: Sequence[HeardClause]) -> tuple[HeardClause, ...]:
    """The talker's own clauses: no fixed phrase, none of the runtime's lines."""
    return tuple(c for c in clauses if not c.phrase and not c.template)


def options_said(text: str) -> int:
    """The distinct departure times of the airline's flights `text` says."""
    found = {(int(h), int(m)) for h, m in _TIME.findall(normalize_digits(text))}
    return len(found & DEPARTURES)


def _day(value: JsonValue, today: date, depart: date | None) -> date | None:
    """A date form a call held, resolved: a return (`depart` given) from that departure."""
    try:
        spec = _DATES.validate_python(value)
    except ValidationError:
        return None
    got = resolve_departure(spec, today) if depart is None else resolve_return(spec, depart, today)
    return got.day if isinstance(got, Resolved) else None


def held(call: TextToolCall, today: date, last_depart: date | None) -> dict[str, object]:
    """The values `call` held, as the airline reads them (the module's docstring)."""
    args, found = call.arguments, dict[str, object]()
    for name in ("destination", "origin"):
        if isinstance(value := args.get(name), str) and (place := find_airport(value)):
            found[name] = place.code
    for name in ("one_way", "travelers", "cabin", "month", "leg"):
        if name in args:
            found[name] = args[name]
    for name in ("depart", "from_date"):
        if name in args:
            found[name] = _day(args[name], today, None)
    depart = found.get("depart")
    since = depart if isinstance(depart, date) else last_depart
    if "return_date" in args and since is not None:
        found["return_date"] = _day(args["return_date"], today, since)
    choice = args.get("choice")
    if isinstance(choice, dict):
        found |= {name: choice[name] for name in _PICKS if name in choice}
    return found


def _expected(args: Args) -> dict[str, object]:
    return {name: value for name, value in args.model_dump().items() if value is not None}


def _outcome(turn: Turn, read: TurnRead) -> str | None:
    """The name of the outcome check `read` fails, or None."""
    expected = turn.outcome
    if expected == "read_back":
        return None if read.read_back else ("read_back" if turn.read_back else "outcome")
    if expected == "asked_again":
        ok = read.asked_again
    elif expected in ("done", "failed", "unknown"):
        ok = read.confirmed and read.ended == expected
    else:  # declined, none
        ok = not (read.read_back or read.asked_again or read.confirmed)
    return None if ok else "outcome"


def _language(scenario: Scenario, turn: Turn, words: Sequence[HeardClause]) -> Iterator[str]:
    language = turn.language or scenario.language
    text = said(words)
    arabic, latin = len(_ARABIC.findall(text)), len(_LATIN.findall(text))
    if language == "en":
        script = arabic == 0 and all(c.language == "en" for c in words)
    else:
        script = arabic >= latin and all(c.language != "en" for c in words)
    if words and not script:
        yield "language"
    wanted = held_register(scenario, turn)
    if wanted is not None and arabic and not register_held(text, wanted):
        yield "register"


def turn_checks(
    scenario: Scenario, n: int, reads: Sequence[TurnRead | None], last_depart: date | None
) -> Iterator[str]:
    """The checks turn `n` of `scenario` fails (the module's docstring), its reply `reads[n]`,
    the turns before it read as `reads[:n]`."""
    turn, read = scenario.turns[n], reads[n]
    if turn.stop:
        return
    if read is None:
        yield "said"
        return
    if turn.calls is not None and tuple(c.tool for c in read.tools) != turn.calls:
        yield "calls"
    values = [held(call, scenario.today, last_depart) for call in read.tools]
    if any(not any(v.get(k) == want for v in values) for k, want in _expected(turn.args).items()):
        yield "args"
    if turn.outcome is not None and (failed := _outcome(turn, read)) is not None:
        yield failed
    heard = form(said(read.heard))
    if not all(any(form(v) in heard for v in group) for group in turn.said_any):
        yield "said_any"
    if any(form(word) in heard for word in turn.said_none):
        yield "said_none"
    words = own(read.heard)
    text = said(words)
    if turn.outcome == "read_back" and _DIGIT.search(normalize_digits(text)):
        yield "own_summary"
    yield from _language(scenario, turn, words)
    if len(text.split()) > turn.max_words:
        yield "max_words"
    if options_said(text) > turn.max_options:
        yield "max_options"
    earlier = [said(own(r.heard)) for r in reads[:n] if r is not None]
    # A read-back said again is exempt as the runtime's lines are left out of `text` (`own`).
    if find_repeat(text, earlier, asks_repeat=turn.asks_repeat) is not None:
        yield "repeat"
    if turn.repeat_of_cut and not _cut_repeated(read, reads[n - 2] if n >= 2 else None):
        yield "cut_repeat"
    if turn.shows_card and not read.cards:
        yield "card"
    if turn.hears_progress and not any(c.phrase for c in read.heard):
        yield "progress"
    if read.blocked or any(c.phrase and form(c.text) in failure_notices() for c in read.heard):
        yield "notice"
    if stage_note(said(read.heard)):
        yield "stage_note"


def _cut_repeated(read: TurnRead, cut: TurnRead | None) -> bool:
    """Whether `read`'s reply says the cut reply `cut` again (its whole text, heard or not)."""
    if cut is None:
        return False
    whole = said([c for c in cut.clauses if not c.phrase])
    return repeats_cut_reply(said([c for c in read.heard if not c.phrase]), whole)


def _last_read_back(scenario: Scenario) -> ReadBack | None:
    found = [t.read_back for t in scenario.turns if t.read_back is not None]
    return found[-1] if found else None


def _booked(scenario: Scenario, read: PlayRead) -> Iterator[str]:
    mine = [b for b in read.made if b.traveler_id == TRAVELER.id]
    if len(mine) != len(read.made):
        yield "others"
    wanted = any(t.outcome == "done" for t in scenario.turns)
    back = _last_read_back(scenario)
    if not wanted or back is None:
        if mine:
            yield "booked"
        return
    legs = [(back.outbound.number, back.outbound.day)]
    if back.return_ is not None:
        legs.append((back.return_.number, back.return_.day))
    made = [((b.travelers, b.cabin), [(leg.flight, leg.day) for leg in b.legs]) for b in mine]
    if made != [((back.travelers, back.cabin), legs)]:
        yield "booked"


def _references(scenario: Scenario, read: PlayRead) -> Iterator[Failed]:
    references = [b.reference for b in read.made]
    for n, turn in enumerate(read.turns):
        if turn is None:
            continue
        heard = form(said(turn.heard)).replace(" ", "")
        says = any(r in heard for r in references)
        if says != (scenario.turns[n].asks_reference and bool(references)):
            yield Failed("reference", n + 1)


def failures(scenario: Scenario, read: PlayRead) -> tuple[Failed, ...]:
    """Every check one play of `scenario` failed, `read` what it did (the module's docstring)."""
    found: list[Failed] = []
    if read.failure is not None:
        found.append(Failed("failure"))
    if read.violations:
        found.append(Failed("violations"))
    found += [Failed(name) for name in _booked(scenario, read)]
    found += _references(scenario, read)
    last_depart: date | None = None
    for n in range(len(scenario.turns)):
        found += [Failed(name, n + 1) for name in turn_checks(scenario, n, read.turns, last_depart)]
        said_turn = read.turns[n]
        for call in () if said_turn is None else said_turn.tools:
            depart = held(call, scenario.today, last_depart).get("depart")
            last_depart = depart if isinstance(depart, date) else last_depart
    return tuple(found)

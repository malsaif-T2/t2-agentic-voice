"""The flight agent's scripted calls: one TOML file each under
apps/flight-voice-agent/evals/calls/, named by its id, each played as one call in text against a
new mock airline, every fact checked in code (the mock airline is exact, so no judge reads them).

**A scenario** has its `id`, its `split` (`dev` or `held-out`, fixed before any run), the
`language` its caller speaks (`ar-SA` Saudi, `ar` MSA, `en`; an MSA caller is held in the
agent's Arabic call and answered in MSA), its `kind` (what it tests; every kind has a dev and a
held-out scenario), `notes`, the capabilities it `needs` (from `NEEDS`, a closed list: a
scenario whose need does not play in text yet is skipped and reported), the airline's `modes`
(its searches, its profile, its bookings and their lookup) and `today` (Monday 2026-11-16 unless
given), and its `turns`.

**A turn** is the caller's words (`says`), said `when` (unset, while the agent is silent; or
over its reply playing, while a tool of the reply runs, over a read-back's summary or over its
closing question), `after_s` seconds into that moment; or the client's Stop (`stop = true`) at
a point of the reply (`at`, the same points), `after_s` into it, expecting nothing of its own.
What a turn's reply is expected to do, each unchecked when left out:

- `calls`, the tools it called, in order (`[]` for none); `args`, values those calls held, read
  as the airline reads them (a city as its code, a date form as its day, a pick by its kind);
  `forms`, the date form the caller's words name for each date of `args`, which the airline's
  own date code resolves against `today` to that date (a return from the departure), so no date
  is worked out by hand;
- `outcome`: a read-back played, asked again, the `done`, `failed`, `unknown` or `declined`
  line, or `none` of these; `read_back`, the trip it reads back (`outbound = "T2 401@2026-11-19"`,
  `return`, `one_way`, `travelers`, `cabin`), never its total, which the check prices from the
  airline so a fare change breaks no scenario;
- `said_any`, groups of words of which the reply says one of each (variants in both scripts);
  `said_none`, words it never says; `language` (the scenario's unless given) and, for Arabic,
  `register` (`saudi` for `ar-SA`, `msa` for `ar`, unless given); `max_words` (45) and
  `max_options` (3, the listed departures it says);
- `asks_repeat` (the caller asks to hear something again: no repeat is held against it),
  `repeat_of_cut` (the turn right after a stop: its reply is held to the cut reply's words),
  `asks_reference` (the caller asks for a booking's reference, the one turn whose reply may say
  it), `shows_card` (the reply's card reaches the page, not dropped by the output guard) and
  `hears_progress` (a tool's progress line plays before the answer).

`load` reads the set; evals/rules.py's `problems` lists every rule a set breaks.
"""

from __future__ import annotations

import re
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Annotated, Final, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from flight_voice.airline.airports import Code
from flight_voice.airline.bookings import Mode
from flight_voice.airline.dates import DateSpec
from flight_voice.airline.schedule import Cabin
from flight_voice.airline.system import AIRLINE_CODE, ProfileMode, SearchMode
from flight_voice.said import Tag
from flight_voice.said.words import PartOfDay
from flight_voice.trip import LegKind

CALLS: Final = Path(__file__).resolve().parents[3] / "evals" / "calls"
# The day scripted calls are held on: Monday 2026-11-16.
TODAY: Final = date(2026, 11, 16)
MAX_WORDS: Final = 45
MAX_OPTIONS: Final = 3
# The tools a reply may call: the agent's, and the library's own language switch.
ToolName = Literal[
    "search_flights",
    "choose_flight",
    "change_trip",
    "get_trip",
    "fare_calendar",
    "compare_cabins",
    "traveler_profile",
    "book_trip",
    "switch_language",
]
Split = Literal["dev", "held-out"]
When = Literal["agent_speaking", "tool_running", "read_back", "closing_question"]
Outcome = Literal["read_back", "asked_again", "done", "failed", "unknown", "declined", "none"]
ArabicRegister = Literal["saudi", "msa"]
Pick = Literal["number", "cheapest", "earliest", "latest", "part_of_day", "time"]
_FLIGHT = re.compile(r"^(?P<code>[A-Z0-9]{2}) (?P<number>[0-9]{3})@(?P<day>[0-9-]{10})$")


@dataclass(frozen=True)
class Capability:
    """A capability a scenario may need, `doc` saying what it is, and whether a call held in
    text plays it today (`plays`); a scenario needing one that does not is skipped and
    reported."""

    name: str
    doc: str
    plays: bool


NEEDS: Final[Mapping[str, Capability]] = {
    "language_switch": Capability(
        "language_switch",
        "The caller moves the call to the agent's other language mid-call, by asking in any "
        "words or by speaking it (D-103). It plays under `stt.live_language = detected` "
        "(run_setup.py's `play_settings`), a typed turn heard in the call's language as it "
        "stands, as a real call's speech-to-text is told a move (`TextCall`). In text the call "
        "moves on a switch request or the talker's tool alone: no second speech-to-text "
        "request hears the other language.",
        plays=True,
    ),
}


class _Model(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Modes(_Model):
    """How the mock airline answers: its searches, its profile, its bookings and their lookup."""

    search: SearchMode = "answer"
    profile: ProfileMode = "answer"
    booking: Mode = "answer"
    lookup: bool = True


class Args(_Model):
    """Values a turn's tool calls held, as the airline reads them."""

    destination: Code | None = None
    origin: Code | None = None
    depart: date | None = None
    return_date: date | None = None
    from_date: date | None = None
    one_way: bool | None = None
    travelers: int | None = Field(default=None, ge=1, le=9)
    cabin: Cabin | None = None
    month: int | None = Field(default=None, ge=1, le=12)
    leg: LegKind | None = None
    pick: Pick | None = None
    n: int | None = Field(default=None, ge=1, le=4)
    part: PartOfDay | None = None
    departs: str | None = Field(default=None, pattern=r"^([01][0-9]|2[0-3]):[0-5][0-9]$")


class Forms(_Model):
    """The date form the caller's words name for each date of a turn's `args`."""

    depart: DateSpec | None = None
    return_date: DateSpec | None = None
    from_date: DateSpec | None = None


class FlightOn(_Model):
    """A flight on its day, written as the airline's code, its number and the day:
    "T2 401@2026-11-19"."""

    number: int
    day: date

    @model_validator(mode="before")
    @classmethod
    def _written(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        found = _FLIGHT.match(value)
        if found is None or found["code"] != AIRLINE_CODE:
            raise ValueError(f'a flight is written as "{AIRLINE_CODE} 401@2026-11-19"')
        return {"number": int(found["number"]), "day": found["day"]}


class ReadBack(_Model):
    """The trip a read-back reads back, with no total: the check prices it from the airline."""

    outbound: FlightOn
    return_: FlightOn | None = Field(default=None, alias="return")
    one_way: bool
    travelers: int = Field(ge=1, le=9)
    cabin: Cabin

    @model_validator(mode="after")
    def _kind(self) -> Self:
        if self.one_way == (self.return_ is not None):
            raise ValueError("a one-way read-back has no return, and a round trip's has one")
        return self


Words = Annotated[str, Field(min_length=1, max_length=80)]
_STOP_FIELDS: Final = frozenset({"stop", "at", "after_s"})


class Turn(_Model):
    """One turn of a scripted call (the module's docstring)."""

    says: str | None = Field(default=None, min_length=1, max_length=400)
    when: When | None = None
    after_s: float = Field(default=0.0, ge=0.0, le=30.0)
    stop: bool = False
    at: When | None = None
    calls: tuple[ToolName, ...] | None = None
    args: Args = Args()
    forms: Forms = Forms()
    outcome: Outcome | None = None
    read_back: ReadBack | None = None
    said_any: tuple[Annotated[tuple[Words, ...], Field(min_length=1)], ...] = ()
    said_none: tuple[Words, ...] = ()
    language: Tag | None = None
    register_: ArabicRegister | None = Field(default=None, alias="register")
    max_words: int = Field(default=MAX_WORDS, ge=1, le=200)
    max_options: int = Field(default=MAX_OPTIONS, ge=0, le=4)
    asks_repeat: bool = False
    repeat_of_cut: bool = False
    asks_reference: bool = False
    shows_card: bool = False
    hears_progress: bool = False

    @model_validator(mode="after")
    def _shape(self) -> Self:
        if self.stop:
            if self.at is None or self.model_fields_set - _STOP_FIELDS:
                raise ValueError("a stop has `at` and `after_s` alone: it expects nothing")
        elif self.says is None or self.at is not None:
            raise ValueError("a turn says words (`says`), or is a stop (`stop = true`, `at`)")
        if self.read_back is not None and self.outcome != "read_back":
            raise ValueError('a turn with a `read_back` has the outcome "read_back"')
        return self


class Scenario(_Model):
    """One scripted call (the module's docstring)."""

    id: str = Field(pattern=r"^[a-z]+[0-9]{2}_[a-z0-9_]{3,60}$")
    split: Split
    language: Tag
    kind: str = Field(pattern=r"^[a-z][a-z_]{2,40}$")
    notes: str = Field(min_length=1, max_length=600)
    needs: tuple[str, ...] = ()
    modes: Modes = Modes()
    today: date = TODAY
    turns: tuple[Turn, ...] = Field(min_length=1, max_length=12)

    @model_validator(mode="after")
    def _turns(self) -> Self:
        if self.turns[0].stop:
            raise ValueError("a call starts with the caller's words, not a stop")
        for turn in self.turns:
            if turn.register_ is not None and (turn.language or self.language) == "en":
                raise ValueError("a `register` is held only on an Arabic reply")
        return self


def held_register(scenario: Scenario, turn: Turn) -> ArabicRegister | None:
    """The register `turn`'s reply is held to: its own, else its language's (none in English)."""
    language = turn.language or scenario.language
    if turn.register_ is not None or language == "en":
        return turn.register_
    return "saudi" if language == "ar-SA" else "msa"


def waiting(scenario: Scenario) -> tuple[str, ...]:
    """The needs of `scenario` that a call in text does not play yet: none when it plays."""
    return tuple(n for n in scenario.needs if n not in NEEDS or not NEEDS[n].plays)


class ScenarioError(ValueError):
    """A scenario file that cannot be read, or holds another id than its name."""


def load(folder: Path = CALLS) -> tuple[Scenario, ...]:
    """Every scenario under `folder`, one TOML file each named by its id, in name order."""
    if not folder.is_dir():
        raise ScenarioError(f"{folder.name}: no such folder of scripted calls")
    found: list[Scenario] = []
    for path in sorted(folder.glob("*.toml")):
        try:
            each = Scenario.model_validate(tomllib.loads(path.read_text(encoding="utf-8")))
        except (tomllib.TOMLDecodeError, ValidationError) as error:
            raise ScenarioError(f"{path.name}: {error}") from error
        if each.id != path.stem:
            raise ScenarioError(f"{path.name}: holds the scenario '{each.id}', not its name")
        found.append(each)
    return tuple(found)

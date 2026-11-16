"""The flight agent's scripted calls (flight_voice/evals/scenarios.py) as committed: every file
reads, the whole set, dev and held-out, breaks no rule (a dev and a held-out scenario never share
a leg, and every kind has both), the held-out set covers every kind in both languages, every
expected date is the one the airline's date code gives the caller's words (and no Arabic day said
by its number is also a weekday's name), every flight a
read-back holds flies on its day, and every need is on the closed list; and the model refuses each
malformed shape at the boundary, naming it."""

from __future__ import annotations

from pathlib import Path
from typing import Any, get_args

import pytest
from flight_voice.agent import declare
from flight_voice.airline.dates import Resolved, resolve_departure, resolve_return
from flight_voice.airline.fares import seats_left
from flight_voice.airline.schedule import departures, find_flight, window
from flight_voice.airline.system import Airline
from flight_voice.evals.rules import legs, problems
from flight_voice.evals.scenarios import (
    CALLS,
    NEEDS,
    TODAY,
    Scenario,
    ScenarioError,
    ToolName,
    Turn,
    held_register,
    load,
    waiting,
)
from flight_voice.trip import TripBook
from pydantic import ValidationError
from t2_agentic_voice.actions.language_tool import NAME as SWITCH_LANGUAGE

from tests.flight_voice import scenario_dates

SCENARIOS = load()
DEV_IDS = [f"f{n:02d}" for n in range(1, 29)]
HELD_OUT_IDS = [f"h{n:02d}" for n in range(1, 16)]


def _scenario(**fields: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": "x01_crafted",
        "split": "dev",
        "language": "en",
        "kind": "round_trip",
        "notes": "A crafted call.",
        "turns": [{"says": "Hello."}],
    }
    return base | fields


def test_every_file_reads_and_the_dev_set_is_f01_to_f28() -> None:
    assert [s.id.split("_")[0] for s in SCENARIOS if s.split == "dev"] == DEV_IDS
    assert sorted(p.stem for p in CALLS.glob("*.toml")) == [s.id for s in SCENARIOS]
    assert all(s.today == TODAY == scenario_dates.TODAY for s in SCENARIOS)
    assert TODAY.weekday() == 0  # a Monday


def test_the_whole_set_dev_and_held_out_breaks_no_rule() -> None:
    assert problems(SCENARIOS) == []


def test_the_held_out_set_covers_every_kind_in_both_languages() -> None:
    held_out = [s for s in SCENARIOS if s.split == "held-out"]
    assert [s.id.split("_")[0] for s in held_out] == HELD_OUT_IDS
    assert {s.kind for s in held_out} == {s.kind for s in SCENARIOS if s.split == "dev"}
    assert {s.language for s in held_out} == {"ar-SA", "ar", "en"}
    dev_legs = set().union(*(legs(s) for s in SCENARIOS if s.split == "dev"))
    assert all(legs(s).isdisjoint(dev_legs) for s in held_out)


def test_every_expected_date_is_the_airlines_resolution_of_the_callers_words() -> None:
    checked = 0
    for scenario in SCENARIOS:
        depart = None
        for turn in scenario.turns:
            args, forms = turn.args, turn.forms
            depart = args.depart or depart
            assert (args.depart is None) == (forms.depart is None), scenario.id
            assert (args.return_date is None) == (forms.return_date is None), scenario.id
            if forms.depart is not None:
                got = resolve_departure(forms.depart, scenario.today)
                assert isinstance(got, Resolved) and got.day == args.depart, scenario.id
                checked += 1
            if forms.return_date is not None:
                assert depart is not None, scenario.id
                back = resolve_return(forms.return_date, depart, scenario.today)
                assert isinstance(back, Resolved) and back.day == args.return_date, scenario.id
                checked += 1
    assert checked >= 30


def test_an_arabic_day_said_by_its_number_is_never_also_a_weekdays_name() -> None:
    # «يوم اثنين ديسمبر» is both "the second of December" and "a Monday in December": a
    # verdict on such a line would rest on the script's wording, not on the agent.
    bare = {"اثنين", "ثلاثاء", "أربعاء", "خميس", "جمعة", "سبت", "أحد"}
    clashes = [
        scenario.id
        for scenario in SCENARIOS
        for turn in scenario.turns
        if scenario.language != "en"
        and "on" in {f.kind for f in (turn.forms.depart, turn.forms.return_date) if f}
        and bare & set((turn.says or "").split())
    ]
    assert clashes == []


def test_every_flight_a_read_back_holds_flies_on_its_day_with_seats() -> None:
    legs = 0
    for scenario in SCENARIOS:
        first, last = window(scenario.today)
        for turn in scenario.turns:
            if (read_back := turn.read_back) is None:
                continue
            back = read_back.return_
            for leg in (read_back.outbound,) if back is None else (read_back.outbound, back):
                flight = find_flight(leg.number)
                assert flight is not None and first <= leg.day <= last, scenario.id
                flown = departures(flight.origin, flight.destination, leg.day)
                assert leg.number in {d.flight.number for d in flown}, scenario.id
                assert read_back.cabin in flight.cabins, scenario.id
                assert seats_left(flight, leg.day, read_back.cabin) >= read_back.travelers
                legs += 1
    assert legs >= 25


def test_needs_come_only_from_the_closed_list_and_the_switch_waits() -> None:
    assert list(NEEDS) == ["language_switch"]
    assert all(c.name == name and len(c.doc) > 40 for name, c in NEEDS.items())
    assert {n for s in SCENARIOS for n in s.needs} <= set(NEEDS)
    assert [s.id for s in SCENARIOS if waiting(s)] == [
        "f09_switch_ar_to_en",
        "f10_switch_en_to_ar",
        "h06_switch_at_read_back_saudi",
    ]
    assert waiting(Scenario.model_validate(_scenario(needs=["telepathy"]))) == ("telepathy",)


def test_the_tools_a_turn_may_name_are_the_agents_the_booking_and_the_switch() -> None:
    agent = declare(Airline(today=lambda: TODAY), TripBook())
    assert get_args(ToolName) == (*(t.name for t in agent.tools), SWITCH_LANGUAGE)


def test_a_replys_register_follows_its_language_unless_given() -> None:
    saudi = Scenario.model_validate(_scenario(language="ar-SA"))
    msa = Scenario.model_validate(_scenario(language="ar"))
    english = Scenario.model_validate(_scenario())
    given = Turn.model_validate({"says": "x", "register": "msa"})
    assert held_register(saudi, saudi.turns[0]) == "saudi"
    assert held_register(msa, msa.turns[0]) == "msa"
    assert held_register(english, english.turns[0]) is None
    assert held_register(saudi, given) == "msa"
    assert held_register(english, Turn(says="x", language="ar-SA")) == "saudi"


@pytest.mark.parametrize(
    ("fields", "names"),
    [
        (
            {
                "turns": [
                    {
                        "says": "x",
                        "outcome": "read_back",
                        "read_back": {
                            "outbound": "T2 201@2026-11-17",
                            "one_way": True,
                            "travelers": 1,
                            "cabin": "economy",
                            "total": 540,
                        },
                    }
                ]
            },
            "total",
        ),
        (
            {
                "turns": [
                    {
                        "says": "x",
                        "outcome": "read_back",
                        "read_back": {
                            "outbound": "T2 201@2026-11-17",
                            "return": "T2 202@2026-11-20",
                            "one_way": True,
                            "travelers": 1,
                            "cabin": "economy",
                        },
                    }
                ]
            },
            "one-way",
        ),
        (
            {
                "turns": [
                    {
                        "says": "x",
                        "outcome": "read_back",
                        "read_back": {
                            "outbound": "XX 201@2026-11-17",
                            "one_way": True,
                            "travelers": 1,
                            "cabin": "economy",
                        },
                    }
                ]
            },
            "T2 401@2026-11-19",
        ),
        (
            {
                "turns": [
                    {
                        "says": "x",
                        "read_back": {
                            "outbound": "T2 201@2026-11-17",
                            "one_way": True,
                            "travelers": 1,
                            "cabin": "economy",
                        },
                    }
                ]
            },
            "outcome",
        ),
        ({"turns": [{"says": "x"}, {"stop": True, "says": "y", "at": "agent_speaking"}]}, "stop"),
        ({"turns": [{"says": "x"}, {"stop": True, "at": "agent_speaking", "calls": []}]}, "stop"),
        ({"turns": [{"says": "x"}, {"stop": True}]}, "stop"),
        ({"turns": [{"stop": True, "at": "agent_speaking"}]}, "starts"),
        ({"turns": [{"when": "read_back"}]}, "says"),
        ({"turns": [{"says": "x", "at": "tool_running"}]}, "says"),
        ({"turns": [{"says": "x", "register": "saudi"}]}, "register"),
        ({"turns": [{"says": "x", "calls": ["book_hotel"]}]}, "calls"),
        ({"turns": [{"says": "x", "args": {"destination": "MAN"}}]}, "destination"),
        ({"turns": [{"says": "x", "forms": {"depart": {"kind": "soon"}}}]}, "depart"),
        ({"split": "test"}, "split"),
        ({"surprise": 1}, "surprise"),
        ({"id": "Flight 1"}, "id"),
    ],
)
def test_a_malformed_scenario_is_refused_at_the_boundary(
    fields: dict[str, Any], names: str
) -> None:
    with pytest.raises(ValidationError, match=names):
        Scenario.model_validate(_scenario(**fields))


def test_the_loader_refuses_a_file_naming_another_id_or_not_toml(tmp_path: Path) -> None:
    good = (CALLS / "f07_cheapest_days_english.toml").read_bytes()
    (tmp_path / "f99_renamed.toml").write_bytes(good)
    with pytest.raises(ScenarioError, match=r"f99_renamed\.toml: holds the scenario 'f07_"):
        load(tmp_path)
    (tmp_path / "f99_renamed.toml").write_bytes(b"id = ")
    with pytest.raises(ScenarioError, match=r"f99_renamed\.toml"):
        load(tmp_path)
    with pytest.raises(ScenarioError, match="no such folder"):
        load(tmp_path / "missing")

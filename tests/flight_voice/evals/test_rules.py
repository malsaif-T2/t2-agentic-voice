"""The rules a set of scripted calls keeps (flight_voice/evals/rules.py): a crafted set that keeps
them all has no problem, and a crafted set breaking each one has that problem alone, named with
its scenario, its turn and its fix. The flights and days come from the airline's own data (the
scenario dates' finder for a sold-out business cabin and Singapore's Tuesday)."""

from __future__ import annotations

from typing import Any

import pytest
from flight_voice.evals.rules import legs, problems
from flight_voice.evals.scenarios import Scenario

from tests.flight_voice.scenario_dates import business_sold_out, no_flight_day

LONDON: dict[str, Any] = {
    "says": "London next Thursday, back on Sunday.",
    "args": {"destination": "LHR", "depart": "2026-11-19", "return_date": "2026-11-22"},
    "forms": {
        "depart": {"kind": "weekday", "weekday": "thu"},
        "return_date": {"kind": "weekday", "weekday": "sun"},
    },
}
BOOKED: dict[str, Any] = {
    "says": "The morning one, and the last one back.",
    "outcome": "read_back",
    "read_back": {
        "outbound": "T2 401@2026-11-19",
        "return": "T2 404@2026-11-22",
        "one_way": False,
        "travelers": 1,
        "cabin": "economy",
    },
}
DUBAI: dict[str, Any] = {
    "says": "Dubai tomorrow, one way.",
    "args": {"destination": "DXB", "depart": "2026-11-17", "one_way": True},
    "forms": {"depart": {"kind": "relative", "when": "tomorrow"}},
}


def _call(name: str, split: str = "dev", kind: str = "round_trip", **fields: Any) -> Scenario:
    return Scenario.model_validate(
        {
            "id": name,
            "split": split,
            "language": "en",
            "kind": kind,
            "notes": "A crafted call.",
            "turns": [LONDON, BOOKED],
        }
        | fields
    )


def _pair(**held_out: Any) -> list[Scenario]:
    return [_call("x01_dev"), _call("x02_held", "held-out", **held_out)]


def _read_back(outbound: str, *, cabin: str = "economy", travelers: int = 1) -> dict[str, Any]:
    return {
        "says": "That one.",
        "outcome": "read_back",
        "read_back": {
            "outbound": outbound,
            "one_way": True,
            "travelers": travelers,
            "cabin": cabin,
        },
    }


def test_a_set_that_keeps_every_rule_has_no_problem() -> None:
    assert problems(_pair(turns=[DUBAI])) == []


def test_the_legs_a_scenario_holds_are_its_searches_and_its_read_backs() -> None:
    found = legs(_call("x01_dev"))
    assert {(a, b, day.isoformat()) for a, b, day in found} == {
        ("RUH", "LHR", "2026-11-19"),
        ("LHR", "RUH", "2026-11-22"),
    }


def test_an_id_held_twice() -> None:
    twice = [_call("x01_dev"), _call("x01_dev", "held-out", turns=[DUBAI])]
    assert problems(twice) == [
        "x01_dev: 2 scenarios hold this id. FIX: give each its own id and file name."
    ]


@pytest.mark.parametrize("split", ["dev", "held-out"])
def test_a_kind_with_no_scenario_in_a_split(split: str) -> None:
    other = "held-out" if split == "dev" else "dev"
    lonely = _call("x03_lonely", split, kind="profile", turns=[{"says": "My trips?"}])
    found = problems([*_pair(turns=[DUBAI]), lonely])
    assert found == [
        f"the kind 'profile' has no {other} scenario. FIX: write one, on other routes and words."
    ]


def test_a_dev_and_a_held_out_scenario_sharing_a_leg() -> None:
    found = problems(_pair())
    assert found == [
        "x01_dev and x02_held: a dev and a held-out scenario share the leg LHR to RUH on "
        "2026-11-22. FIX: move the held-out one to another route or day.",
        "x01_dev and x02_held: a dev and a held-out scenario share the leg RUH to LHR on "
        "2026-11-19. FIX: move the held-out one to another route or day.",
    ]


def test_a_leg_only_a_read_back_holds_is_shared_too() -> None:
    dev = _call("x01_dev", turns=[DUBAI])
    held = _call(
        "x02_held", "held-out", turns=[{"says": "Dubai."}, _read_back("T2 201@2026-11-17")]
    )
    assert {(a, b, d.isoformat()) for a, b, d in legs(held)} == {("RUH", "DXB", "2026-11-17")}
    assert len([p for p in problems([dev, held]) if "share the leg RUH to DXB" in p]) == 1


def test_a_need_off_the_closed_list() -> None:
    found = problems(_pair(turns=[DUBAI], needs=["telepathy"]))
    assert len(found) == 1 and found[0].startswith("x02_held: needs 'telepathy'")


@pytest.mark.parametrize(
    ("turn", "says"),
    [
        ({**DUBAI, "forms": {}}, "turn 1, depart: a date and its form go together"),
        ({**DUBAI, "args": {"destination": "DXB"}}, "turn 1, depart: a date and its form"),
        (
            {**DUBAI, "args": {"destination": "DXB", "depart": "2026-11-18"}},
            "turn 1, depart: its form resolves to 2026-11-17 against 2026-11-16, not 2026-11-18",
        ),
        (
            {**DUBAI, "forms": {"depart": {"kind": "on", "day": 31, "month": 11}}},
            "turn 1, depart: its form resolves to no date",
        ),
        (
            {
                "says": "Back a week later.",
                "args": {"return_date": "2026-11-24"},
                "forms": {"return_date": {"kind": "nights", "nights": 7}},
            },
            "turn 1, return_date: its form resolves to no date",
        ),
        (
            {**DUBAI, "args": {"from_date": "2026-11-17"}, "forms": {}},
            "turn 1, from_date: a date and its form go together",
        ),
    ],
)
def test_an_expected_date_the_airline_does_not_resolve_to(turn: dict[str, Any], says: str) -> None:
    found = problems(_pair(turns=[turn]))
    assert len(found) == 1 and found[0].startswith(f"x02_held, {says}"), found


def test_a_return_counts_from_the_departure_an_earlier_turn_held() -> None:
    back = {
        "says": "Back three nights later.",
        "args": {"return_date": "2026-11-20"},
        "forms": {"return_date": {"kind": "nights", "nights": 3}},
    }
    assert problems(_pair(turns=[DUBAI, back])) == []


def test_read_back_flights_the_airline_does_not_sell() -> None:
    sold_out, day = business_sold_out("RUH", "CAI") or (0, None)
    assert day is not None
    tuesday = no_flight_day("RUH", "SIN")
    assert tuesday is not None
    cases = {
        "T2 999@2026-11-17": "is not one the airline sells",
        "T2 201@2027-06-01": "is not one the airline sells",
        f"T2 601@{tuesday.isoformat()}": "does not fly that day in economy",
    }
    for outbound, says in cases.items():
        found = [p for p in problems(_pair(turns=[_read_back(outbound)])) if says in p]
        assert len(found) == 1, outbound
    first = problems(_pair(turns=[DUBAI, _read_back("T2 201@2026-11-17", cabin="first")]))
    assert first == [
        "x02_held, turn 2: flight 201 on 2026-11-17 does not fly that day in first. FIX: pick one."
    ]
    cairo = {
        "says": "Cairo, the day after tomorrow, business.",
        "args": {"destination": "CAI", "depart": day.isoformat()},
        "forms": {"depart": {"kind": "relative", "when": "day_after_tomorrow"}},
    }
    full = _read_back(f"T2 {sold_out}@{day.isoformat()}", cabin="business")
    assert problems(_pair(turns=[cairo, full])) == [
        f"x02_held, turn 2: flight {sold_out} on {day.isoformat()} has too few seats. "
        "FIX: pick a day it has them."
    ]


def test_a_read_back_on_a_day_no_search_held() -> None:
    found = problems(_pair(turns=[DUBAI, _read_back("T2 201@2026-11-18")]))
    assert found == [
        "x02_held, turn 2: flight 201 on 2026-11-18: no search held that day. "
        "FIX: read back a searched day."
    ]


def test_a_return_that_does_not_fly_the_outbound_route_back() -> None:
    wrong = {**BOOKED, "read_back": {**BOOKED["read_back"], "return": "T2 202@2026-11-22"}}
    dev = _call("x01_dev", turns=[DUBAI])
    assert problems([dev, _call("x02_held", "held-out", turns=[LONDON, wrong])]) == [
        "x02_held, turn 2: the return does not fly the outbound's route back. FIX: one."
    ]


@pytest.mark.parametrize(
    "turns",
    [
        [{"says": "Hi.", "repeat_of_cut": True}],
        [DUBAI, {"says": "Again?", "repeat_of_cut": True}],
    ],
)
def test_a_repeat_of_a_cut_not_right_after_a_stop(turns: list[dict[str, Any]]) -> None:
    found = problems(_pair(turns=turns))
    assert len(found) == 1 and "`repeat_of_cut` is held only right after a stop" in found[0]


def test_a_repeat_of_a_cut_right_after_a_stop_keeps_the_rule() -> None:
    stop = {"stop": True, "at": "agent_speaking", "after_s": 1.0}
    again = {"says": "One more time?", "asks_repeat": True, "repeat_of_cut": True}
    assert problems(_pair(turns=[DUBAI, stop, again])) == []

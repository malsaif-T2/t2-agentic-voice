"""Every tool and the action of the flight agent as the talker is shown it (the library's
actions/tool_schema.py; plan 010, run F's first smoke play): no reference, `$defs`, `oneOf` or
`discriminator`, and each constant (a date form's or a pick's `kind`) required with no default.
Shown with a `$ref`, gpt-oss on Groq wrote a date form as text and Groq refused the call
(`tool_use_failed`) on 37 of 56 first turns of run F."""

from __future__ import annotations

import json
from typing import Any

from flight_voice.agent import declare
from flight_voice.airline.system import Airline
from flight_voice.trip import TripBook
from t2_agentic_voice import Action, Tool

from tests.flight_voice.scenario_dates import TODAY


def _objects(node: Any) -> list[dict[str, Any]]:
    """Every object schema in `node`, nested ones among them."""
    if isinstance(node, list):
        return [o for item in node for o in _objects(item)]
    if not isinstance(node, dict):
        return []
    found = [node] if node.get("type") == "object" else []
    return found + [o for value in node.values() for o in _objects(value)]


def _shown() -> dict[str, Any]:
    agent = declare(Airline(today=lambda: TODAY), TripBook())
    tools = [t for t in agent.tools if isinstance(t, Tool | Action)]
    assert len(tools) == len(agent.tools)
    return {t.name: dict(t.tool_schema().parameters) for t in tools}


def test_no_tool_is_shown_with_a_reference_or_a_one_of() -> None:
    shown = _shown()
    assert {"search_flights", "choose_flight", "fare_calendar", "book_trip"} <= set(shown)
    for name, schema in shown.items():
        text = json.dumps(schema)
        for word in ('"$ref"', '"$defs"', '"oneOf"', '"discriminator"'):
            assert word not in text, (name, word)


def test_each_constant_of_a_union_is_required_with_no_default() -> None:
    constants = 0
    for name, schema in _shown().items():
        for each in _objects(schema):
            for field, prop in each.get("properties", {}).items():
                if isinstance(prop, dict) and "const" in prop:
                    constants += 1
                    assert field in each.get("required", []) and "default" not in prop, name
    assert constants >= 12  # the date forms (search, calendar) and the picks

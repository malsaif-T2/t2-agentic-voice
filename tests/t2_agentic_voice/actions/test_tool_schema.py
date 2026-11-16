"""The schema a tool's parameters are shown to the talker as (actions/tool_schema.py; plan 010):
no titles, no references (each inlined, a recursive one kept with what it needs), a union as
`anyOf` with no `discriminator`, each constant required with no default; a schema with none of
these is only untitled. Every model is made up for the test."""

from __future__ import annotations

import json
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from t2_agentic_voice.actions.tool_schema import model_schema
from t2_agentic_voice.actions.tools import Tool


class _Spec(BaseModel):
    model_config = ConfigDict(extra="forbid")


class OnDay(_Spec):
    """A day of the month."""

    kind: Literal["on"] = "on"
    day: int = Field(ge=1, le=31)
    month: int | None = None


class InDays(_Spec):
    """A number of days from today."""

    kind: Literal["in_days"] = "in_days"
    days: int = Field(ge=1)


When = Annotated[OnDay | InDays, Field(discriminator="kind")]


class Search(BaseModel):
    city: str = Field(description="The city as said.")
    depart: When = Field(description="The day they leave.")
    back: When | None = None


class Node(BaseModel):
    name: str
    children: list[Node] = []


class Plain(BaseModel):
    title: str = Field(description="A property named title.")
    discriminator: str = "kept"
    count: int | None = None


def _text(schema: Any) -> str:
    return json.dumps(schema)


def test_a_union_is_inlined_as_any_of_its_tag_required() -> None:
    shown = model_schema(Search.model_json_schema())
    text = _text(shown)
    assert "$ref" not in text and "$defs" not in text and "oneOf" not in text
    assert '"discriminator"' not in text and '"title": "' not in text
    on, in_days = shown["properties"]["depart"]["anyOf"]
    assert on["description"] == "A day of the month."
    assert on["properties"]["kind"] == {"const": "on", "type": "string"}
    assert on["required"] == ["kind", "day"]
    assert in_days["required"] == ["kind", "days"]
    assert shown["properties"]["depart"]["description"] == "The day they leave."
    union, null = shown["properties"]["back"]["anyOf"]  # pydantic's nesting, as measured
    assert [b["type"] for b in union["anyOf"]] == ["object", "object"] and null == {"type": "null"}
    assert shown["required"] == ["city", "depart"]


def test_every_argument_still_validates_by_the_model_itself() -> None:
    """The schema only tells the talker; the arguments are read by the model, unchanged."""
    made = Search.model_validate({"city": "London", "depart": {"kind": "on", "day": 19}})
    assert made.depart == OnDay(day=19)
    assert Search.model_validate(
        {"city": "Paris", "depart": {"kind": "in_days", "days": 3}, "back": None}
    ).depart == InDays(days=3)


def test_a_recursive_model_keeps_its_reference_and_the_definition_it_needs() -> None:
    shown = model_schema(Node.model_json_schema())
    assert shown["properties"]["children"]["items"] == {"$ref": "#/$defs/Node"}
    assert set(shown["$defs"]) == {"Node"}
    assert shown["$defs"]["Node"]["properties"]["children"]["items"] == {"$ref": "#/$defs/Node"}
    assert '"title": "' not in _text(shown)


def test_a_schema_with_no_reference_union_or_constant_is_only_untitled() -> None:
    schema = Plain.model_json_schema()
    shown = model_schema(schema)
    untitled = {k: v for k, v in schema.items() if k != "title"}
    untitled["properties"] = {
        name: {k: v for k, v in prop.items() if k != "title"}
        for name, prop in schema["properties"].items()
    }
    assert shown == untitled
    assert set(shown["properties"]) == {"title", "discriminator", "count"}  # names kept


def test_a_tool_and_its_nested_model_are_shown_inlined() -> None:
    def find(search: Search) -> str:
        return search.city

    shown: Any = Tool.from_function(find, description="Find.").tool_schema().parameters
    assert "$defs" not in shown and "$ref" not in _text(shown)
    assert shown["properties"]["search"]["properties"]["city"]["type"] == "string"

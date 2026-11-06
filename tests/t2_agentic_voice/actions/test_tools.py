"""Building a tool (actions/tools.py, actions/signature.py; the design's 4.4 and 6.4): `@tool` and
`Tool.from_function` on an async or a sync function, the parameters' model read from its
signature, the call's context found by its type and left out, a bound parameter filled from the
caller and hidden from the schema the talker sees; a function the library cannot call by its
parameters' names, or a value a tool refuses, a ConfigurationError naming the field, with a FIX
line, never the value."""

from __future__ import annotations

from typing import Annotated, Any, Literal

import pytest
from pydantic import BaseModel, Field, ValidationError
from t2_agentic_voice.actions.tools import CallContext, Tool, from_caller, tool
from t2_agentic_voice.core.errors import ConfigurationError
from t2_agentic_voice.core.identity import Caller

CALLER = Caller(
    subject="made-up-subject", display_name="Made Up", locale="ar-SA", attributes={"team": "it"}
)
AssetTag = Annotated[str, Field(pattern=r"^LT-\d{5}$", description="For example LT-00423")]


@tool(description="Find a device assigned to the caller, by its asset tag.", timeout_s=3)
async def lookup_device(
    ctx: CallContext, asset_tag: AssetTag, employee_id: str, detail: bool = False
) -> dict[str, str]:
    return {"tag": asset_tag, "owner": employee_id, "language": ctx.language}


def list_requests(employee_id: str, status: Literal["open", "closed"] = "open") -> list[str]:
    return [f"{status} requests of {employee_id}"]


def test_the_decorator_makes_a_tool_of_an_async_function_its_parameters_from_the_signature() -> (
    None
):
    assert isinstance(lookup_device, Tool)
    assert (lookup_device.name, lookup_device.timeout_s) == ("lookup_device", 3)
    assert (lookup_device.on_interrupt, lookup_device.progress) == ("cancel", None)
    fields = lookup_device.parameters.model_fields
    assert list(fields) == ["asset_tag", "employee_id", "detail"]  # no ctx
    parsed: Any = lookup_device.parameters.model_validate(
        {"asset_tag": "LT-00423", "employee_id": "x"}
    )
    assert parsed.detail is False
    with pytest.raises(ValidationError):
        lookup_device.parameters.model_validate({"asset_tag": "LT-1", "employee_id": "x"})
    with pytest.raises(ValidationError):  # an argument the function does not take
        lookup_device.parameters.model_validate(
            {"asset_tag": "LT-00423", "employee_id": "x", "admin": True}
        )


def test_from_function_wraps_a_sync_function_its_bound_parameter_hidden_from_the_schema() -> None:
    wrapped = Tool.from_function(
        list_requests,
        name="my_requests",
        description="List the caller's IT requests.",
        bind={"employee_id": from_caller("subject")},
        progress="searching",
        progress_after_s=0.5,
    )
    assert (wrapped.name, wrapped.progress, wrapped.progress_after_s) == (
        "my_requests",
        "searching",
        0.5,
    )
    schema = wrapped.tool_schema()
    assert schema.name == "my_requests"
    assert schema.parameters == {
        "additionalProperties": False,
        "properties": {"status": {"default": "open", "enum": ["open", "closed"], "type": "string"}},
        "type": "object",
    }
    assert "employee_id" not in str(schema.parameters)


class Article(BaseModel):
    """An article."""  # its docstring is the schema's description, which the talker reads

    title: str = Field(description="The article's title")
    tags: list[str] = []


def find(article: Article, title: str) -> str:
    return title


def test_a_schema_keeps_descriptions_and_a_property_named_title_and_drops_titles() -> None:
    schema: Any = Tool.from_function(find, description="Find an article.").tool_schema().parameters
    assert set(schema["properties"]) == {"article", "title"}
    assert schema["$defs"] == {
        "Article": {
            "description": "An article.",
            "properties": {
                "title": {"description": "The article's title", "type": "string"},
                "tags": {"default": [], "items": {"type": "string"}, "type": "array"},
            },
            "required": ["title"],
            "type": "object",
        }
    }
    assert '"title": "' not in str(schema).replace("'", '"')  # no schema title is left


def test_a_bound_parameter_takes_the_callers_field() -> None:
    assert from_caller("subject").value(CALLER) == "made-up-subject"
    assert from_caller("display_name").value(CALLER) == "Made Up"
    assert from_caller("locale").value(CALLER) == "ar-SA"
    assert from_caller("attributes.team").value(CALLER) == "it"
    assert from_caller("attributes.room").value(CALLER) is None
    assert from_caller("display_name").value(Caller(subject="x")) is None


async def _spread(*args: str) -> str:
    return ""


async def _keywords(**kwargs: str) -> str:
    return ""


async def _unannotated(query) -> str:  # type: ignore[no-untyped-def]
    return str(query)


def _positional(query: str, /) -> str:
    return query


def _strange(query: object) -> str:  # a type pydantic parses (any object), so it builds
    return str(query)


def test_an_annotation_that_cannot_be_read_is_a_configuration_error() -> None:
    """A model defined inside a function, under postponed annotations, cannot be found by name."""

    class Local(BaseModel):
        x: int

    def local(item: Local) -> int:
        return item.x

    with pytest.raises(ConfigurationError, match="cannot be read") as raised:
        Tool.from_function(local, description="Made up.")
    assert raised.value.details == {"field": "function"}


@pytest.mark.parametrize(
    ("function", "bind", "parameter"),
    [
        (_spread, None, "args"),
        (_keywords, None, "kwargs"),
        (_unannotated, None, "query"),
        (_positional, None, "query"),
        (list_requests, {"customer_id": from_caller("subject")}, "customer_id"),
    ],
)
def test_a_function_the_talker_cannot_call_by_name_is_a_configuration_error(
    function: Any, bind: Any, parameter: str
) -> None:
    with pytest.raises(ConfigurationError, match="FIX: ") as raised:
        Tool.from_function(function, description="Made up.", bind=bind)
    assert raised.value.details == {"field": "function", "parameter": parameter}
    assert Tool.from_function(_strange, description="Made up.").name == "_strange"


def _lambda_free(secret_value: str) -> str:
    return secret_value


@pytest.mark.parametrize(
    ("changes", "field"),
    [
        ({"name": "look up"}, "name"),
        ({"description": "  "}, "description"),
        ({"timeout_s": 0}, "timeout_s"),
        ({"progress": "Searching"}, "progress"),
        ({"progress": "searching", "progress_after_s": 9.0}, "progress_after_s"),
        ({"on_interrupt": "pause"}, "on_interrupt"),
    ],
)
def test_a_value_a_tool_refuses_is_a_configuration_error_naming_the_field(
    changes: dict[str, Any], field: str
) -> None:
    values: dict[str, Any] = {"description": "Made up."} | changes
    with pytest.raises(ConfigurationError, match="FIX: ") as raised:
        Tool.from_function(_lambda_free, **values)
    assert raised.value.details == {"field": field}
    assert "look up" not in str(raised.value)


def test_a_lambda_has_no_name_the_talker_can_call() -> None:
    with pytest.raises(ConfigurationError, match="FIX: ") as raised:
        Tool.from_function(lambda: "x", description="Made up.")
    assert raised.value.details == {"field": "name"}


class Opaque:
    """A type pydantic has no schema for."""


def _opaque(item: Opaque) -> str:
    return str(item)


def test_a_parameter_type_pydantic_cannot_parse_is_a_configuration_error() -> None:
    with pytest.raises(ConfigurationError, match="not one pydantic can parse") as raised:
        Tool.from_function(_opaque, description="Made up.")
    assert raised.value.details == {"field": "function"}


def _unreadable(query: Missing) -> str:  # type: ignore[name-defined]  # noqa: F821
    return str(query)


def test_a_tool_given_whole_whose_signature_cannot_be_read_runs_with_no_context() -> None:
    """A Tool built from its fields (not from_function) is never refused for its annotations:
    the runner gives it no context, and it runs."""
    import asyncio

    from t2_agentic_voice.actions.runner import ToolRunner
    from t2_agentic_voice.domain.ports.chat_model import ToolCallRequest

    from tests.t2_agentic_voice.fakes import FakeClock

    class Query(BaseModel):
        query: str

    given = Tool(name="unreadable", description="Made up.", parameters=Query, function=_unreadable)
    runner = ToolRunner([given])
    ctx = CallContext(caller=CALLER, call_id="call-1", language="en")
    request = ToolCallRequest(id="c-1", name="unreadable", arguments='{"query": "x"}')
    assert asyncio.run(runner.run(request, ctx, clock=FakeClock())).data == "x"

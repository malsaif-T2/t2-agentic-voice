"""The `t2v/1` message list (plan 003, step 11): the models of voice/protocol.py and
api/protocol.py match the committed fixture exactly, every message by direction, type and field,
and every route by its bodies, its success status and its error codes by status, with the one
error body, so a change to the protocol changes the fixture with it, in plain view.

Each field is written as the fixture's `about` says, from the model's own annotation; a client's
field is `(optional)` when it has a default, and every inbound model is the strict kind."""

from __future__ import annotations

import json
import types
from pathlib import Path
from typing import Annotated, Any, Literal, Union, get_args, get_origin

from pydantic import BaseModel, SecretStr
from pydantic.fields import FieldInfo
from t2_agentic_voice.api.protocol import BODIES, OFFER_SECRET_HEADER, ErrorBody, ErrorCode
from t2_agentic_voice.voice.protocol import (
    CLIENT_MESSAGES,
    PROTOCOL,
    RESERVED_PREFIX,
    RESERVED_TYPES,
    SESSION_MESSAGES,
)

FIXTURE = Path(__file__).parent / "fixtures" / "t2v_protocol.json"
_NAMES = {str: "string", SecretStr: "string", int: "integer", float: "number", bool: "boolean"}
ENVELOPE = ("v", "type")


def _spelled(annotation: Any, objects: dict[str, type[BaseModel]]) -> str:
    """A type as the fixture writes it; each object it names is added to `objects`."""
    origin = get_origin(annotation)
    if origin is Annotated:
        return _spelled(get_args(annotation)[0], objects)
    if origin is Literal:
        return " | ".join(str(value) for value in get_args(annotation))
    if origin in (Union, types.UnionType):
        return " | ".join(_spelled(arg, objects) for arg in get_args(annotation))
    if origin in (list, tuple):
        return f"[{_spelled(get_args(annotation)[0], objects)}]"
    if annotation is type(None):
        return "null"
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        objects[annotation.__name__] = annotation
        return annotation.__name__
    return _NAMES[annotation]


def _field(info: FieldInfo, inbound: bool, objects: dict[str, type[BaseModel]]) -> str:
    spelled = _spelled(info.annotation, objects)
    return f"{spelled} (optional)" if inbound and not info.is_required() else spelled


def _fields(
    model: type[BaseModel], objects: dict[str, type[BaseModel]], skip: tuple[str, ...] = ()
) -> dict[str, str]:
    """The model's fields as the fixture lists them; a model the client sends (inbound) is
    parsed strictly."""
    inbound = model.model_config.get("strict") is True
    return {
        name: _field(info, inbound, objects)
        for name, info in model.model_fields.items()
        if name not in skip
    }


def _type(model: type[BaseModel]) -> str:
    (name,) = get_args(model.model_fields["type"].annotation)
    return str(name)


def _fixture() -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return loaded


def test_the_data_channels_messages_are_the_lists() -> None:
    fixture, objects = _fixture(), dict[str, type[BaseModel]]()
    assert (fixture["protocol"], PROTOCOL) == (1, 1)
    assert fixture["reserved"] == {"types": list(RESERVED_TYPES), "text_prefix": RESERVED_PREFIX}
    listed = fixture["data_channel"]
    for direction, models, strict in (
        ("client_to_session", CLIENT_MESSAGES, True),
        ("session_to_client", SESSION_MESSAGES, None),
    ):
        built = {_type(model): _fields(model, objects, skip=ENVELOPE) for model in models}
        assert list(built) == list(listed[direction]), direction
        assert built == listed[direction], direction
        for model in models:
            assert model.model_config.get("strict") is strict, model
            assert get_args(model.model_fields["v"].annotation) == (PROTOCOL,), model
    assert objects == {}  # no message nests an object


def test_the_http_bodies_and_their_objects_are_the_lists() -> None:
    fixture, objects = _fixture(), dict[str, type[BaseModel]]()
    assert fixture["offer_secret_header"] == OFFER_SECRET_HEADER
    built = {
        path: {
            "request": _fields(route.request, objects),
            "status": route.status,
            "response": None if route.response is None else _fields(route.response, objects),
            "errors": {str(status): list(codes) for status, codes in route.errors.items()},
        }
        for path, route in BODIES.items()
    }
    assert list(built) == list(fixture["http"])
    assert built == fixture["http"]
    nested = {name: _fields(model, {}) for name, model in objects.items()}
    assert nested == fixture["objects"]
    assert {route.request.model_config.get("strict") for route in BODIES.values()} == {True}


def test_the_one_error_body_and_its_codes_are_the_lists() -> None:
    """Every route answers each error in the one body; each code is some route's answer. Every
    route answers a body over its cap, one not sent as JSON, a crash and a runtime not started
    alike, and a PATCH with the call's own secret before its offer was answered gets a quiet
    409 of its own."""
    assert _fields(ErrorBody, {}) == _fixture()["error_body"]
    statuses = [status for route in BODIES.values() for status in route.errors]
    codes = {code for route in BODIES.values() for each in route.errors.values() for code in each}
    assert codes == set(get_args(ErrorCode)) and all(400 <= s < 600 for s in statuses)
    shared = {413: ("too_large",), 415: ("unsupported_media_type",), 500: ("internal_error",)}
    shared |= {503: ("not_started",)}
    assert all(dict(route.errors).items() >= shared.items() for route in BODIES.values())
    assert BODIES["PATCH /offer"].errors[409] == ("not_offered", "ice_completed", "call_ended")


def test_the_fixture_spells_each_kind_of_field() -> None:
    """The spelling's own cases, so a field of a new kind fails here, named, not as a KeyError."""
    objects: dict[str, type[BaseModel]] = {}
    assert _spelled(Annotated[int, "x"] | None, objects) == "integer | null"
    assert _spelled(tuple[Literal["a", "b"], ...], objects) == "[a | b]"
    assert _spelled(list[SecretStr], objects) == "[string]"
    assert _spelled(float, objects) == "number" and _spelled(bool, objects) == "boolean"

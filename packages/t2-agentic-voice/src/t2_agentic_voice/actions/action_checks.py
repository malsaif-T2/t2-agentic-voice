"""What `@action` refuses as it is built (the design's 6.4; docs/SECURITY.md, invariant 4): a draft
the talker could use to claim a yes, a template that names a field its model has not, and a
fixed value with no way to be said. Each is a ConfigurationError naming the field, with a FIX
line, never a value.

The refusal of a consent-named field reads the JSON schema the talker sees, its nested models
and aliases included, beside the model's own field names: a nested field or an alias appears
nowhere else.
"""

from __future__ import annotations

import inspect
import re
from collections.abc import Callable, Iterable
from enum import Enum
from types import UnionType
from typing import Annotated, Any, Literal, Union, get_args, get_origin

from pydantic import BaseModel
from pydantic.errors import PydanticUserError

from t2_agentic_voice.actions.signature import context_parameter
from t2_agentic_voice.domain.action_declaration import ReadBack, Say, Spoken, refused

# What a field named like consent holds, wherever it is in the name; and the words that count
# only as whole words, since "yes" and "agree" sit inside other words.
_STEMS = ("confirm", "consent", "approv", "authoriz", "authoris")
_WHOLE = frozenset({"yes", "agree", "agreed", "agrees", "accept", "accepted"})
_WORDS = re.compile(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+")
_CONSENT_FIX = (
    "rename the field: the talker writes the draft, so a draft can claim nothing about the "
    "caller's yes, which only the words heard after the read-back give"
)
_FIELDS_FIX = "name only a field of the draft (in `done`, of the result)"
_SPOKEN_FIX = (
    'put the labels on the field\'s type, as Annotated[Literal["a"], Spoken({"a": {"ar": "..."}})]'
)


def named_like_consent(name: str) -> bool:
    """Whether a field called `name` reads as a claim of the caller's consent."""
    joined = re.sub("[^a-z]", "", name.lower())
    words = {word.lower() for word in _WORDS.findall(name)}
    return any(stem in joined for stem in _STEMS) or bool(words & _WHOLE)


def _field_names(node: Any) -> Iterable[str]:
    """Every property name anywhere in the JSON schema `node`."""
    if isinstance(node, list):
        for item in node:
            yield from _field_names(item)
    elif isinstance(node, dict):
        for key, value in node.items():
            if key == "properties" and isinstance(value, dict):
                yield from value
            yield from _field_names(value)


def _schema(draft: type[BaseModel]) -> dict[str, Any]:
    try:
        return draft.model_json_schema()
    except PydanticUserError:
        raise refused(
            "draft",
            "its schema cannot be made",
            "give every field a type pydantic can write as JSON",
        ) from None


def check_draft(draft: object) -> type[BaseModel]:
    """`draft` when it is a pydantic model whose schema has no field named like consent."""
    if not (isinstance(draft, type) and issubclass(draft, BaseModel)):
        raise refused(
            "draft",
            "it is not a pydantic model",
            "annotate the function's `draft` parameter with one",
        )
    names = set(draft.model_fields) | set(_field_names(_schema(draft)))
    for name in sorted(names):
        if named_like_consent(name):
            raise refused(
                "draft",
                f"its field `{name}` is named like the caller's consent",
                _CONSENT_FIX,
            )
    return draft


def check_fields(field: str, named: frozenset[str], fields: Iterable[str]) -> None:
    """Refuses a template that names a field `fields` does not hold."""
    if named - set(fields):
        raise refused(field, "a template names a field that does not exist", _FIELDS_FIX)


def _fixed_values(annotation: object) -> tuple[str, ...] | None:
    """The fixed values a field's type allows, as text; None for a type that fixes none."""
    origin = get_origin(annotation)
    if origin is Annotated:
        return _fixed_values(get_args(annotation)[0])
    if origin in (Union, UnionType):
        found = [v for a in get_args(annotation) if (v := _fixed_values(a)) is not None]
        return found[0] if found else None
    if origin is Literal:
        return tuple(str(value) for value in get_args(annotation))
    if isinstance(annotation, type) and issubclass(annotation, Enum):
        return tuple(str(member.value) for member in annotation)
    return None


def check_read_back(read_back: ReadBack, draft: type[BaseModel]) -> None:
    """Refuses a read-back that names a field the draft has not, or a fixed value it could not
    say: every `Literal` field it names needs `Spoken` labels, one for each value."""
    check_fields("read_back", read_back.placeholders, draft.model_fields)
    for name in read_back.placeholders:
        field = draft.model_fields[name]
        values = _fixed_values(field.annotation)
        if values is None:
            continue
        labels = next((m.labels for m in field.metadata if isinstance(m, Spoken)), None)
        if labels is None or set(labels) != set(values):
            raise refused(
                "read_back",
                f"its field `{name}` is a fixed value with no label for each value",
                _SPOKEN_FIX,
            )


def check_templates(
    done: Say,
    result: type[BaseModel],
    draft: type[BaseModel],
    outcomes: Iterable[tuple[str, Say | None]],
) -> None:
    """`done` names only the result's fields; each other outcome only the draft's."""
    check_fields("done", done.placeholders, result.model_fields)
    for field, say in outcomes:
        if say is not None:
            check_fields(field, say.placeholders, draft.model_fields)


def _parameters(function: Callable[..., Any]) -> tuple[inspect.Signature, Any]:
    try:
        signature = inspect.signature(function, eval_str=True)
    except (NameError, SyntaxError, TypeError, ValueError):
        raise refused(
            "execute",
            "its signature, or an annotation in it, cannot be read",
            "annotate its parameters with types that can be imported where it is defined",
        ) from None
    return signature, signature.parameters.get("draft")


def draft_and_result(
    function: Callable[..., Any], *, context: type
) -> tuple[type[BaseModel], type[BaseModel]]:
    """The draft and the result `function`'s signature declares: a `draft` parameter and a
    return annotation, each a pydantic model, and no parameter but those and its context."""
    signature, draft = _parameters(function)
    if draft is None:
        raise refused(
            "draft",
            "the function has no `draft` parameter",
            "take the draft as a parameter named draft, annotated with a pydantic model",
        )
    own = context_parameter(function, context=context)
    if any(name not in ("draft", own) for name in signature.parameters):
        raise refused(
            "execute",
            "it takes a parameter other than its context and its draft",
            "take only `ctx: ActionContext` and `draft`, and reach your system by a closure",
        )
    returned = signature.return_annotation
    if not (isinstance(returned, type) and issubclass(returned, BaseModel)):
        raise refused(
            "execute",
            "its return annotation is not a pydantic model",
            "return a model whose fields `done` names",
        )
    return check_draft(draft.annotation), returned

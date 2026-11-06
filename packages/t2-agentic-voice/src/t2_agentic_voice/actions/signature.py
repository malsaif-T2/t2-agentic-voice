"""What a tool's function says of itself (actions/tools.py; the design's 6.4): the model of the
arguments the talker gives, read from its signature; which of its parameters is the call's
context, found by its type (`CallContext`), and optional; and whether it is async or sync (a
sync one runs in a worker thread). A function the library cannot call by its parameters' names
is a ConfigurationError, with a FIX line, naming the parameter and never a value.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable, Collection
from typing import Any

from pydantic import BaseModel, ConfigDict, create_model
from pydantic.errors import PydanticUserError

from t2_agentic_voice.core.errors import ConfigurationError

# The arguments' model of a function: a misspelt or extra argument is an error the talker is
# told of, the field named (invariant 4), and no error repeats a value it refused.
ARGUMENTS = ConfigDict(extra="forbid", hide_input_in_errors=True, protected_namespaces=())
_FIX = (
    "FIX: give the function named parameters, each with a type annotation the talker fills "
    "(as `asset_tag: str`), a `CallContext` parameter if it reads the call, and bind= only "
    "parameters it has; or build the Tool with its own `parameters` model."
)


def _refused(what: str, *, parameter: str | None = None) -> ConfigurationError:
    details: dict[str, Any] = {"field": "function"}
    if parameter is not None:
        details["parameter"] = parameter
    message = f"A tool cannot be built from its function: {what}. {_FIX}"
    return ConfigurationError(message, details=details)


def _signature(function: Callable[..., Any]) -> inspect.Signature:
    """`function`'s signature, its annotations evaluated (a module with postponed annotations
    writes them as text)."""
    try:
        return inspect.signature(function, eval_str=True)
    except (NameError, SyntaxError, TypeError, ValueError):
        raise _refused("its signature, or an annotation in it, cannot be read") from None


def _is(annotation: object, context: type) -> bool:
    """Whether `annotation` is the call's `context` class, or a class built on it."""
    return isinstance(annotation, type) and issubclass(annotation, context)


def context_parameter(function: Callable[..., Any], *, context: type) -> str | None:
    """The name of `function`'s parameter annotated as the call's `context` (`CallContext`),
    None when it has none, or when its signature cannot be read: such a function is given no
    context."""
    try:
        parameters = inspect.signature(function, eval_str=True).parameters
    except (NameError, SyntaxError, TypeError, ValueError):
        return None
    return next((name for name, p in parameters.items() if _is(p.annotation, context)), None)


def is_async(function: Callable[..., Any]) -> bool:
    """Whether calling `function` gives a coroutine: an async function, a partial of one, or an
    object whose `__call__` is one."""
    call = getattr(function, "__call__", None)  # noqa: B004 - an object's own async __call__
    return inspect.iscoroutinefunction(function) or inspect.iscoroutinefunction(call)


def arguments_model(
    function: Callable[..., Any], *, bound: Collection[str], context: type
) -> type[BaseModel]:
    """The model of the arguments the talker gives `function`: each of its parameters, typed by
    its annotation and with its default, but the call's `context` (`CallContext`) and the
    parameters `bound` fills from the session, which the talker never sees."""
    parameters = _signature(function).parameters
    missing = sorted(set(bound) - set(parameters))
    if missing:
        raise _refused("bind= names a parameter the function does not have", parameter=missing[0])
    fields: dict[str, Any] = {}
    for name, parameter in parameters.items():
        if parameter.kind in (parameter.VAR_POSITIONAL, parameter.VAR_KEYWORD):
            raise _refused("it takes *args or **kwargs", parameter=name)
        if parameter.kind is parameter.POSITIONAL_ONLY:
            raise _refused("a parameter is positional-only", parameter=name)
        if _is(parameter.annotation, context) or name in bound:
            continue
        if parameter.annotation is parameter.empty:
            raise _refused("a parameter the talker fills has no type annotation", parameter=name)
        default = ... if parameter.default is parameter.empty else parameter.default
        fields[name] = (parameter.annotation, default)
    try:
        return create_model("Arguments", __config__=ARGUMENTS, **fields)
    except (PydanticUserError, TypeError, ValueError):
        raise _refused("a parameter's type is not one pydantic can parse") from None

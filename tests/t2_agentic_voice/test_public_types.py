"""No public signature names a type of Pipecat, aiortc, onnxruntime or groq (the design's 5.3,
point 1), so a team's code is written against the library's own types and the frameworks under
it can move without breaking the team. Every name in a public module's `__all__` is read: a
function's parameters and return; a class's fields and annotated attributes, and the parameters
and return of its constructor and of each public method and property the library defines on it
or on a base of its own; a type alias's value (`type Pronunciations = ...`); each annotation
resolved and followed to every class it names, through any alias it names."""

from __future__ import annotations

import importlib
import inspect
import typing
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Literal, Protocol

import pytest

from scripts.harness_config import load_config

ROOT = Path(__file__).resolve().parents[2]
PUBLIC = sorted(load_config(ROOT).arch.public)
LIBRARY = "t2_agentic_voice"
# The frameworks a public signature never names, by their top-level package.
FRAMEWORKS = ("pipecat", "aiortc", "onnxruntime", "groq")


def _params(obj: object) -> dict[str, object]:
    """The type parameters `obj` declares (`def on[E: Event]`), which its annotations name."""
    return {p.__name__: p for p in getattr(obj, "__type_params__", ())}


def annotations_of(obj: object, *, library: str = LIBRARY) -> Iterator[object]:
    """Every annotation of `obj`'s public signature, resolved; a class's members are read on
    each of its bases that sits in `library`, where the library defines them. A type alias has
    no signature: its value is what it names."""
    if isinstance(obj, typing.TypeAliasType):
        yield obj.__value__
        return
    params = _params(obj)
    yield from typing.get_type_hints(obj, localns=params or None).values()
    if not inspect.isclass(obj):
        return
    for base in obj.__mro__:
        if not base.__module__.startswith(f"{library}."):
            continue
        for name, member in vars(base).items():
            if name.startswith("_") and name != "__init__":
                continue
            if isinstance(member, classmethod | staticmethod):
                member = member.__func__
            elif isinstance(member, property):
                member = member.fget
            if inspect.isfunction(member) and member.__module__.startswith(f"{library}."):
                hints = typing.get_type_hints(member, localns=params | _params(member))
                yield from hints.values()


def named(annotation: object) -> Iterator[type]:
    """Every class `annotation` names: itself, its origin and arguments (a union's members, a
    generic's parameters, a callable's), a type variable's bound and constraints, and what a
    type alias stands for."""
    if isinstance(annotation, typing.TypeAliasType):
        yield from named(annotation.__value__)
        return
    if isinstance(annotation, typing.TypeVar):
        for each in (annotation.__bound__, *annotation.__constraints__):
            yield from named(each)
        return
    if isinstance(annotation, list | tuple):
        for each in annotation:
            yield from named(each)
        return
    if isinstance(annotation, type):
        yield annotation
    if (origin := typing.get_origin(annotation)) is not None:
        yield from named(origin)
        yield from named(typing.get_args(annotation))


def frameworks(obj: object, *, library: str = LIBRARY) -> set[str]:
    """The framework classes `obj`'s public signature names, each by its module and name."""
    return {
        f"{kind.__module__}.{kind.__qualname__}"
        for annotation in annotations_of(obj, library=library)
        for kind in named(annotation)
        if kind.__module__.split(".")[0] in FRAMEWORKS
    }


def _public() -> Iterator[tuple[str, str]]:
    for module in PUBLIC:
        for name in importlib.import_module(module).__all__:
            yield module, name


@pytest.mark.parametrize(("module", "name"), sorted(_public()))
def test_no_public_signature_names_a_frameworks_type(module: str, name: str) -> None:
    found = frameworks(getattr(importlib.import_module(module), name))
    assert found == set(), (
        f"{module}.{name} names {sorted(found)} in its signature. FIX: take and return the "
        "library's own types (a port's data type, a pydantic model), and convert to and from "
        "the framework's inside the module that uses it."
    )


def test_every_public_module_is_read() -> None:
    assert {module for module, _ in _public()} == set(PUBLIC)


class AsyncGroq:
    """A stand-in for a framework's class, named by its module as the framework's own is."""

    __module__ = "groq._client"


class _Port(Protocol):
    def send(self, client: AsyncGroq) -> None: ...


class _Holder:
    @property
    def clients(self) -> dict[str, list[AsyncGroq | None]]:
        return {}


def _made[C: AsyncGroq](make: Callable[[], C]) -> C:
    return make()


def _plain(text: Literal["a"], count: int, *rest: str) -> tuple[str, ...] | None:
    return None


type _Clients = dict[str, list[AsyncGroq]]
type _Words = dict[str, list[str]]


def _aliased(clients: _Clients) -> None:
    return None


def test_the_check_finds_a_frameworks_type_wherever_a_signature_names_it() -> None:
    """In a protocol's parameter, inside a property's generic return, in a type variable's
    bound, in a type alias and behind one a parameter names; the stand-ins sit in this module,
    which the check reads as it reads the library."""
    here = __name__.split(".")[0]
    for found in (_Port, _Holder, _made, _Clients, _aliased):
        assert frameworks(found, library=here) == {"groq._client.AsyncGroq"}, found
    for plain in (_plain, _Words):
        assert frameworks(plain, library=here) == set(), plain

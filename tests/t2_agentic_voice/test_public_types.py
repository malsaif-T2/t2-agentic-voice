"""No public signature names a type of Pipecat, aiortc, onnxruntime or groq (the design's 5.3,
point 1), and every class of the library a public signature names is public itself (D-032), so a
team writes its code against the library's own types, which it can import, and the frameworks
under it can move without breaking the team.

Every name in a public module's `__all__` is read, and then every class of the library its
signature names, in turn: a function's parameters and return; a class's bases, its fields and
annotated attributes, and the parameters and return of its constructor, of the dunders a caller
uses (`__call__`, `__enter__`, `__getitem__` and the like) and of each public method, property and
cached property the library defines on it or on a base of its own; a type alias's value. Each
annotation is resolved and followed to every class it names, through any type alias or NewType. A
parameter or field whose name starts with `_` is private, and is not read."""

from __future__ import annotations

import functools
import importlib
import inspect
import typing
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Literal, NewType, Protocol

import pytest
from pydantic import BaseModel

from scripts.harness_config import load_config

ROOT = Path(__file__).resolve().parents[2]
PUBLIC = sorted(load_config(ROOT).arch.public)
LIBRARY = "t2_agentic_voice"
# The frameworks a public signature never names, by their top-level package.
FRAMEWORKS = ("pipecat", "aiortc", "onnxruntime", "groq", "torch", "speechbrain")
# The dunders a caller uses, read with the public methods.
DUNDERS = frozenset(
    {
        "__init__",
        "__new__",
        "__call__",
        "__enter__",
        "__exit__",
        "__aenter__",
        "__aexit__",
        "__iter__",
        "__aiter__",
        "__next__",
        "__anext__",
        "__getitem__",
        "__contains__",
        "__await__",
    }
)


def _params(obj: object) -> dict[str, object]:
    """The type parameters `obj` declares (`def on[E: Event]`), which its annotations name."""
    return {p.__name__: p for p in getattr(obj, "__type_params__", ())}


def _hints(obj: object, localns: dict[str, object]) -> Iterator[object]:
    """`obj`'s resolved annotations, but a private name's (`_calls`)."""
    for name, hint in typing.get_type_hints(obj, localns=localns or None).items():
        if not name.startswith("_"):
            yield hint


def _members(base: type) -> Iterator[object]:
    """The functions behind the public members and the dunders `base` itself defines."""
    for name, member in vars(base).items():
        if name.startswith("_") and name not in DUNDERS:
            continue
        if isinstance(member, classmethod | staticmethod):
            yield member.__func__
        elif isinstance(member, property):
            yield from (f for f in (member.fget, member.fset) if f is not None)
        elif isinstance(member, functools.cached_property):
            yield member.func
        else:
            yield member


def _in(obj: object, library: str) -> bool:
    return getattr(obj, "__module__", "").startswith(f"{library}.")


def annotations_of(obj: object, *, library: str = LIBRARY) -> Iterator[object]:
    """Every annotation of `obj`'s public signature, resolved; a class's members are read on
    each of its bases that sits in `library`, where the library defines them. A type alias and
    a NewType have no signature: what they stand for is what they name."""
    if isinstance(obj, typing.TypeAliasType):
        yield obj.__value__
        return
    if isinstance(obj, NewType):
        yield obj.__supertype__
        return
    params = _params(obj)
    yield from _hints(obj, params)
    if not inspect.isclass(obj):
        return
    for base in (b for b in obj.__mro__ if _in(b, library)):
        for member in _members(base):
            if inspect.isfunction(member) and _in(member, library):
                yield from _hints(member, params | _params(member))


def named(annotation: object) -> Iterator[type]:
    """Every class `annotation` names: itself, its origin and arguments (a union's members, a
    generic's parameters, a callable's), a type variable's bound and constraints, and what a
    type alias or a NewType stands for."""
    if isinstance(annotation, typing.TypeAliasType):
        yield from named(annotation.__value__)
        return
    if isinstance(annotation, NewType):
        yield from named(annotation.__supertype__)
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


def reached(obj: object, *, library: str = LIBRARY) -> tuple[set[type], list[object]]:
    """The classes `obj`'s public signature names, and those the library's classes among them
    name in theirs, in turn; and what was read: `obj`, then each of those library classes."""
    found: set[type] = set()
    read = [obj]
    for each in read:
        for kind in (k for a in annotations_of(each, library=library) for k in named(a)):
            if kind not in found:
                found.add(kind)
                if _in(kind, library) and kind not in read:
                    read.append(kind)
    return found, read


def _framework(kind: type) -> bool:
    return kind.__module__.split(".")[0] in FRAMEWORKS


def frameworks(obj: object, *, library: str = LIBRARY) -> set[str]:
    """The framework classes `obj`'s public signature names, directly or through the library's
    own classes it names, or that one of those, or `obj`, is built on; each by module and name."""
    found, read = reached(obj, library=library)
    bases = {base for each in read if inspect.isclass(each) for base in each.__mro__}
    return {f"{k.__module__}.{k.__qualname__}" for k in found | bases if _framework(k)}


def _public() -> Iterator[tuple[str, str]]:
    for module in PUBLIC:
        for name in importlib.import_module(module).__all__:
            yield module, name


def _object(module: str, name: str) -> object:
    return getattr(importlib.import_module(module), name)


@pytest.mark.parametrize(("module", "name"), sorted(_public()))
def test_no_public_signature_names_a_frameworks_type(module: str, name: str) -> None:
    found = frameworks(_object(module, name))
    assert found == set(), (
        f"{module}.{name} names {sorted(found)} in its signature. FIX: take and return the "
        "library's own types (a port's data type, a pydantic model), and convert to and from "
        "the framework's inside the module that uses it."
    )


def test_every_library_class_a_public_signature_names_is_public() -> None:
    """D-032: a team can import every type a public signature asks it for."""
    exported = {id(_object(module, name)) for module, name in _public()}
    named_here = {k for each in _public() for k in reached(_object(*each))[0]}
    missing = sorted(
        f"{k.__module__}.{k.__qualname__}"
        for k in named_here
        if _in(k, LIBRARY) and id(k) not in exported
    )
    assert missing == [], (
        f"Public signatures name {missing}, which no public module exports. FIX: re-export each "
        "from the public module whose row of the design's 5.1 it belongs with, and add it to "
        "tests/t2_agentic_voice/test_facades.py; or type the signature with a public type."
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


def _private(text: str, _client: AsyncGroq | None = None) -> None:
    return None


type _Clients = dict[str, list[AsyncGroq]]
type _Words = dict[str, list[str]]
type _Handler = Callable[[AsyncGroq], None]
_Client = NewType("_Client", AsyncGroq)


def _aliased(clients: _Clients) -> None:
    return None


class _WithCall:
    def __call__(self, client: AsyncGroq) -> None: ...


class _WithCached:
    @functools.cached_property
    def client(self) -> AsyncGroq:
        return AsyncGroq()


class _WithAlias:
    def on(self, handler: _Handler) -> None: ...


def _with_new_type(client: _Client) -> None:
    return None


class _WithAEnter:
    async def __aenter__(self) -> AsyncGroq:
        return AsyncGroq()


class _Sub(AsyncGroq):
    """A class built on a framework's."""


class _Inner(BaseModel):
    def client(self) -> AsyncGroq:
        return AsyncGroq()


class _Outer(BaseModel):
    inner: _Inner


def test_the_check_finds_a_frameworks_type_wherever_a_signature_names_it() -> None:
    """In a protocol's parameter, inside a property's generic return, in a type variable's
    bound, in a type alias and behind one a parameter names, in `__call__` and `__aenter__`, in a
    cached property, behind a NewType, among a class's bases, and in a method of a library class
    a field names; the stand-ins sit in this module, which the check reads as it reads the
    library."""
    here = __name__.split(".")[0]
    found: list[object] = [_Port, _Holder, _made, _Clients, _aliased, _WithCall, _WithCached]
    found += [_WithAlias, _with_new_type, _WithAEnter, _Sub, _Outer]
    for each in found:
        assert frameworks(each, library=here) == {"groq._client.AsyncGroq"}, each
    for plain in (_plain, _Words, _private):
        assert frameworks(plain, library=here) == set(), plain
    assert _Inner in reached(_Outer, library=here)[0]

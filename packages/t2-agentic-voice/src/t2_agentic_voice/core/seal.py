"""How a class only one layer may build is built and recognised (docs/SECURITY.md, invariants 1
and 2), the same way core/identity.py's `SignedConsent` is (invariant 8), kept apart from it so
that module stays as its invariant's reviews left it.

A `SealedModel` is frozen, strict, a misspelt key an error, and built only by a validation given
its class's seal as the context, an object one module defines and compares by identity. Every
other way to build or change one raises TypeError: the constructor (pydantic's `__init__` passes
no context), a validation without the seal, `model_construct`, `model_copy` with an update, and
a subclass. The validation records that very instance; `still_sealed(instance)` is true only for
it, alive, each field the same object. A copy of any kind reads the same and proves nothing, so
each class's module offers one module-level check (`is_heard_words` and its kin) that asks for
its own type and `still_sealed`. Other layers ask that check and never test the class.

So a seal's fields are texts, numbers and tuples, never a team's mutable object, which is why a
draft travels as its JSON text. `[[restricted]]` (ARCH-CONSTRUCT) reports the calls that build
one outside its layer and any mention of its seal's name outside the modules listed; each row
says what the seal alone guards. Memory rewritten through `ctypes`, or a write to this module's
registry, gets past both, for review, as for `SignedConsent`.
"""

from __future__ import annotations

import weakref
from collections.abc import Mapping
from dataclasses import dataclass
from functools import partial
from typing import Any, ClassVar, Self

from pydantic import BaseModel, ConfigDict


@dataclass(frozen=True, slots=True)
class _Record:
    """An instance as its seal's validation built it: a weak reference to it, the `__dict__`
    that holds its fields (a re-called `__init__` gives it another), and each field's value."""

    instance: weakref.ref[SealedModel]
    fields: dict[str, Any]
    values: tuple[tuple[str, Any], ...]

    def holds(self, instance: SealedModel) -> bool:
        """Whether `instance` is that instance, alive, each field still the same object."""
        fields = instance.__dict__
        return (
            self.instance() is instance
            and fields is self.fields
            and len(fields) == len(self.values)
            and all(name in fields and fields[name] is value for name, value in self.values)
        )


# Each instance a seal's validation built, by its id(): only this module reads or writes it. An
# entry goes when its instance is collected, before the id is free again.
_SEALED: dict[int, _Record] = {}


def _forget(key: int, _: object) -> None:
    """Drops the entry of a collected instance."""
    _SEALED.pop(key, None)


class SealedModel(BaseModel):
    """What every sealed class is (the module's docstring). Each is `@final`, built directly on
    this class, says who builds it (`refusal`), and has `model_post_init` call `_seal_with` with
    its own seal: pydantic calls that after every validation, with its context, and after
    `model_construct`, with none."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True, hide_input_in_errors=True)

    refusal: ClassVar[str] = "Only the module that holds its seal builds this."

    def __init_subclass__(cls, **kwargs: Any) -> None:
        if cls.__bases__ != (SealedModel,):
            raise TypeError(f"{cls.__name__} takes no subclass. {cls.refusal}")
        super().__init_subclass__(**kwargs)

    def _seal_with(self, context: Any, seal: object) -> None:
        """Refuses this instance unless its validation was given `seal`, and records it: a
        subclass's instance is refused, past a mixin that skips the refusal at its definition."""
        if context is not seal or type(self).__bases__ != (SealedModel,):
            raise TypeError(self.refusal)
        key, fields = id(self), self.__dict__
        record = _Record(weakref.ref(self, partial(_forget, key)), fields, tuple(fields.items()))
        _SEALED[key] = record

    def model_copy(self, *, update: Mapping[str, Any] | None = None, deep: bool = False) -> Self:
        """A copy, which proves nothing; never one with an `update`, which pydantic does not
        validate."""
        if update:
            raise TypeError(self.refusal)
        return super().model_copy(deep=deep)

    def copy(
        self,
        *,
        include: object = None,
        exclude: object = None,
        update: Mapping[str, Any] | None = None,
        deep: bool = False,
    ) -> Self:
        """Pydantic's deprecated copy, which proves nothing; never given `update`, `include` or
        `exclude`, which it neither validates nor checks."""
        if include is not None or exclude is not None or update is not None:
            raise TypeError(self.refusal)
        return super().copy(deep=deep)


def still_sealed(instance: SealedModel) -> bool:
    """Whether `instance` is the very object a seal's validation built, unchanged since. Each
    class's own check asks this after its type."""
    record = _SEALED.get(id(instance))
    return record is not None and record.holds(instance)

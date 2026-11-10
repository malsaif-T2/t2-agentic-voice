"""Every class only one layer may build (docs/SECURITY.md, invariants 1 and 2) is sealed the same
way: only a validation given its seal makes one, only that very instance, unchanged, counts, and
`poe arch` reports the class and its seal anywhere but in the modules that hold them."""

from __future__ import annotations

import ast
import copy
import gc
import pickle
import weakref
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel, create_model
from t2_agentic_voice.core import seal as seal_module
from t2_agentic_voice.core.seal import SealedModel
from t2_agentic_voice.core.yes_inputs import (
    HEARD_WORDS_SEAL,
    READ_BACK_SEAL,
    HeardWords,
    ReadBackReceipt,
    is_heard_words,
    is_read_back_receipt,
)
from t2_agentic_voice.domain.completed_action import RECORD_SEAL, CompletedAction, is_recorded
from t2_agentic_voice.domain.yes_rule import CONFIRMED_SEAL, ConfirmedAction, is_confirmed

from scripts.arch_module import ModuleChecker
from scripts.harness_config import load_config

ROOT = Path(__file__).resolve().parents[3]
HEARD: dict[str, Any] = {
    "turn_id": 3,
    "text": "made-up yes",
    "language": "en",
    "at": 9.0,
    "speech_at": 8.0,
}
RECEIPT: dict[str, Any] = {
    "action": "open_request",
    "draft_json": '{"summary": "made up"}',
    "reply_id": 4,
    "summary_played_at": 6.0,
}
CONFIRMED: dict[str, Any] = {
    "action": "open_request",
    "draft_json": '{"summary": "made up"}',
    "reply_id": 4,
    "turn_id": 3,
    "words": "made-up yes",
    "source": "speech_to_text",
    "speech_at": 8.0,
}
COMPLETED: dict[str, Any] = {
    "action": "open_request",
    "request_id": "r-1",
    "result_json": '{"id": "1234"}',
    "evidence": ("1234",),
    "at": 12.0,
}
# Each sealed class: its class, its seal, its fields, its one check, its seal's name, and the
# modules the harness lets name it.
Sealed = tuple[type[SealedModel], object, dict[str, Any], Callable[[object], bool], str, str]
SEALED: dict[str, Sealed] = {
    "heard words": (
        HeardWords,
        HEARD_WORDS_SEAL,
        HEARD,
        is_heard_words,
        "HEARD_WORDS_SEAL",
        "voice/session/heard.py",
    ),
    "a receipt": (
        ReadBackReceipt,
        READ_BACK_SEAL,
        RECEIPT,
        is_read_back_receipt,
        "READ_BACK_SEAL",
        "voice/session/read_back.py",
    ),
    "a confirmed action": (
        ConfirmedAction,
        CONFIRMED_SEAL,
        CONFIRMED,
        is_confirmed,
        "CONFIRMED_SEAL",
        "domain/yes_rule.py",
    ),
    "a completed action": (
        CompletedAction,
        RECORD_SEAL,
        COMPLETED,
        is_recorded,
        "RECORD_SEAL",
        "actions/record.py",
    ),
}
CASES = list(SEALED.values())
IDS = list(SEALED)


def _built(kind: type[SealedModel], seal: object, values: dict[str, Any]) -> SealedModel:
    return kind.model_validate(values, context=seal)


@pytest.mark.parametrize(("kind", "seal", "values", "check", "name", "file"), CASES, ids=IDS)
def test_the_seal_builds_one_and_its_check_says_so(
    kind: type[SealedModel],
    seal: object,
    values: dict[str, Any],
    check: Callable[[object], bool],
    name: str,
    file: str,
) -> None:
    made = _built(kind, seal, values)
    assert type(made) is kind and check(made) is True
    assert check(made) is True  # asking changes nothing
    for other in (object(), None, "a made-up text", kind.model_fields):
        assert check(other) is False


# The ways the design's reviews found to build or change a sealed object outside its layer, each
# refused at run time: `made` is one its layer built.
UNSEALED: dict[str, Callable[[type[SealedModel], dict[str, Any], SealedModel], object]] = {
    "the constructor": lambda kind, values, _: kind(**values),
    "type(made)(...)": lambda _, values, made: type(made)(**values),
    "model_validate": lambda kind, values, _: kind.model_validate(values),
    "model_validate_json": lambda kind, values, made: kind.model_validate_json(
        made.model_dump_json()
    ),
    "a seal of its own": lambda kind, values, _: kind.model_validate(values, context=object()),
    "a copy of a seal": lambda kind, values, _: kind.model_validate(
        values, context=copy.copy(object())
    ),
    "model_construct": lambda kind, values, _: kind.model_construct(**values),
    "model_copy with an update": lambda _, values, made: made.model_copy(
        update={next(iter(values)): 0}
    ),
    "a deprecated copy with an update": lambda _, values, made: made.copy(
        update={next(iter(values)): 0}
    ),
}


@pytest.mark.parametrize("route", UNSEALED.values(), ids=UNSEALED.keys())
@pytest.mark.parametrize(("kind", "seal", "values", "check", "name", "file"), CASES, ids=IDS)
def test_a_sealed_class_is_built_no_other_way(
    route: Callable[[type[SealedModel], dict[str, Any], SealedModel], object],
    kind: type[SealedModel],
    seal: object,
    values: dict[str, Any],
    check: Callable[[object], bool],
    name: str,
    file: str,
) -> None:
    made = _built(kind, seal, values)
    with pytest.raises(TypeError):
        route(kind, values, made)


@pytest.mark.parametrize(("kind", "seal", "values", "check", "name", "file"), CASES, ids=IDS)
def test_the_seal_of_another_class_builds_nothing(
    kind: type[SealedModel],
    seal: object,
    values: dict[str, Any],
    check: Callable[[object], bool],
    name: str,
    file: str,
) -> None:
    for other_seal in (each[1] for each in CASES if each[0] is not kind):
        with pytest.raises(TypeError):
            kind.model_validate(values, context=other_seal)


@pytest.mark.parametrize(("kind", "seal", "values", "check", "name", "file"), CASES, ids=IDS)
def test_a_sealed_class_takes_no_subclass(
    kind: type[SealedModel],
    seal: object,
    values: dict[str, Any],
    check: Callable[[object], bool],
    name: str,
    file: str,
) -> None:
    with pytest.raises(TypeError, match="takes no subclass"):
        create_model("Mine", __base__=kind)
    with pytest.raises(TypeError, match="takes no subclass"):

        class Mine(kind):  # type: ignore[misc,valid-type]
            pass


@pytest.mark.parametrize(
    "same",
    [copy.copy, copy.deepcopy, lambda m: pickle.loads(pickle.dumps(m))],  # noqa: S301 (its own)
    ids=["copy.copy", "deepcopy", "pickle"],
)
@pytest.mark.parametrize(("kind", "seal", "values", "check", "name", "file"), CASES, ids=IDS)
def test_a_copy_reads_the_same_and_proves_nothing(
    same: Callable[[SealedModel], SealedModel],
    kind: type[SealedModel],
    seal: object,
    values: dict[str, Any],
    check: Callable[[object], bool],
    name: str,
    file: str,
) -> None:
    made = _built(kind, seal, values)
    copied = same(made)
    assert copied == made and copied is not made
    assert check(copied) is False and check(made) is True


@pytest.mark.parametrize(("kind", "seal", "values", "check", "name", "file"), CASES, ids=IDS)
def test_a_sealed_object_rewritten_in_place_proves_nothing(
    kind: type[SealedModel],
    seal: object,
    values: dict[str, Any],
    check: Callable[[object], bool],
    name: str,
    file: str,
) -> None:
    made = _built(kind, seal, values)
    field, value = next(iter(values.items()))
    made.__dict__[field] = value + 1 if isinstance(value, int) else "".join([str(value), "!"])
    assert check(made) is False


@pytest.mark.parametrize(("kind", "seal", "values", "check", "name", "file"), CASES, ids=IDS)
def test_a_collected_object_leaves_the_registry(
    kind: type[SealedModel],
    seal: object,
    values: dict[str, Any],
    check: Callable[[object], bool],
    name: str,
    file: str,
) -> None:
    made = _built(kind, seal, values)
    key, alive = id(made), weakref.ref(made)
    assert key in seal_module._SEALED
    del made
    gc.collect()
    assert alive() is None and key not in seal_module._SEALED


def _construct_lines(source: str, *, rel: str) -> list[int]:
    """The lines ARCH-CONSTRUCT reports in `source`, as the library's module `rel`."""
    arch = load_config(ROOT).arch
    checker = ModuleChecker(arch, layer=rel.split("/")[0], rel=rel, display=rel, source=source)
    checker.visit(ast.parse(source))
    return sorted(v.line for v in checker.violations if v.rule == "ARCH-CONSTRUCT")


@pytest.mark.parametrize(("kind", "seal", "values", "check", "name", "file"), CASES, ids=IDS)
def test_poe_arch_reports_the_class_and_its_seal_outside_their_modules(
    kind: type[SealedModel],
    seal: object,
    values: dict[str, Any],
    check: Callable[[object], bool],
    name: str,
    file: str,
) -> None:
    class_name = kind.__name__
    assert _construct_lines(f"{class_name}()\n", rel="agent/turn.py") == [1]
    assert _construct_lines(f"{class_name}.model_validate({{}})\n", rel="agent/turn.py") == [1]
    assert _construct_lines(f"seal = {name}\n", rel="agent/turn.py") == [1]
    assert _construct_lines(f"from x import {name} as S\n", rel="agent/turn.py") == [1]
    assert _construct_lines(f'name = "{name}"\n', rel="api/server.py") == [1]
    assert _construct_lines(f"{class_name}.model_validate({{}})\n", rel=file) == []
    assert _construct_lines(f"seal = {name}\n", rel=file) == []


def test_only_voice_builds_a_receipt_and_only_the_yes_rule_issues_a_confirmed_action() -> None:
    assert _construct_lines("ConfirmedAction.model_validate({})\n", rel="domain/guard.py") == [1]
    assert _construct_lines(
        "ConfirmedAction.model_validate({})\n", rel="voice/session/call.py"
    ) == [1]
    assert _construct_lines(
        "ReadBackReceipt.model_validate({})\n", rel="voice/session/call.py"
    ) == [1]
    assert _construct_lines("CompletedAction.model_validate({})\n", rel="agent/turn.py") == [1]
    assert _construct_lines("HeardWords(text='x')\n", rel="voice/session/call.py") == []
    assert _construct_lines("HeardWords(text='x')\n", rel="actions/runner.py") == [1]


def test_no_sealed_class_appears_among_the_public_names() -> None:
    from t2_agentic_voice.domain.ports import outbox as _outbox  # a port names none of them

    assert issubclass(_outbox.OutboxEntry, BaseModel)
    arch = load_config(ROOT).arch
    public = "\n".join(
        (ROOT / "packages/t2-agentic-voice/src" / f"{m.replace('.', '/')}.py").read_text(
            encoding="utf-8"
        )
        for m in arch.public
        if m != "t2_agentic_voice"
    )
    root = (ROOT / "packages/t2-agentic-voice/src/t2_agentic_voice/__init__.py").read_text(
        encoding="utf-8"
    )
    for name in ("HeardWords", "ReadBackReceipt", "ConfirmedAction", "CompletedAction"):
        assert name not in public and name not in root, name

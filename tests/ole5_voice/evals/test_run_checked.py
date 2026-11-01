"""A run scores only the variants the owner has checked, as `poe golden` accepts them (plan 002's
registration, "The independent check of each reference"): an unconfirmed variant, or a typed one
not yet confirmed in a later pass, is neither answered nor in the digest, and is counted as left
out, never named. And a run times its requests with a clock fine enough for latency."""

from __future__ import annotations

import inspect
import time
from datetime import UTC, datetime
from pathlib import Path

import pytest
from ole5_voice.evals import answerers
from ole5_voice.evals.models import Item, Variant
from ole5_voice.evals.run_parts import Choice, Parts, load_plan
from t2_agentic_voice import InvalidRequestError

from tests.ole5_voice.evals.test_run_parts import World, _parts, golden_set, make_world

WHEN = datetime(2026, 11, 2, 10, 0, tzinfo=UTC)


@pytest.fixture
def world(tmp_path: Path) -> World:
    return make_world(tmp_path)


def _with(item: Item, **changes: object) -> Item:
    """`item` with its variants changed: the same `changes` on each."""
    variants = [Variant.model_validate(v.model_dump() | changes) for v in item.variants]
    return Item.model_validate(item.model_dump() | {"variants": variants})


def _typed(passes: tuple[int, ...]) -> dict[str, object]:
    confirmations = [{"at": WHEN, "review_pass": p} for p in passes]
    return {"reference_source": "typed", "confirmations": confirmations}


def test_an_unchecked_variant_is_left_out_of_the_run_and_its_digest(world: World) -> None:
    both = world.item("a", takes=2)
    first, second = both.variants
    unchecked = second.model_dump() | {"confirmations": []}
    mixed = Item.model_validate(both.model_dump() | {"variants": [first, unchecked]})
    alone = Item.model_validate(both.model_dump() | {"variants": [first]})
    plan = load_plan(world.data, Choice("dev"), _parts(golden_set(mixed, world.item("b"))))
    assert [(t.item.id, t.variant.id) for t in plan.todo] == [("a", "a-v1"), ("b", "b-v1")]
    same = load_plan(world.data, Choice("dev"), _parts(golden_set(alone, world.item("b"))))
    assert plan.digest == same.digest  # the digest covers what the run scores, nothing more


def test_a_typed_reference_counts_only_once_confirmed_in_a_later_pass(world: World) -> None:
    waiting = _with(world.item("t", "a typed text"), **_typed(()))
    confirmed = _with(world.item("c", "another typed text"), **_typed((2,)))
    plan = load_plan(world.data, Choice("dev"), _parts(golden_set(waiting, confirmed)))
    assert [t.item.id for t in plan.todo] == ["c"]


def test_a_run_with_nothing_checked_is_refused_naming_no_variant(
    world: World, capsys: pytest.CaptureFixture[str]
) -> None:
    golden = golden_set(world.item("secret-a", confirmed=False), world.item("h"), held_out=("h",))
    with pytest.raises(InvalidRequestError, match="no variant the owner has checked") as refused:
        load_plan(world.data, Choice("dev"), _parts(golden))
    assert "poe golden" in refused.value.message and "secret" not in refused.value.message
    out = capsys.readouterr().out
    assert "unchecked_left_out" in out and "variants=1" in out and "secret" not in out


def test_a_held_out_runs_smoke_test_takes_a_checked_dev_variant(world: World) -> None:
    golden = golden_set(
        world.item("a", confirmed=False), world.item("b"), world.item("h"), held_out=("h",)
    )
    plan = load_plan(world.data, Choice("held-out"), _parts(golden))
    assert (plan.smoke.item.id, [t.item.id for t in plan.todo]) == ("b", ["h"])
    unchecked_dev = golden_set(world.item("a", confirmed=False), world.item("h"), held_out=("h",))
    with pytest.raises(InvalidRequestError, match="no dev variant for its smoke test"):
        load_plan(world.data, Choice("held-out"), _parts(unchecked_dev))


def test_requests_are_timed_with_a_monotonic_clock_finer_than_a_millisecond() -> None:
    """`time.monotonic` moves in 15.6 ms steps on Windows (GetTickCount64): a request's latency
    would be off by up to a step, coarser than the medians the registration compares."""
    default = inspect.signature(answerers.make_answerer).parameters["clock"].default
    assert Parts().clock is default is time.perf_counter
    info = time.get_clock_info("perf_counter")
    assert info.monotonic and info.resolution < 1e-3

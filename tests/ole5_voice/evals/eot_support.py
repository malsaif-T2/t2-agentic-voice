"""What the tests of `poe eot` and `poe eval-timing` share: made-up paused requests (each variant
with one turn end marked) and other items in a run's world (`run_support.World`), the parts a
run is built from, and a recorder of the history lines it appends."""

from __future__ import annotations

from pathlib import Path

from ole5_voice.evals.models import Confirmation, Device, Item, Language, Variant
from ole5_voice.evals.run_lines import AnyLine
from ole5_voice.evals.run_parts import Parts

from tests.ole5_voice.evals.fakes import FakeGoldenSet, FakeMatcher
from tests.ole5_voice.evals.run_support import World, golden_set
from tests.ole5_voice.evals.samples import WHEN


def paused(
    world: World,
    item_id: str,
    *,
    language: Language = "saudi",
    devices: tuple[Device, ...] = ("laptop",),
    end_ms: int = 1500,
    seconds: float = 2.0,
    kind: str = "paused_request",
) -> Item:
    """An item with one variant per device, each `seconds` long with its turn end marked at
    `end_ms` (none for another `kind`), confirmed by the owner's listen."""
    variants = tuple(
        Variant(
            id=f"{item_id}-{device}",
            segments=(world.clip(f"{item_id}-{device}", seconds),),
            device=device,
            session=f"{device}-1",
            reference="made-up words",
            reference_source="script",
            confirmations=(Confirmation(at=WHEN, review_pass=1),),
            turn_ends_ms=(end_ms,) if kind == "paused_request" else (),
        )
        for device in devices
    )
    return Item(
        id=item_id,
        source="script",
        kind=kind,
        language=language,
        text="made-up words",
        variants=variants,
    )


def parts_of(world: World, golden: FakeGoldenSet) -> Parts:
    """A run's parts in `world`, with `golden`'s loaders and a fake matcher."""
    return Parts(
        folder=world.top,
        git=world.git,
        load_items=golden.load_items,
        load_split=golden.load_split,
        load_matcher=lambda path: FakeMatcher(),
        now=lambda: WHEN,
    )


class Lines:
    """Stands in for `history.append_line`: keeps each line with the file it was for."""

    def __init__(self) -> None:
        self.appended: list[tuple[AnyLine, Path]] = []

    def __call__(self, line: AnyLine, history: Path) -> None:
        self.appended.append((line, history))


__all__ = ["Lines", "golden_set", "parts_of", "paused"]

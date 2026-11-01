"""The items, their TOML writer, and the two imports.

Plan 002's Track D builds them and replaces this file's stub tests.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from ole5_voice.evals import import_recordings, import_talkover
from ole5_voice.evals.items import load_items
from ole5_voice.evals.toml_write import dump_item

from tests.ole5_voice.evals import samples


def test_the_items_and_the_imports_are_stubs_until_track_d(tmp_path: Path) -> None:
    calls: list[Callable[[], object]] = [
        lambda: load_items(tmp_path),
        lambda: dump_item(samples.item()),
        lambda: import_talkover.main([]),
        lambda: import_recordings.main([]),
    ]
    for call in calls:
        with pytest.raises(NotImplementedError, match="Track D"):
            call()

"""The golden set's items: read from their TOML files under `evals/golden/`.

Built by plan 002's Track D; until then a stub.
"""

from __future__ import annotations

from pathlib import Path

from ole5_voice.evals.models import Item

_STUB = "items.py is built by plan 002's Track D"


def load_items(folder: Path) -> tuple[Item, ...]:
    """Every item under `folder`, one TOML file each, in the order of their IDs."""
    raise NotImplementedError(_STUB)

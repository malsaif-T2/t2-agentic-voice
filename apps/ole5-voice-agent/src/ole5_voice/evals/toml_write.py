"""Items written as TOML, in their fixed shape, with no TOML-writing package.

Built by plan 002's Track D; until then a stub.
"""

from __future__ import annotations

from ole5_voice.evals.models import Item

_STUB = "toml_write.py is built by plan 002's Track D"


def dump_item(item: Item) -> str:
    """The TOML text of `item`, which `tomllib` reads back as the same item."""
    raise NotImplementedError(_STUB)

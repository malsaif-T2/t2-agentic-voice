"""The strata: the items, their variants and the script's lines counted by each label, which
the committed set must hold as `strata.toml` registers them."""

from __future__ import annotations

from ole5_voice.evals.items import count_strata
from ole5_voice.evals.models import Item, Variant
from ole5_voice.evals.takes import Script

from tests.ole5_voice.evals import samples


def test_the_strata_count_items_variants_and_script_lines() -> None:
    item = Item.model_validate(
        samples.item().model_dump()
        | {
            "variants": (
                samples.variant("v1"),
                Variant.model_validate(samples.variant("v2").model_dump() | {"tags": ("duck",)}),
            )
        }
    )
    script = Script.model_validate(
        {"lines": [{"id": "n1", "kind": "silence", "language": "none", "seconds": 4}]}
    )
    strata = count_strata([item], script)
    assert strata.items.model_dump() == {
        "total": 1,
        "source": {"script": 1},
        "language": {"english": 1},
        "kind": {"stop_word": 1},
        "device": {},
        "tag": {},
    }
    assert (strata.variants.total, strata.variants.device, strata.variants.tag) == (
        2,
        {"laptop": 2},
        {"duck": 1},
    )
    assert (strata.script.total, strata.script.kind) == (1, {"silence": 1})

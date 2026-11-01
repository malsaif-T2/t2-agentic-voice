"""`poe golden`, and the independent check it accepts a variant on: the owner's confirmation
after a listen, the typing of a reference never counting as its own check.

Plan 002's Track D builds `golden.py`; its stub test stays until it is built.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from ole5_voice.evals import golden
from ole5_voice.evals.items import GoldenSetError, accepted, reviewed, unchecked
from ole5_voice.evals.models import Confirmation, Item, Variant
from ole5_voice.evals.takes import Review

from tests.ole5_voice.evals import samples

WHEN = samples.WHEN


def test_golden_is_a_stub_until_track_d() -> None:
    with pytest.raises(NotImplementedError, match="Track D"):
        golden.main([])


def _confirmed(variant: Variant, *passes: int) -> Variant:
    confirmations = [{"at": WHEN, "review_pass": p} for p in passes]
    return Variant.model_validate(variant.model_dump() | {"confirmations": confirmations})


def _typed(variant: Variant) -> Variant:
    return Variant.model_validate(variant.model_dump() | {"reference_source": "typed"})


def test_a_variant_is_checked_once_the_owner_confirmed_it() -> None:
    plain = samples.variant()
    assert unchecked(plain) == "not yet confirmed by the owner's listen"
    assert unchecked(_confirmed(plain, 1)) is None
    # A typed reference with no second confirmation is left out (the plan's Track D, Tests).
    assert "waiting on its second confirmation" in (unchecked(_typed(plain)) or "")
    assert unchecked(_confirmed(_typed(plain), 2)) is None


def test_only_checked_variants_are_accepted() -> None:
    item = samples.item()
    both = Item.model_validate(
        item.model_dump()
        | {"variants": (_confirmed(samples.variant("v1"), 1), samples.variant("v2"))}
    )
    assert [v.id for i in accepted([both]) for v in i.variants] == ["v1"]
    assert accepted([item]) == ()


def _review(review_pass: int, verdict: str = "confirmed", text: str = "") -> Review:
    return Review.model_validate(
        {
            "take": "t1",
            "review_pass": review_pass,
            "at": WHEN + timedelta(days=review_pass),
            "verdict": verdict,
            "text": text,
        }
    )


def test_reviews_confirm_the_reference_or_replace_it_with_typed_words() -> None:
    assert reviewed("stop now", "script", []) == ("stop now", "script", ())
    reference, source, confirmations = reviewed("stop now", "script", [_review(2), _review(1)])
    assert (reference, source, [c.review_pass for c in confirmations]) == (
        "stop now",
        "script",
        [1, 2],
    )
    # Typed in pass 1 and confirmed in pass 2: the typed words, confirmed once after.
    typed = reviewed("stop now", "script", [_review(1, "typed", " stop  then "), _review(2)])
    assert (typed[0], typed[1], [c.review_pass for c in typed[2]]) == ("stop then", "typed", [2])
    # A confirmation of the script's words does not confirm words typed later.
    later = reviewed("stop now", "script", [_review(1), _review(2, "typed", "stop then")])
    assert later == ("stop then", "typed", ())
    assert reviewed("", "none", [_review(1)])[1:] == (
        "none",
        (Confirmation(at=WHEN + timedelta(days=1), review_pass=1),),
    )


def test_reviews_in_one_pass_twice_or_typed_empty_are_refused() -> None:
    with pytest.raises(GoldenSetError, match="one review in each pass"):
        reviewed("x", "script", [_review(1), _review(1, "typed", "y")])
    with pytest.raises(GoldenSetError, match="review 1 of t1 is empty"):
        reviewed("x", "script", [_review(1, "typed", "  ")])

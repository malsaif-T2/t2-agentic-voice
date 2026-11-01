"""The items, their TOML writer, and the two imports.

Plan 002's Track D builds them; the imports' stub test stays until they are built.
"""

from __future__ import annotations

import re
import tomllib
from collections.abc import Callable
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest
from ole5_voice.evals import import_recordings, import_talkover
from ole5_voice.evals.items import (
    GoldenSetError,
    accepted,
    count_strata,
    load_items,
    load_manifests,
    load_terms,
    read_json,
    reviewed,
    unchecked,
)
from ole5_voice.evals.models import AudioRef, Confirmation, Item, Manifest, Variant
from ole5_voice.evals.takes import Review, Script
from ole5_voice.evals.toml_write import dump_item

from tests.ole5_voice.evals import samples

SHA = samples.SHA
WHEN = samples.WHEN
TRICKY = 'a "quote", a \\ slash, a\nbreak, a\ttab, \x00\x1b\x7f, # not a comment = «تمام» 👍'


def _rich_item() -> Item:
    segments = (
        AudioRef(root="talkover", path="s06__seg1.wav", sha256=SHA),
        AudioRef(root="talkover", path="s06__seg2.wav", sha256="f" * 64),
    )
    confirmations = (
        Confirmation(at=WHEN, review_pass=1),
        Confirmation(at=datetime(2026, 11, 4, 8, 30, 15, 123456), review_pass=2),
        Confirmation(at=datetime(2026, 11, 5, tzinfo=timezone(timedelta(hours=3))), review_pass=3),
    )
    first = Variant(
        id="s06__duck",
        segments=segments,
        device="laptop",
        session="talkover-2026-10-27",
        reference=TRICKY,
        reference_source="typed",
        confirmations=confirmations,
        turn_ends_ms=(1200, 4800),
        tags=("duck", "over-assistant"),
    )
    second = samples.variant("s06__pause", reference="")
    return Item(
        id="s06",
        source="talkover",
        kind="request",
        language="saudi",
        text="عندي مشكلة في… يعني",
        alternatives=("one", TRICKY),
        terms=("Outlook", "PDF"),
        want="send",
        variants=(first, second),
    )


def test_an_item_round_trips_through_its_toml() -> None:
    for item in (samples.item(), _rich_item()):
        text = dump_item(item)
        assert Item.model_validate(tomllib.loads(text)) == item
        assert "\r" not in text and text.endswith("\n")


def test_a_missing_want_is_left_out_as_toml_has_no_null() -> None:
    text = dump_item(samples.item())
    assert "want" not in text
    assert Item.model_validate(tomllib.loads(text)).want is None


def test_comments_go_at_the_top_and_are_dropped_when_read() -> None:
    text = dump_item(samples.item(), comments=["DRAFT: waiting on the owner (Q7)", ""])
    assert text.startswith("# DRAFT: waiting on the owner (Q7)\n#\nid = ")
    assert Item.model_validate(tomllib.loads(text)) == samples.item()
    for broken in ("two\nlines", "a\rreturn", "a\x00zero"):
        with pytest.raises(ValueError, match="one line"):
            dump_item(samples.item(), comments=[broken])


def _write(folder: Path, item: Item, name: str | None = None) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{name or item.id}.toml").write_text(dump_item(item), encoding="utf-8")


def test_the_items_are_read_in_the_order_of_their_ids(tmp_path: Path) -> None:
    for name in ("i2", "i10", "i1"):
        item = samples.item(name)
        _write(
            tmp_path,
            Item.model_validate(item.model_dump() | {"variants": (samples.variant(f"v{name}"),)}),
        )
    (tmp_path / "notes.txt").write_text("not an item", encoding="utf-8")
    assert [item.id for item in load_items(tmp_path)] == ["i1", "i10", "i2"]


def test_an_item_file_named_for_another_item_is_refused(tmp_path: Path) -> None:
    _write(tmp_path, samples.item("i1"), name="i2")
    with pytest.raises(GoldenSetError, match=re.escape("i2.toml: holds the item 'i1'")):
        load_items(tmp_path)


def test_two_variants_with_one_id_are_refused(tmp_path: Path) -> None:
    _write(tmp_path, samples.item("i1"))
    _write(tmp_path, samples.item("i2"))  # both hold the variant v1
    with pytest.raises(GoldenSetError, match="same ID in two places: v1"):
        load_items(tmp_path)


def test_a_broken_item_file_is_refused_by_name_without_echoing_it(tmp_path: Path) -> None:
    secret = "made-up-secret-value"
    cases = {
        "a.toml": f'id = "{secret}\n',  # not TOML
        "b.toml": dump_item(samples.item("b")).replace('kind = "stop_word"', f'kind = "{secret}!"'),
        "c.toml": dump_item(samples.item("c")) + f'colour = "{secret}"\n',  # a field no item has
    }
    for name, text in cases.items():
        folder = tmp_path / name
        folder.mkdir()
        (folder / name).write_text(text, encoding="utf-8")
        with pytest.raises(GoldenSetError, match=name) as refused:
            load_items(folder)
        assert secret not in str(refused.value)
    with pytest.raises(GoldenSetError, match="no such folder"):
        load_items(tmp_path / "absent")


def test_a_manifest_file_named_twice_below_one_root_is_refused(tmp_path: Path) -> None:
    file = {"path": "a.wav", "sha256": SHA, "seconds": 1.0, "sample_rate": 16000}
    one = {"root": "owner", "files": [file | {"device": "laptop", "session": "s1"}]}
    for name in ("owner-s1.json", "owner-s2.json"):
        (tmp_path / name).write_text(
            Manifest.model_validate(one).model_dump_json(), encoding="utf-8"
        )
    with pytest.raises(GoldenSetError, match=re.escape("two manifests: owner:a.wav")):
        load_manifests(tmp_path)
    (tmp_path / "owner-s2.json").unlink()
    assert [m.root for m in load_manifests(tmp_path)] == ["owner"]
    (tmp_path / "owner-s1.json").write_text("{", encoding="utf-8")
    with pytest.raises(GoldenSetError, match=re.escape("owner-s1.json")):
        read_json(tmp_path / "owner-s1.json", Manifest)


def test_the_terms_are_each_given_once_with_no_space_around(tmp_path: Path) -> None:
    path = tmp_path / "terms.toml"
    path.write_text('terms = ["Outlook", "PDF"]\n', encoding="utf-8")
    assert load_terms(path) == ("Outlook", "PDF")
    for broken in (
        'terms = ["PDF", "PDF"]\n',
        'terms = [" PDF"]\n',
        'terms = [""]\n',
        "terms = []\n",
    ):
        path.write_text(broken, encoding="utf-8")
        with pytest.raises(GoldenSetError, match=re.escape("terms.toml")):
            load_terms(path)


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


def test_the_imports_are_stubs_until_track_d() -> None:
    calls: list[Callable[[], object]] = [
        lambda: import_talkover.main([]),
        lambda: import_recordings.main([]),
    ]
    for call in calls:
        with pytest.raises(NotImplementedError, match="Track D"):
            call()


def test_a_confirmation_keeps_its_time_zone() -> None:
    item = _rich_item()
    again = Item.model_validate(tomllib.loads(dump_item(item)))
    times = [c.at for c in again.variants[0].confirmations]
    assert times[0].tzinfo == UTC or times[0].utcoffset() == timedelta(0)
    assert times[1].tzinfo is None and times[1].microsecond == 123456
    assert times[2].utcoffset() == timedelta(hours=3)

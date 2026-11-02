"""The items and their TOML writer, the manifests, the terms, and which variants are checked.
The two imports have their own tests: `test_import_talkover.py` and `test_import_recordings.py`."""

from __future__ import annotations

import re
import tomllib
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest
from ole5_voice.evals.items import (
    GoldenSetError,
    dump_manifest,
    holds_term,
    load_items,
    load_manifests,
    load_terms,
    read_json,
    references,
    unchecked,
)
from ole5_voice.evals.models import AudioRef, Confirmation, Item, Manifest, Variant
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


def test_a_confirmation_keeps_its_time_zone() -> None:
    item = _rich_item()
    again = Item.model_validate(tomllib.loads(dump_item(item)))
    times = [c.at for c in again.variants[0].confirmations]
    assert times[0].tzinfo == UTC or times[0].utcoffset() == timedelta(0)
    assert times[1].tzinfo is None and times[1].microsecond == 123456
    assert times[2].utcoffset() == timedelta(hours=3)


def _confirmed(variant: Variant, *passes: int) -> Variant:
    confirmations = [{"at": WHEN, "review_pass": p} for p in passes]
    return Variant.model_validate(variant.model_dump() | {"confirmations": confirmations})


def _typed(variant: Variant) -> Variant:
    return Variant.model_validate(variant.model_dump() | {"reference_source": "typed"})


def test_a_variant_is_checked_once_the_owner_confirmed_it() -> None:
    plain = samples.variant()
    assert unchecked(plain) == "not yet confirmed by the owner's listen"
    assert unchecked(_confirmed(plain, 1)) is None
    # A typed reference with no second confirmation is left out (Q9: a check in a later pass).
    assert "waiting on its second confirmation" in (unchecked(_typed(plain)) or "")
    assert unchecked(_confirmed(_typed(plain), 2)) is None


def test_a_term_is_held_as_a_whole_word_as_the_product_writes_it() -> None:
    """The talk-over import picks an item's terms by it, and `poe golden` checks them."""
    assert holds_term("Open it in Outlook.", "Outlook") and holds_term("PDF", "PDF")
    for text in ("outlook", "Outlooks", "MyOutlook", "Out look"):
        assert not holds_term(text, "Outlook"), text
    assert holds_term("in C++.", "C++") and not holds_term("in C++x", "C++")


def test_what_counts_as_right_is_the_reference_then_the_items_alternatives() -> None:
    item = Item.model_validate(samples.item().model_dump() | {"alternatives": ("stop it",)})
    assert references(item, item.variants[0]) == ("stop now", "stop it")


def test_a_manifest_is_written_as_its_committed_text() -> None:
    file = {"path": "a.wav", "sha256": SHA, "seconds": 1.5, "sample_rate": 16000}
    one = {"root": "owner", "files": [file | {"device": "laptop", "session": "s1"}]}
    text = dump_manifest(Manifest.model_validate(one))
    assert text.startswith('{\n  "root": "owner",') and text.endswith("}\n")
    assert Manifest.model_validate_json(text) == Manifest.model_validate(one)

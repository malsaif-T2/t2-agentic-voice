"""The items, their TOML writer, and the two imports: the talk-over's from the lab's records, the
new recordings' from the recorder's files, neither reading any audio (the tests give made-up
facts in place of the WAV files)."""

from __future__ import annotations

import json
import re
import tomllib
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
from ole5_voice.evals import import_talkover
from ole5_voice.evals.audio import AudioFormatError, Wav, sha256_of
from ole5_voice.evals.items import (
    GoldenSetError,
    accepted,
    load_items,
    load_manifests,
    load_terms,
    read_json,
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


# The talk-over import, on a made-up lab: its records as the lab writes them (with fields the
# import ignores), and a fake reader in place of the WAV files, so no test reads audio.
# phrase, lang, kind, want, text, each segment's over_bot, condition, device
LAB = [
    (
        "s06_pause_error",
        "ar",
        "sentence",
        "send",
        "عندي مشكلة… يعني",
        (True, False),
        "duck",
        "speakers",
    ),
    ("s06_pause_error", "ar", "sentence", "send", "عندي مشكلة… يعني", (False,), "pause", "headset"),
    ("u01_signature", "ar", "unscripted", "send", " كيف  أضيف توقيع ", (True,), "duck", "speakers"),
    (
        "e03_signature",
        "en",
        "sentence",
        "send",
        "How do I change it in Outlook?",
        (True,),
        "duck",
        "speakers",
    ),
    ("r03_repeat", "ar", "request", "repeat", "ممكن تعيد؟", (True,), "duck", "speakers"),
    ("r01_muwazzaf", "ar", "request", "send", "أبغى موظف", (True,), "duck", "speakers"),
    ("b01_tamam", "ar", "backchannel", "listen", "تمام", (True,), "duck", "speakers"),
    ("k01_wagif", "ar", "command", "halt", "وقف", (True,), "duck", "speakers"),
    ("y04_naam", "ar", "confirm", "submit", "نعم", (True,), "duck", "speakers"),
    ("y04_naam", "ar", "confirm", "submit", "نعم", (), "pause", "speakers"),  # no segment
]


def _lab() -> tuple[dict[str, Any], dict[str, Any]]:
    refs: dict[str, Any] = {}
    takes: dict[str, Any] = {}
    for n, (phrase, lang, kind, want, text, over, condition, device) in enumerate(LAB):
        take = f"{phrase}__{condition}__{device}__{100000 + n}"
        common = {"phrase_id": phrase, "take": take, "text": text, "lang": lang, "kind": kind}
        common |= {"want": want, "condition": condition, "device": device}
        names = [f"{take}__seg{i}.wav" for i in range(1, len(over) + 1)]
        for i, (name, over_bot) in enumerate(zip(names, over, strict=True), start=1):
            refs[name] = common | {"segment_index": i, "segments_in_take": len(names)}
            refs[name] |= {"over_bot": over_bot, "lab_heard": {"text": "ignored"}}
        takes[take] = common | {"recorded_at": "2026-10-27T18:18:25", "segments": names, "meta": {}}
    return refs, takes


def _save(folder: Path, refs: dict[str, Any], takes: dict[str, Any]) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    for name, data in (("refs.json", refs), ("takes.json", takes)):
        (folder / name).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return folder


def _describe(path: Path) -> Wav:
    """Made-up facts for a segment, from its name: no file is read."""
    return Wav(pcm16=b"\x00\x00" * 8000, sample_rate=16000, sha256=sha256_of(path.name.encode()))


def test_the_talk_over_import_makes_one_item_a_phrase(tmp_path: Path) -> None:
    lab = _save(tmp_path / "lab", *_lab())
    items, manifest, left_out = import_talkover.build(
        lab, terms=["Outlook", "PDF"], describe=_describe
    )
    found = {item.id: item for item in items}
    assert [(i.id, i.kind, i.language) for i in items] == [
        ("b01_tamam", "listening_sound", "saudi"),
        ("e03_signature", "request", "english"),
        ("k01_wagif", "stop_word", "saudi"),
        ("r01_muwazzaf", "short_request", "saudi"),
        ("r03_repeat", "repeat_request", "saudi"),
        ("s06_pause_error", "request", "saudi"),
        ("u01_signature", "request", "saudi"),
        ("y04_naam", "confirmation", "msa"),
    ]
    split, headset = found["s06_pause_error"].variants
    assert [s.path for s in split.segments] == [f"{split.id}__seg1.wav", f"{split.id}__seg2.wav"]
    assert split.tags == ("duck", "over-assistant", "playback-speakers")
    assert headset.tags == ("pause", "playback-headset")
    sessions = {(v.device, v.session) for i in items for v in i.variants}
    assert sessions == {("laptop", "talkover-2026-10-27")}
    typed = found["u01_signature"]
    assert (typed.text, typed.variants[0].reference) == ("", "كيف أضيف توقيع")
    assert typed.variants[0].reference_source == "typed"
    assert (found["e03_signature"].terms, found["k01_wagif"].want) == (("Outlook",), "halt")
    assert len(manifest.files) == 10 and manifest.consent is None
    assert [f.path for f in manifest.files] == sorted(f.path for f in manifest.files)
    assert {(f.seconds, f.sample_rate) for f in manifest.files} == {(0.5, 16000)}
    assert split.segments[0].sha256 == sha256_of(split.segments[0].path.encode())
    assert left_out == ["y04_naam__pause__speakers__100009"]


def test_the_owners_reviews_of_a_talk_over_variant_become_its_confirmations(
    tmp_path: Path,
) -> None:
    lab = _save(tmp_path / "lab", *_lab())
    take = "u01_signature__duck__speakers__100002"
    reviews = tmp_path / "out" / "talkover-2026-10-27"
    reviews.mkdir(parents=True)
    for n, verdict, text in ((1, "typed", "كيف أضيف التوقيع"), (2, "confirmed", "")):
        review = {"take": take, "review_pass": n, "at": WHEN.isoformat(), "verdict": verdict}
        path = reviews / f"{take}.review-{n}.json"
        path.write_text(json.dumps(review | {"text": text}), encoding="utf-8")
    items, _, _ = import_talkover.build(lab, terms=[], describe=_describe, reviews=tmp_path / "out")
    variant = next(i for i in items if i.id == "u01_signature").variants[0]
    assert variant.reference == "كيف أضيف التوقيع"
    assert [c.review_pass for c in variant.confirmations] == [2]


def _broken(refs: dict[str, Any], takes: dict[str, Any], case: str) -> None:
    first = next(iter(refs))
    take = refs[first]["take"]
    if case == "text":
        refs[first]["text"] = "another"
    elif case == "index":
        refs[first]["segment_index"] = 2
    elif case == "extra":
        refs["made-up__seg1.wav"] = refs[first]
    elif case == "phrases":  # one phrase's two takes, each consistent, with two texts
        for data in (*refs.values(), *takes.values()):
            if data["take"].startswith("s06_pause_error__pause"):
                data["text"] = "another"
    elif case == "key":
        takes["another_take"] = takes.pop(take)
    elif case == "phrase":  # an Arabic phrase with no proposed language
        for data in (*refs.values(), *takes.values()):
            if data["phrase_id"] == "b01_tamam":
                data["phrase_id"] = "z99_unknown"
    else:  # a segment in a folder below the lab's
        takes[take]["segments"][0] = f"sub/{first}"
        refs[f"sub/{first}"] = refs.pop(first)


@pytest.mark.parametrize(
    ("case", "problem"),
    [
        ("text", "disagree on the segment"),
        ("index", "disagree on the segment"),
        ("extra", "name different segment files"),
        ("phrases", "the takes of s06_pause_error disagree on their phrase"),
        ("key", "under another name"),
        ("phrase", "no language is given for the Arabic phrase z99_unknown"),
        ("folder", "disagree on the segment sub/"),
    ],
)
def test_a_lab_whose_records_disagree_is_refused(tmp_path: Path, case: str, problem: str) -> None:
    refs, takes = _lab()
    _broken(refs, takes, case)
    with pytest.raises(GoldenSetError, match=re.escape(problem)):
        import_talkover.build(_save(tmp_path / "lab", refs, takes), terms=[], describe=_describe)


def test_a_segment_that_is_not_the_golden_sets_audio_is_refused(tmp_path: Path) -> None:
    lab = _save(tmp_path / "lab", *_lab())

    def refuse(path: Path) -> Wav:
        raise AudioFormatError("44100 Hz, 2 channel(s), 16-bit")

    with pytest.raises(GoldenSetError, match=re.escape("seg1.wav: 44100 Hz")):
        import_talkover.build(lab, terms=[], describe=refuse)
    (lab / "refs.json").write_text("{", encoding="utf-8")
    with pytest.raises(GoldenSetError, match=re.escape("refs.json")):
        import_talkover.build(lab, terms=[], describe=_describe)


def test_the_talk_over_command_writes_only_the_items_and_manifest_it_owns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lab = _save(tmp_path / "lab", *_lab())
    evals = tmp_path / "evals"
    evals.mkdir()
    (evals / "terms.toml").write_text('terms = ["Outlook"]\n', encoding="utf-8")
    monkeypatch.setattr(import_talkover, "read_wav", _describe)
    whole, _, _ = import_talkover.build(lab, terms=[], describe=_describe)
    gone = {i.id: i for i in whole}["s06_pause_error"].variants[1].id  # the real ones: not here
    monkeypatch.setattr(import_talkover, "LEFT_OUT", {gone: "cut off at its start"})
    assert import_talkover.main(["--lab", str(lab), "--evals", str(evals)]) == 0
    assert len(load_items(evals / "golden")) == 8
    assert gone not in {v.id for i in load_items(evals / "golden") for v in i.variants}
    assert len(load_manifests(evals / "manifests")[0].files) == 9  # its file left out with it
    with pytest.raises(GoldenSetError, match="no take of the lab is named t9_gone"):
        import_talkover.build(lab, terms=[], describe=_describe, left_out={"t9_gone": "why"})
    assert [m.root for m in load_manifests(evals / "manifests")] == ["talkover"]
    arabic = (evals / "golden" / "b01_tamam.toml").read_text(encoding="utf-8")
    english = (evals / "golden" / "e03_signature.toml").read_text(encoding="utf-8")
    assert arabic.startswith("# Written by") and english.startswith("# Written by")
    assert "DRAFT" not in arabic + english  # every dialect is the owner's ruling (Q7)
    assert sorted(p.name for p in evals.iterdir()) == ["golden", "manifests", "terms.toml"]
    (evals / "terms.toml").unlink()
    assert import_talkover.main(["--lab", str(lab), "--evals", str(evals)]) == 1

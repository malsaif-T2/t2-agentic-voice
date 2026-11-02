"""The import of the talk-over segments as items, from the lab's records, on a made-up lab: its
records as the lab writes them (with fields the import ignores), and a fake reader in place of
the WAV files, so no test reads audio."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest
from ole5_voice.evals import import_talkover
from ole5_voice.evals.audio import AudioFormatError, Wav, sha256_of
from ole5_voice.evals.items import GoldenSetError, load_items, load_manifests

from tests.ole5_voice.evals import samples

WHEN = samples.WHEN

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


@pytest.mark.parametrize("name", ["refs.json", "takes.json"])
def test_a_lab_record_that_does_not_fit_is_refused_without_echoing_it(
    tmp_path: Path, name: str
) -> None:
    """A lab record's text is a transcript: the refusal names the file and the field, never
    the record, and no exception chain leads to it."""
    refs, takes = _lab()
    planted = "SECRET-1"  # short, and first in its record, so even a shortened echo shows it
    records = refs if name == "refs.json" else takes
    key = next(iter(records))
    rest = {f: v for f, v in records[key].items() if f not in ("text", "want")}
    records[key] = {"text": planted} | rest
    with pytest.raises(GoldenSetError, match=re.escape(f"{name}: ")) as refused:
        import_talkover.build(_save(tmp_path / "lab", refs, takes), terms=[], describe=_describe)
    assert planted not in str(refused.value) and "want" in str(refused.value)
    assert refused.value.__context__ is None and refused.value.__cause__ is None

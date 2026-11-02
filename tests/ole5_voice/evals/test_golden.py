"""`poe golden`: every item validated against the files of `evals/`, the variants the owner has
not yet checked left out and listed, the expected answers frozen, and, with `--audio`, every
file's hash and format checked. The tests build a small set in a temporary folder and read
audio through a fake reader, so no test reads audio."""

from __future__ import annotations

import json
import re
import shutil
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import pytest
from ole5_voice.evals import golden
from ole5_voice.evals.audio import AudioFormatError, Wav
from ole5_voice.evals.import_talkover import LANGUAGE, LEFT_OUT
from ole5_voice.evals.items import EVALS, Counts, count_strata, load_items
from ole5_voice.evals.models import Item, Manifest, Variant
from ole5_voice.evals.split import split_items
from ole5_voice.evals.takes import Script, load_script
from ole5_voice.evals.toml_write import dump_item

from tests.ole5_voice.evals import samples
from tests.ole5_voice.evals.fakes import FakeSpellingCheck
from tests.ole5_voice.evals.recorder_support import link_folder

SHA, WHEN = samples.SHA, samples.WHEN
CONSENT = {"speaker": "the owner", "agreed": True, "on": "2026-11-02", "words": "I agree."}
SCRIPT = {
    "listening_sounds": ["mm-hmm"],
    "lines": [
        {"id": "n01", "kind": "listening_sound", "language": "english", "say": ["mm-hmm"]},
        {"id": "n02", "kind": "silence", "language": "none", "seconds": 4},
    ],
}


def _variant(name: str, root: str, reference: str, **changes: Any) -> Variant:
    base = {
        "id": name,
        "segments": [{"root": root, "path": f"{name}.wav", "sha256": SHA}],
        "device": "laptop",
        "session": "s1",
        "reference": reference,
        "reference_source": "script",
        "confirmations": [{"at": WHEN, "review_pass": 1}],
    }
    return Variant.model_validate(base | changes)


def _items() -> list[Item]:
    """A talk-over item of two variants, one confirmed; one typed by the owner, confirmed and
    not; and a new recording's item, confirmed."""
    said = "عندي مشكلة في Outlook"
    talkover = {"source": "talkover", "kind": "request", "language": "saudi", "want": "send"}
    first = [
        _variant("t01-a", "talkover", said),
        _variant("t01-b", "talkover", said, confirmations=[]),
    ]
    typed = {"reference_source": "typed"}
    second = [_variant("t02-a", "talkover", "كيف أضيف", **typed)]
    second.append(_variant("t02-b", "talkover", "كيف", confirmations=[], **typed))
    one = {
        "id": "t01",
        "text": said,
        "terms": ["Outlook"],
        "alternatives": ["عندي مشكله في Outlook"],
    }
    script = {"id": "n01", "source": "script", "kind": "listening_sound", "language": "english"}
    return [
        Item.model_validate(talkover | one | {"variants": first}),
        Item.model_validate(talkover | {"id": "t02", "text": "", "variants": second}),
        Item.model_validate(
            script | {"text": "mm-hmm", "variants": [_variant("n01-a", "owner", "mm-hmm")]}
        ),
    ]


def _toml(counts: Counts, part: str) -> list[str]:
    lines = [f"[{part}]", f"total = {counts.total}"]
    for label in ("source", "language", "kind", "device", "tag"):
        lines += [f"[{part}.{label}]"] + [f'"{k}" = {v}' for k, v in getattr(counts, label).items()]
    return lines


def _evals(folder: Path, items: list[Item]) -> Path:
    """A valid set's files: the items, their manifests, the guide, the terms, the script, and a
    split and strata made from them."""
    (folder / "golden").mkdir(parents=True)
    (folder / "manifests").mkdir()
    for item in items:
        (folder / "golden" / f"{item.id}.toml").write_text(dump_item(item), encoding="utf-8")
    for root in ("talkover", "owner"):
        files = [
            {"path": s.path, "sha256": s.sha256, "seconds": 1.0, "sample_rate": 16000}
            | {"device": v.device, "session": v.session}
            for i in items
            for v in i.variants
            for s in v.segments
            if s.root == root
        ]
        manifest = {"root": root, "files": files} | (
            {"consent": CONSENT} if root == "owner" else {}
        )
        (folder / "manifests" / f"{root}.json").write_text(json.dumps(manifest), encoding="utf-8")
    shutil.copy(EVALS / "spelling.toml", folder / "spelling.toml")
    (folder / "terms.toml").write_text('terms = ["Outlook"]\n', encoding="utf-8")
    (folder / "script.toml").write_text(_script_toml(SCRIPT), encoding="utf-8")
    split = {"salt": "made-up", "items": split_items(items, "made-up")}
    (folder / "split.json").write_text(json.dumps(split), encoding="utf-8")
    strata = count_strata(items, Script.model_validate(SCRIPT))
    lines = [
        line
        for part in ("items", "variants", "script")
        for line in _toml(getattr(strata, part), part)
    ]
    (folder / "strata.toml").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return folder


def _script_toml(script: dict[str, Any]) -> str:
    lines = [f"listening_sounds = {json.dumps(script['listening_sounds'], ensure_ascii=False)}"]
    for line in script["lines"]:
        lines.append("[[lines]]")
        lines += [f"{k} = {json.dumps(v, ensure_ascii=False)}" for k, v in line.items()]
    return "\n".join(lines) + "\n"


def _check(evals: Path, **options: Any) -> golden.Report:
    return golden.validate(evals, check=FakeSpellingCheck(), **options)


def test_a_valid_set_freezes_its_accepted_variants_and_lists_the_rest(tmp_path: Path) -> None:
    report = _check(_evals(tmp_path, _items()))
    assert report.problems == []
    typed = "typed by the owner, waiting on its second confirmation in a later review pass"
    unheard = "not yet confirmed by the owner's listen"
    assert report.left_out == [("t01", "t01-b", unheard), ("t02", "t02-b", typed)]
    frozen = json.loads(report.frozen)
    assert frozen["accepted"] == {"items": 3, "variants": 3}
    first = frozen["items"][1]
    assert (first["id"], first["want"], first["terms"]) == ("t01", "send", ["Outlook"])
    expected = ["عندي مشكلة في Outlook", "عندي مشكله في Outlook"]
    assert first["variants"] == [{"id": "t01-a", "device": "laptop", "expected": expected}]
    assert {item["split"] for item in frozen["items"]} <= {"dev", "held-out"}
    assert frozen["left_out"][1] == {"item": "t02", "variant": "t02-b", "why": typed}


def _change(
    items: list[Item], item_id: str, variant: int | None = None, **changes: Any
) -> list[Item]:
    def changed(item: Item) -> Item:
        if item.id != item_id:
            return item
        if variant is None:
            return Item.model_validate(item.model_dump() | changes)
        variants = list(item.variants)
        variants[variant] = Variant.model_validate(variants[variant].model_dump() | changes)
        return Item.model_validate(item.model_dump() | {"variants": variants})

    return [changed(item) for item in items]


CASES: dict[str, tuple[Callable[[list[Item]], list[Item]], str]] = {
    "script text": (
        lambda i: _change(i, "t01", 0, reference="عندي مشكلة"),
        "t01/t01-a: its reference is not its item's scripted text",
    ),
    "empty": (
        lambda i: _change(i, "t01", 0, reference=""),
        "t01/t01-a: an empty reference is exactly one with no speech",
    ),
    "no speech": (
        lambda i: _change(i, "n01", 0, reference_source="none"),
        "n01/n01-a: an empty reference is exactly one with no speech",
    ),
    "language": (
        lambda i: _change(i, "t02", None, language="none"),
        "t02/t02-a: an item of no language is exactly one with no speech",
    ),
    "line": (lambda i: _change(i, "n01", None, id="n03"), "n03: the script has no line of this ID"),
    "line kind": (
        lambda i: _change(i, "n01", None, language="mixed"),
        "n01: its kind, language, text or terms are not its line's",
    ),
    "sound": (
        lambda i: _change(i, "t02", None, kind="listening_sound"),
        "t02/t02-a: a listening sound outside the script's list (listening-sounds)",
    ),
    "term": (
        lambda i: _change(i, "t02", None, terms=["PDF"]),
        "t02: the term PDF is not in terms.toml or not in its text",
    ),
    "spelling": (
        lambda i: _change(i, "t02", 0, reference="ما يفتح اوتلوك"),
        "t02/t02-a: holds 'اوتلوك', which the spelling guide's product-term-outlook rules out: "
        "write Outlook",
    ),
}


@pytest.mark.parametrize("case", sorted(CASES))
def test_an_item_that_breaks_a_rule_fails_the_set(tmp_path: Path, case: str) -> None:
    change, problem = CASES[case]
    evals = _evals(tmp_path, _items())
    for item in change(_items()):
        (evals / "golden" / f"{item.id}.toml").write_text(dump_item(item), encoding="utf-8")
    if case == "line":
        (evals / "golden" / "n01.toml").unlink()
    assert problem in _check(evals).problems


def _manifest(evals: Path, root: str, change: Callable[[dict[str, Any]], None]) -> None:
    path = evals / "manifests" / f"{root}.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    change(manifest)
    path.write_text(json.dumps(manifest), encoding="utf-8")


def test_segments_and_manifests_that_disagree_fail_the_set(tmp_path: Path) -> None:
    evals = _evals(tmp_path, _items())
    _manifest(evals, "talkover", lambda m: m["files"][0].update(sha256="f" * 64))
    _manifest(evals, "talkover", lambda m: m["files"].append(m["files"][1] | {"path": "spare.wav"}))
    _manifest(evals, "owner", lambda m: m.pop("consent"))
    problems = _check(evals).problems
    assert (
        "t01/t01-a: talkover:t01-a.wav: its hash, device or session is not its manifest's"
        in problems
    )
    assert "talkover:spare.wav: named by 0 segments, not one" in problems
    assert "n01/n01-a: owner:n01-a.wav: a new recording whose manifest holds no consent" in problems
    (evals / "manifests" / "owner.json").unlink()
    assert "n01/n01-a: owner:n01-a.wav is in no manifest" in _check(evals).problems


def test_a_split_or_strata_that_do_not_fit_the_items_fail_the_set(tmp_path: Path) -> None:
    evals = _evals(tmp_path, _items())
    split = json.loads((evals / "split.json").read_text(encoding="utf-8"))
    del split["items"]["n01"]
    (evals / "split.json").write_text(json.dumps(split), encoding="utf-8")
    strata = (
        (evals / "strata.toml").read_text(encoding="utf-8").replace("total = 3\n", "total = 4\n", 1)
    )
    (evals / "strata.toml").write_text(strata, encoding="utf-8")
    assert _check(evals).problems == [
        "split.json does not name exactly the items: run the split again",
        "strata.toml: the items do not hold their registered counts",
    ]


def test_a_file_that_cannot_be_read_fails_the_set_by_name(tmp_path: Path) -> None:
    evals = _evals(tmp_path, _items())
    guide = (evals / "spelling.toml").read_text(encoding="utf-8")
    (evals / "spelling.toml").write_text(
        guide.replace('"listening-sounds"', '"sounds"'), encoding="utf-8"
    )
    assert _check(evals).problems == ["the spelling guide has no ruling 'listening-sounds'"]
    (evals / "spelling.toml").write_text(guide, encoding="utf-8")
    (evals / "strata.toml").write_text("[items]\n", encoding="utf-8")
    assert [p.split(":")[0] for p in _check(evals).problems] == ["strata.toml"]


def _reader(changes: Mapping[str, Mapping[str, Any]] | None = None) -> Callable[[Path], Wav]:
    """A fake reader: each file's made-up facts, as its manifest says unless changed."""

    def read(path: Path) -> Wav:
        facts: dict[str, Any] = {"sha256": SHA, "sample_rate": 16000, "frames": 16000}
        facts |= (changes or {}).get(path.name, {})
        if "error" in facts:
            raise facts["error"]
        pcm = b"\x00\x00" * facts["frames"]
        return Wav(pcm16=pcm, sample_rate=facts["sample_rate"], sha256=facts["sha256"])

    return read


def test_the_audio_of_a_root_given_is_checked_against_its_manifest(tmp_path: Path) -> None:
    evals = _evals(tmp_path / "evals", _items())
    folders = {"talkover": tmp_path / "talkover", "owner": tmp_path / "owner"}
    report = _check(evals, audio=folders, read=_reader())
    assert (report.problems, report.audio_files) == ([], 5)
    changes: dict[str, dict[str, Any]] = {
        "t01-a.wav": {"sha256": "f" * 64},
        "t01-b.wav": {"sample_rate": 8000, "frames": 8000},
        "t02-a.wav": {"frames": 16100},
        "t02-b.wav": {"error": AudioFormatError("44100 Hz, 2 channel(s), 16-bit")},
        "n01-a.wav": {"error": FileNotFoundError("no such file")},
    }
    report = _check(evals, audio=folders, read=_reader(changes))
    assert report.problems == [
        "owner:n01-a.wav: FileNotFoundError: no such file",
        "talkover:t01-a.wav: its hash, rate or length is not its manifest's",
        "talkover:t01-b.wav: its hash, rate or length is not its manifest's",
        "talkover:t02-a.wav: its hash, rate or length is not its manifest's",
        "talkover:t02-b.wav: AudioFormatError: 44100 Hz, 2 channel(s), 16-bit",
    ]
    report = _check(evals, audio={"elsewhere": tmp_path}, read=_reader())
    assert report.problems == ["--audio elsewhere: no manifest names this root"]
    assert _check(evals, read=_reader(changes)).problems == []  # no root given: no audio read


def test_an_audio_file_reached_through_a_link_out_of_its_root_is_refused(tmp_path: Path) -> None:
    items = _change(
        _items(), "n01", 0, segments=[{"root": "owner", "path": "linked/n01-a.wav", "sha256": SHA}]
    )
    evals = _evals(tmp_path / "evals", items)
    outside, folder = tmp_path / "outside", tmp_path / "owner"
    outside.mkdir()
    folder.mkdir()
    link_folder(folder / "linked", outside)
    read: list[Path] = []

    def reader(path: Path) -> Wav:
        read.append(path)
        return _reader()(path)

    report = _check(evals, audio={"owner": folder}, read=reader)
    assert report.problems == ["owner:linked/n01-a.wav: leads outside its root's folder"]
    assert read == []  # refused before it is read


def test_the_command_freezes_checks_and_fails_without_writing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(golden, "spelling_issues", FakeSpellingCheck())
    monkeypatch.setattr(golden, "read_wav", _reader())
    evals = _evals(tmp_path / "evals", _items())
    command = ["--evals", str(evals)]
    assert golden.main([*command, "--check"]) == 1  # nothing frozen yet
    assert golden.main([*command, "--audio", f"talkover={tmp_path}"]) == 0
    frozen = (evals / "frozen.json").read_bytes()
    assert frozen.endswith(b"]\n}\n") and b"\r" not in frozen
    assert golden.main([*command, "--check"]) == 0
    out = capsys.readouterr().out
    assert "variant_left_out" in out and "t01-b" in out and "عندي" not in out  # IDs, no text
    # A variant confirmed changes the frozen answers: --check fails until golden runs again.
    confirmed = _change(
        _items(), "t01", 1, confirmations=[{"at": WHEN.isoformat(), "review_pass": 2}]
    )
    (evals / "golden" / "t01.toml").write_text(dump_item(confirmed[0]), encoding="utf-8")
    assert golden.main([*command, "--check"]) == 1
    (evals / "terms.toml").unlink()
    assert golden.main(command) == 1
    assert (evals / "frozen.json").read_bytes() == frozen  # a failed run freezes nothing
    for broken in (
        ["--audio", "talkover"],
        ["--audio", "Bad=x"],
        ["--audio", "a=x", "--audio", "a=y"],
    ):
        with pytest.raises(SystemExit) as refused:
            golden.main([*command, *broken])
        assert refused.value.code == 2


def test_the_committed_set_is_valid_and_its_frozen_answers_are_fresh() -> None:
    report = _check(EVALS)
    assert report.problems == []
    assert report.frozen == (EVALS / "frozen.json").read_text(encoding="utf-8")
    items = {item.id: item for item in load_items(EVALS / "golden")}
    arabic = {
        i for i, item in items.items() if item.source == "talkover" and item.language != "english"
    }
    assert set(LANGUAGE) == arabic  # every Arabic phrase's ruling, and no other
    variants = {v.id for item in items.values() for v in item.variants}
    assert LEFT_OUT and not variants & set(LEFT_OUT)  # the owner's left-out takes stay out
    assert load_script(EVALS / "script.toml").lines


def test_the_manifests_name_no_file_outside_a_plain_path() -> None:
    for path in sorted((EVALS / "manifests").glob("*.json")):
        manifest = Manifest.model_validate_json(path.read_bytes())
        assert all(not re.search(r"[\\:]|\.\.", f.path) for f in manifest.files), path.name

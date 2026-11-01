"""The import of the owner's new takes: the recorder's files below its `--out` (a session's
consent, the take sidecars, the reviews) as items and per-session manifests, with no audio read.
A session that holds takes but no consent is refused."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest
from ole5_voice.evals import import_recordings
from ole5_voice.evals.items import GoldenSetError, load_items, load_manifests
from ole5_voice.evals.models import TICKET_KIND, Item
from ole5_voice.evals.takes import Script, review_file, session_file, take_sidecar
from ole5_voice.evals.toml_write import dump_item

from tests.ole5_voice.evals import samples

SHA = samples.SHA
WHEN = samples.WHEN

# The recordings import, on a made-up recorder `--out`: what `poe record` writes, with no audio.
SCRIPT = Script.model_validate(
    {
        "listening_sounds": ["اها"],
        "lines": [
            {"id": "n01", "kind": "request", "language": "saudi", "say": ["عندي مراسلة", "ثانية"]},
            {"id": "n02", "kind": TICKET_KIND, "language": "english", "say": ["ends in 4821"]},
            {"id": "n03", "kind": "silence", "language": "none", "seconds": 4},
        ],
    }
)
CONSENT = {"speaker": "the owner", "agreed": True, "on": "2026-11-02", "words": "I agree."}


def _put(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def _session(out: Path, session: str, device: str = "laptop") -> None:
    _put(out / session_file(session), {"session": session, "device": device, "consent": CONSENT})


def _take(out: Path, session: str, name: str, line: str, **changes: Any) -> None:
    sidecar = {
        "take": name,
        "line": line,
        "session": session,
        "device": "laptop",
        "microphone": "Microphone Array",
        "track": {"echo_cancellation": True, "sample_rate": 48000},
        "recorded_at": WHEN.isoformat(),
        "file": f"{name}.wav",
        "sha256": SHA,
        "seconds": 2.5,
        "status": "kept",
    }
    _put(out / take_sidecar(session, name), sidecar | changes)


def _review_file(out: Path, session: str, take: str, n: int, verdict: str, text: str = "") -> None:
    review = {"take": take, "review_pass": n, "at": WHEN.isoformat(), "verdict": verdict}
    _put(out / review_file(session, take, n), review | {"text": text})


def _recorded(out: Path) -> None:
    _session(out, "laptop-1")
    _take(out, "laptop-1", "n01-laptop-1", "n01", turn_ends_ms=[1800])
    _take(out, "laptop-1", "n02-laptop-1", "n02")
    _take(out, "laptop-1", "n03-laptop-1", "n03")
    _take(out, "laptop-1", "n03-laptop-1-old", "n03", status="discarded")
    _review_file(out, "laptop-1", "n01-laptop-1", 1, "confirmed")
    _review_file(out, "laptop-1", "n02-laptop-1", 1, "typed", "ends in 4812")
    _session(out, "wired-1", device="wired")
    _take(out, "wired-1", "n01-wired-1", "n01", device="wired")
    _review_file(out, "talkover-2026-10-27", "s01__duck", 1, "confirmed")  # reviews only


def test_the_recordings_import_makes_an_item_of_each_line_recorded(tmp_path: Path) -> None:
    _recorded(tmp_path)
    items, manifests = import_recordings.build(tmp_path, SCRIPT)
    assert [(i.id, i.kind, i.language, len(i.variants)) for i in items] == [
        ("n01", "request", "saudi", 2),
        ("n02", TICKET_KIND, "english", 1),
        ("n03", "silence", "none", 1),
    ]
    laptop, wired = items[0].variants
    assert (laptop.reference, laptop.reference_source) == ("عندي مراسلة ثانية", "script")
    assert ([c.review_pass for c in laptop.confirmations], laptop.turn_ends_ms) == ([1], (1800,))
    assert (wired.device, wired.confirmations) == ("wired", ())
    assert laptop.segments[0].model_dump() == {
        "root": "owner",
        "path": "laptop-1/n01-laptop-1.wav",
        "sha256": SHA,
    }
    ticket = items[1].variants[0]
    assert (ticket.reference, ticket.reference_source, ticket.confirmations) == (
        "ends in 4812",
        "typed",
        (),
    )
    silence = items[2].variants[0]
    assert (silence.reference, silence.reference_source) == ("", "none")
    assert sorted(manifests) == ["owner-laptop-1", "owner-wired-1"]
    laptop_files = manifests["owner-laptop-1"]
    assert laptop_files.consent is not None and laptop_files.consent.words == "I agree."
    assert [f.path for f in laptop_files.files] == [
        "laptop-1/n01-laptop-1.wav",
        "laptop-1/n02-laptop-1.wav",
        "laptop-1/n03-laptop-1.wav",
    ]


def _refused(out: Path, problem: str) -> None:
    with pytest.raises(GoldenSetError, match=re.escape(problem)):
        import_recordings.build(out, SCRIPT)


def test_a_session_without_its_consent_is_refused(tmp_path: Path) -> None:
    _take(tmp_path, "laptop-1", "n01-laptop-1", "n01")
    _refused(tmp_path, "laptop-1: a session without its session.json (consent)")
    (tmp_path / "laptop-1" / "n01-laptop-1.json").unlink()
    (tmp_path / "laptop-1" / "n01-laptop-1.wav").write_bytes(b"")  # a take with no sidecar
    _refused(tmp_path, "without its session.json")
    _session(tmp_path, "laptop-1")
    consent = json.loads((tmp_path / "laptop-1" / "session.json").read_text(encoding="utf-8"))
    consent["consent"]["agreed"] = False
    _put(tmp_path / "laptop-1" / "session.json", consent)
    _refused(tmp_path, "session.json")


@pytest.mark.parametrize(
    ("case", "problem"),
    [
        ("session", "laptop-1/session.json: names another session"),
        ("device", "its session, device or file is not its folder's"),
        ("name", "not the sidecar of the take it names"),
        ("line", "the script has no line n09"),
        ("orphan", "reviews of takes it does not hold: ['n05-laptop-1']"),
        ("review", "not the review its name says"),
    ],
)
def test_recorder_files_that_disagree_are_refused(tmp_path: Path, case: str, problem: str) -> None:
    _session(tmp_path, "laptop-1")
    _take(tmp_path, "laptop-1", "n01-laptop-1", "n01")
    if case == "session":
        _put(
            tmp_path / "laptop-1" / "session.json",
            {"session": "wired-1", "device": "laptop", "consent": CONSENT},
        )
    elif case == "device":
        _take(tmp_path, "laptop-1", "n01-laptop-1", "n01", device="wired")
    elif case == "name":
        _take(tmp_path, "laptop-1", "n01-laptop-1", "n01", take="n02-laptop-1")
    elif case == "line":
        _take(tmp_path, "laptop-1", "n01-laptop-1", "n09")
    elif case == "orphan":
        _review_file(tmp_path, "laptop-1", "n05-laptop-1", 1, "confirmed")
    else:
        _review_file(tmp_path, "laptop-1", "n01-laptop-1", 1, "confirmed")
        path = tmp_path / review_file("laptop-1", "n01-laptop-1", 1)
        path.rename(path.with_name("n01-laptop-1.review-2.json"))
    _refused(tmp_path, problem)


def test_the_recordings_command_writes_items_and_manifests_beside_the_talk_over(
    tmp_path: Path,
) -> None:
    out, evals = tmp_path / "out", tmp_path / "evals"
    _recorded(out)
    (evals / "golden").mkdir(parents=True)
    (evals / "script.toml").write_text(
        '[[lines]]\nid = "n01"\nkind = "request"\nlanguage = "saudi"\nsay = ["عندي مراسلة"]\n'
        '[[lines]]\nid = "n02"\nkind = "ticket_number"\nlanguage = "english"\nsay = ["x"]\n'
        '[[lines]]\nid = "n03"\nkind = "silence"\nlanguage = "none"\n',
        encoding="utf-8",
    )
    assert import_recordings.main(["--takes", str(out), "--evals", str(evals)]) == 0
    assert [i.id for i in load_items(evals / "golden")] == ["n01", "n02", "n03"]
    assert [m.consent is not None for m in load_manifests(evals / "manifests")] == [True, True]
    talkover = samples.item("n02")
    talkover = Item.model_validate(talkover.model_dump() | {"source": "talkover"})
    (evals / "golden" / "n02.toml").write_text(dump_item(talkover), encoding="utf-8")
    assert import_recordings.main(["--takes", str(out), "--evals", str(evals)]) == 1
    assert import_recordings.main(["--takes", str(tmp_path / "absent"), "--evals", str(evals)]) == 1
    with pytest.raises(SystemExit) as refused:
        import_recordings.main(["--takes", str(out), "--root", "Not A Name"])
    assert refused.value.code == 2

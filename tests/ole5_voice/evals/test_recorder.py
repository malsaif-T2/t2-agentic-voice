"""`poe record`, against a real server on a free port of 127.0.0.1 in a thread: the consent,
takes saved with their sidecars and played back, the turn ends of a several-clause take, the
review passes, the golden-set variants beside their references, and the command. The refusals
are in `test_recorder_security.py`; the made-up tree and the client in `recorder_support.py`."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest
from ole5_voice.evals import items, recorder, recorder_state
from ole5_voice.evals.audio import sha256_of
from ole5_voice.evals.models import Item
from ole5_voice.evals.recorder import RecorderServer
from ole5_voice.evals.recorder_state import RecorderError
from ole5_voice.evals.takes import Review, SessionRecord, TakeSidecar

from tests.ole5_voice.evals.recorder_support import (
    CONSENT,
    LONG,
    WHEN,
    Tree,
    get,
    make_tree,
    post,
    recorder_of,
    serving,
    sidecar,
    take,
    wav,
)

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture
def tree(tmp_path: Path) -> Tree:
    return make_tree(tmp_path)


def test_a_take_is_saved_with_its_sidecar_and_plays_back(tree: Tree) -> None:
    clip = wav()
    with serving(recorder_of(tree)) as server:
        assert post(server, "api/consent", CONSENT).status == 200
        saved = post(server, "api/take", take(clip=clip))
        played = get(server, "take/n01-laptop-1-1")
        state = get(server, "api/state").json()
    assert (saved.status, saved.json()) == (200, {"take": "n01-laptop-1-1", "status": "kept"})
    assert (played.status, played.body, played.headers["Content-Type"]) == (200, clip, "audio/wav")
    folder = tree.out / "laptop-1"
    assert (folder / "n01-laptop-1-1.wav").read_bytes() == clip
    written = TakeSidecar.model_validate_json((folder / "n01-laptop-1-1.json").read_bytes())
    assert (written.microphone, written.output) == (
        "Microphone Array (made up)",
        "Speakers (made up)",
    )
    assert (written.line, written.session, written.device, written.recorded_at) == (
        "n01",
        "laptop-1",
        "laptop",
        WHEN,
    )
    assert (written.sha256, written.seconds, written.file) == (
        sha256_of(clip),
        0.5,
        "n01-laptop-1-1.wav",
    )
    assert (written.track.echo_cancellation, written.track.noise_suppression) == (True, True)
    assert state["takes"] == [
        {"take": "n01-laptop-1-1", "line": "n01", "status": "kept", "seconds": 0.5}
    ]
    assert sorted(e["id"] for e in state["review"] if e["due"]) == ["n01-laptop-1-1", "t01-1"]
    assert state["consent"]["speaker"] == "the owner"


def test_the_consent_comes_first_and_is_written_once(tree: Tree) -> None:
    with serving(recorder_of(tree)) as server:
        assert post(server, "api/take", take()).status == 409
        assert post(server, "api/consent", CONSENT | {"agreed": False}).status == 400
        assert post(server, "api/consent", CONSENT | {"words": ""}).status == 400
        assert post(server, "api/consent", CONSENT).status == 200
        first = (tree.out / "laptop-1" / "session.json").read_bytes()
        again = post(server, "api/consent", CONSENT | {"speaker": "someone else"})
    assert again.status == 409 and "never replaced" in again.json()["error"]
    assert (tree.out / "laptop-1" / "session.json").read_bytes() == first
    record = SessionRecord.model_validate_json(first)
    assert (record.session, record.device, record.consent.on) == ("laptop-1", "laptop", WHEN.date())
    assert record.consent.words == CONSENT["words"]
    assert recorder_of(tree).consent == record  # a later run of the session finds it


def test_a_take_never_replaces_a_file(tree: Tree) -> None:
    folder = tree.out / "laptop-1"
    folder.mkdir()
    for stray in ("n01-laptop-1-1.wav", "n01-laptop-1-2.wav"):
        (folder / stray).write_bytes(b"the owner's own file")
    with serving(recorder_of(tree)) as server:
        post(server, "api/consent", CONSENT)
        first = post(server, "api/take", take()).json()["take"]
        second = post(server, "api/take", take(status="discarded")).json()["take"]
    assert (first, second) == ("n01-laptop-1-3", "n01-laptop-1-4")
    for stray in ("n01-laptop-1-1.wav", "n01-laptop-1-2.wav"):
        assert (folder / stray).read_bytes() == b"the owner's own file"


@pytest.mark.parametrize(
    ("ends", "status", "code"),
    [
        ((), "kept", 400),  # a kept take of several clauses needs its turn ends
        ((501,), "kept", 400),  # past the take's 500 ms
        ((300, 100), "kept", 400),  # out of order
        ((250, 250), "kept", 400),  # twice the same
        ((250, 500), "kept", 200),
        ((), "discarded", 200),
    ],
)
def test_a_take_of_several_clauses_keeps_its_true_turn_ends(
    tree: Tree, ends: tuple[int, ...], status: str, code: int
) -> None:
    with serving(recorder_of(tree)) as server:
        post(server, "api/consent", CONSENT)
        answer = post(server, "api/take", take("n02", turn_ends_ms=list(ends), status=status))
    assert answer.status == code
    written = list((tree.out / "laptop-1").glob("n02-*.json"))
    assert [TakeSidecar.model_validate_json(p.read_bytes()).turn_ends_ms for p in written] == (
        [ends] if code == 200 else []
    )


def test_a_typed_text_comes_back_for_its_own_check_in_a_later_pass(tree: Tree) -> None:
    typed = {"id": "n01-laptop-1-1", "verdict": "typed", "text": " open a ticket about my email "}
    with serving(recorder_of(tree)) as server:
        post(server, "api/consent", CONSENT)
        post(server, "api/take", take())
        post(server, "api/take", take(status="discarded"))  # n01-laptop-1-2, never checked
        confirmed = post(server, "api/review", {"id": "t01-1", "verdict": "confirmed"})
        first = post(server, "api/review", typed)
        again = post(server, "api/review", {"id": "n01-laptop-1-1", "verdict": "confirmed"})
        assert (
            post(server, "api/review", {"id": "n01-laptop-1-2", "verdict": "confirmed"}).status
            == 404
        )
        assert post(server, "api/review", typed | {"text": "  "}).status == 400
        assert (
            post(server, "api/review", {"id": "t01-1", "verdict": "confirmed", "text": "x"}).status
            == 400
        )
    assert (confirmed.status, confirmed.json()["due"]) == (200, False)
    assert (first.status, first.json()["due"], first.json()["source"]) == (200, False, "typed")
    assert first.json()["reference"] == "open a ticket about my email"
    assert again.status == 409  # one review a pass: its second check waits for a later pass
    later = recorder_of(tree)
    shown = {e["id"]: e for e in later.state()["review"]}
    assert later.review_pass == 2
    assert (shown["n01-laptop-1-1"]["due"], shown["t01-1"]["due"]) == (True, False)
    assert shown["n01-laptop-1-1"]["reference"] == "open a ticket about my email"
    with serving(later) as server:
        assert (
            post(server, "api/review", {"id": "n01-laptop-1-1", "verdict": "confirmed"}).json()[
                "due"
            ]
            is False
        )
    second = tree.out / "laptop-1" / "n01-laptop-1-1.review-2.json"
    review = Review.model_validate_json(second.read_bytes())
    assert (review.verdict, review.review_pass, review.at, review.text) == (
        "confirmed",
        2,
        WHEN,
        "",
    )
    assert (tree.out / "talkover-1" / "t01-1.review-1.json").is_file()


def test_the_variants_the_manifests_name_play_beside_their_reference(tree: Tree) -> None:
    checker = recorder_of(tree)
    with serving(checker) as server:
        played = get(server, "variant/t01-1/0")
        reply = get(server, "reply/en_ticket")
        state = get(server, "api/state").json()
    assert (played.status, played.body) == (200, tree.segment)
    assert (reply.status, reply.body) == (200, (tree.replies / "en_ticket.wav").read_bytes())
    assert state["replies"] == [
        {"id": "en_ticket", "lang": "en", "topic": "a ticket read-back", "ms": 300}
    ]
    shown = {e["id"]: e for e in state["review"]}
    assert shown == {
        "t01-1": {
            "id": "t01-1",
            "of": "t01",
            "kind": "sentence",
            "language": "saudi",
            "reference": "افتح تذكرة",
            "source": "script",
            "segments": 1,
            "reviews": [],
            "due": True,
        }
    }  # t01-2's file is on no manifest, t01-3's root was not given
    assert checker.skipped == ["variant t01-2: a segment is no file its manifest names"]
    (tree.talkover / "seg" / "a.wav").write_bytes(wav(0.25))  # changed since its manifest
    with serving(checker) as server:
        assert get(server, "variant/t01-1/0").status == 409


def test_a_recorder_without_a_session_only_reviews(tree: Tree) -> None:
    with serving(recorder_of(tree, session=None, device=None)) as server:
        refused = [
            post(server, route, body).status
            for route, body in [("api/consent", CONSENT), ("api/take", take())]
        ]
        state = get(server, "api/state").json()
    assert refused == [409, 409]
    assert (state["session"], state["device"], state["consent"], state["takes"]) == (
        None,
        None,
        None,
        [],
    )
    assert [line["id"] for line in state["lines"]] == ["n01", "n02", "n03", LONG]


def _unreadable(folder: Path) -> tuple[Item, ...]:
    raise ValueError("a made-up item file that does not parse")


def _break(tree: Tree, case: str) -> dict[str, Any]:
    """What makes the recorder refuse to start, for each case."""
    other = {"device": "wired"}
    if case == "--out in the repository":
        return {"out": ROOT / "docs" / "takes"}
    if case == "no script":
        return {"script": tree.root / "missing.toml"}
    if case == "two lines one ID":
        tree.script.write_text(
            tree.script.read_text(encoding="utf-8").replace('"n02"', '"n01"'), encoding="utf-8"
        )
    elif case == "a reply but no --replies":
        return {"replies": None}
    elif case in {"a reply's file is a path", "a reply's file is below a folder"}:
        name = "../../.env" if case == "a reply's file is a path" else "sub/en_ticket.wav"
        replies = json.dumps([{"id": "en_ticket", "file": name}])
        (tree.replies / "replies.json").write_text(replies, encoding="utf-8")
    elif case == "two replies one ID":
        (tree.replies / "replies.json").write_text(
            json.dumps([{"id": "en_ticket", "file": "a.wav"}] * 2), encoding="utf-8"
        )
    elif case in {
        "a broken sidecar",
        "a misplaced sidecar",
        "a misplaced review",
        "another device",
    }:
        folder = tree.out / "laptop-1"
        folder.mkdir()
        if case == "a broken sidecar":
            (folder / "n01-laptop-1-1.json").write_text("{", encoding="utf-8")
        elif case == "a misplaced sidecar":
            (folder / "n01-laptop-1-9.json").write_text(
                sidecar("n01-laptop-1-1", "n01", "0" * 64), encoding="utf-8"
            )
        elif case == "a misplaced review":
            review = {
                "take": "n01-laptop-1-1",
                "review_pass": 2,
                "at": WHEN.isoformat(),
                "verdict": "confirmed",
            }
            (folder / "n01-laptop-1-1.review-1.json").write_text(
                json.dumps(review), encoding="utf-8"
            )
        else:
            record = {
                "session": "laptop-1",
                "device": "laptop",
                "consent": CONSENT | {"on": "2026-11-02"},
            }
            (folder / "session.json").write_text(json.dumps(record), encoding="utf-8")
            return other
    elif case == "a root no manifest names":
        return {"audio": {"owner": tree.talkover}}
    elif case == "items that do not load":
        return {"load_items": _unreadable}
    return {}


@pytest.mark.parametrize(
    "case",
    [
        "--out in the repository",
        "no script",
        "two lines one ID",
        "a reply but no --replies",
        "a reply's file is a path",
        "a reply's file is below a folder",
        "two replies one ID",
        "a broken sidecar",
        "a misplaced sidecar",
        "a misplaced review",
        "another device",
        "a root no manifest names",
        "items that do not load",
    ],
)
def test_the_recorder_never_starts_on_a_guess(tree: Tree, case: str) -> None:
    with pytest.raises(RecorderError):
        recorder_of(tree, **_break(tree, case))
    assert not (ROOT / "docs" / "takes").exists()


def test_a_take_whose_line_left_the_script_is_listed_not_checked(tree: Tree) -> None:
    folder = tree.out / "laptop-1"
    folder.mkdir()
    (folder / "gone-laptop-1-1.json").write_text(
        sidecar("gone-laptop-1-1", "gone", "0" * 64), encoding="utf-8"
    )
    (tree.out / "Not A Session").mkdir()  # not named as a session is: not read
    checker = recorder_of(tree)
    assert checker.skipped[0] == "take gone-laptop-1-1: the script has no line gone"
    assert "gone-laptop-1-1" not in checker.entries and "gone-laptop-1-1" in checker.takes


def test_poe_record_logs_its_address_and_closes_on_ctrl_c(
    tree: Tree, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def interrupted(self: RecorderServer, poll_interval: float = 0.5) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(RecorderServer, "serve_forever", interrupted)
    folder = tree.out / "laptop-1"
    folder.mkdir()
    (folder / "gone-laptop-1-1.json").write_text(
        sidecar("gone-laptop-1-1", "gone", "0" * 64), encoding="utf-8"
    )
    given = ["--out", str(tree.out), "--session", "laptop-1", "--device", "laptop"]
    given += ["--script", str(tree.script), "--replies", str(tree.replies), "--port", "0"]
    assert recorder.main(given) == 0
    out = capsys.readouterr().out
    assert re.search(r"recorder_ready .* address=.?http://127\.0\.0\.1:\d+/[\w-]{40,}/", out)
    assert "recorder_left_out" in out and "recorder_closed" in out
    assert out.count("http://127.0.0.1:") == 1  # the token is in one line only


@pytest.mark.parametrize(
    "given",
    [
        ["--session", "laptop-1"],  # without --device
        ["--device", "laptop"],
        ["--session", "Laptop 1", "--device", "laptop"],
        ["--audio", "talkover"],
        ["--audio", "a=x", "--audio", "a=y"],
        ["--port", "70000"],
        ["--port", "x"],
        ["--device", "phone", "--session", "s"],
    ],
)
def test_poe_record_refuses_arguments_it_cannot_use(tree: Tree, given: list[str]) -> None:
    with pytest.raises(SystemExit) as done:
        recorder.main(["--out", str(tree.out), *given])
    assert done.value.code == 2


def test_poe_record_says_why_it_does_not_start(
    tree: Tree, capsys: pytest.CaptureFixture[str]
) -> None:
    assert recorder.main(["--out", str(tree.out), "--script", str(tree.root / "none.toml")]) == 2
    assert "recorder_not_started" in capsys.readouterr().out
    with serving(recorder_of(tree)) as taken:  # its port is in use
        given = [
            "--out",
            str(tree.out),
            "--script",
            str(tree.script),
            "--replies",
            str(tree.replies),
        ]
        assert recorder.main([*given, "--port", str(taken.server_port)]) == 2


def test_the_clock_is_local_time_with_its_offset() -> None:
    assert recorder_state.local_now().utcoffset() is not None
    assert items.EVALS == ROOT / "apps" / "ole5-voice-agent" / "evals"

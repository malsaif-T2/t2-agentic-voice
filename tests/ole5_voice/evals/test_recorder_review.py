"""`poe record`'s review mode, against a real server on 127.0.0.1: a typed text comes back for
its own check in a later pass, the golden-set variants play beside their references, a recorder
with no session only reviews, and the page shows each entry's reference and check by the
import's rule (`items.reviewed`, Q9 of plan 002)."""

from __future__ import annotations

import json

import pytest
from ole5_voice.evals.recorder_state import RecorderError
from ole5_voice.evals.takes import Review

from tests.ole5_voice.evals.recorder_support import (
    CONSENT,
    LONG,
    WHEN,
    Tree,
    get,
    post,
    recorder_of,
    serving,
    take,
    wav,
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


def test_the_page_shows_a_reference_and_its_check_as_the_import_reads_them(tree: Tree) -> None:
    """The page's review state is `items.reviewed`'s: a typed text, its spaces collapsed as the
    import collapses them, is the reference and is due until a later pass confirms it; and a
    review the import would refuse stops the recorder before it starts (plan 004, app9)."""
    folder = tree.out / "talkover-1"
    folder.mkdir(parents=True)

    def review(n: int, verdict: str, text: str = "") -> None:
        fields = {"take": "t01-1", "review_pass": n, "at": WHEN.isoformat(), "verdict": verdict}
        (folder / f"t01-1.review-{n}.json").write_text(json.dumps(fields | {"text": text}))

    def shown() -> tuple[str, str, bool]:
        entry = {e["id"]: e for e in recorder_of(tree).state()["review"]}["t01-1"]
        return entry["reference"], entry["source"], entry["due"]

    review(1, "typed", " open  a\tticket ")
    assert shown() == ("open a ticket", "typed", True)
    review(2, "confirmed")
    assert shown() == ("open a ticket", "typed", False)
    review(3, "typed", "   ")
    with pytest.raises(RecorderError, match="the review 3 of t01-1 is empty, below --out"):
        recorder_of(tree)

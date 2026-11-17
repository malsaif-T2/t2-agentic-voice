"""The flight agent's page in three segments (apps/flight-voice-agent/web/cards.js; the owner's
ruling of 2026-11-17), run in the fake browser: each card in the segment its `slot` names,
outbound, return, review, then one card of no segment, a new one in place of the last, every
text as text; a pick marked in its leg's segment from the card that keeps it, lost when a change
drops it, a new search clearing the return and the review, a one-way trip showing no return; and
the review waiting for the yes, then booked with its reference from "Your trips"."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from t2_agentic_voice import CardRow
from t2_agentic_voice.voice.protocol import ShowCard, State, wire

from tests.browser import descendants, receive, text
from tests.flight_voice.page_support import (
    ANSWERS,
    BOOKINGS,
    ENGLISH,
    SCRIPT,
    TRIP,
    call,
    look,
    page,
)


def _segments(snapshot: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """The segments a snapshot of the cards' list shows, by their slot."""
    return {item["attrs"]["data-slot"]: item for item in snapshot["children"]}


def _rows(segment: dict[str, Any]) -> list[tuple[str, str | None]]:
    """A segment's rows, each its title and its mark."""
    rows = segment["children"][1]["children"]
    return [(text(row["children"][0]), row["attrs"].get("data-mark")) for row in rows]


def test_each_card_fills_its_segment_in_place_every_text_as_text(tmp_path: Path) -> None:
    sent = [
        ShowCard(title=SCRIPT, steps=("<img src=x onerror=alert(1)>",), slot="outbound"),
        ShowCard(title="الذهاب: الرياض إلى لندن", steps=("٠٩:١٠ إلى ١٦:١٥",), slot="outbound"),
        ShowCard(title="العودة: لندن إلى الرياض", steps=("١٦:٠٠ إلى ٢٣:٥٥",), slot="return"),
        ShowCard(title="رحلتك", steps=("المجموع",), slot="review"),
        ShowCard(title="الدرجات على رحلة T2 401", steps=("السياحية",)),
    ]
    shown = page(
        tmp_path,
        [
            look("cards-section"),
            *call(*(receive(wire(card)) for card in sent), look("cards-section")),
        ],
    )
    before, after = shown["snapshots"]
    assert "hidden" in before["attrs"] and "hidden" not in after["attrs"]
    (_, listed) = after["children"]
    items = listed["children"]
    assert [item["attrs"]["data-slot"] for item in items] == [
        "outbound",
        "return",
        "review",
        "extra",
    ]
    assert [text(item["children"][0]) for item in items] == [c.title for c in sent[1:]]
    for item in items:
        title, lines = item["children"]
        assert title["attrs"]["dir"] == "auto"
        assert all(line["attrs"] == {"dir": "auto"} for line in lines["children"])
    shown = page(tmp_path / "again", call(receive(wire(sent[0])), look("cards")))
    (only,) = shown["snapshots"][0]["children"]
    title, lines = only["children"]
    assert text(title) == SCRIPT
    assert [text(line) for line in lines["children"]] == list(sent[0].steps)
    assert [e["tag"] for e in descendants(only)] == ["h3", "ul", "li"]


A, B = CardRow(title="09:10 to 13:15", value="3,560 SAR", mark="best"), CardRow(title="14:40")
C, D = CardRow(title="16:00 to 23:55", value="2,390 SAR"), CardRow(title="21:45 to 05:40")
OUT = ShowCard(title="Outbound", rows=(A, B), slot="outbound")
BACK = ShowCard(title="Return", rows=(C, D, A.model_copy(update={"mark": "chosen"})), slot="return")
PICKED = (A.model_copy(update={"mark": "chosen"}), C.model_copy(update={"mark": "chosen"}))
REVIEW = ShowCard(title="Your trip", rows=(*PICKED, CardRow(title="Total")), slot="review")


def test_a_pick_is_marked_in_its_legs_segment_and_lost_when_a_change_drops_it(
    tmp_path: Path,
) -> None:
    one_way = ShowCard(title="Your trip", rows=(PICKED[0], CardRow(title="Total")), slot="review")
    relisted = ShowCard(title="Outbound", rows=(B, PICKED[1]), slot="outbound")
    steps = [receive(wire(card)) for card in (OUT, BACK)]
    shown = page(
        tmp_path,
        [
            ENGLISH,
            *call(*steps, look("cards"), receive(wire(REVIEW)), look("cards")),
            *[receive(wire(card)) for card in (relisted,)],
            look("cards"),
            *[receive(wire(card)) for card in (OUT, BACK, REVIEW, one_way)],
            look("cards"),
            receive(wire(OUT)),
            look("cards"),
        ],
    )
    picked, reviewed, lost, made_one_way, searched = (_segments(s) for s in shown["snapshots"])
    assert _rows(picked["outbound"]) == [(A.title, "chosen"), (B.title, None)]
    assert _rows(picked["return"]) == [(C.title, None), (D.title, None)]
    assert text(picked["outbound"]["children"][1]["children"][0]).endswith("Your pick")
    assert _rows(reviewed["return"]) == [(C.title, "chosen"), (D.title, None)]
    assert _rows(reviewed["outbound"])[0] == (A.title, "chosen") and "review" in reviewed
    # A change that lists the outbound again: its pick is lost, the return's kept.
    assert _rows(lost["outbound"]) == [(B.title, None)] and "review" not in lost
    assert _rows(lost["return"])[0] == (C.title, "chosen")
    # The trip made one way: no return segment; a new search: the outbound alone.
    assert set(made_one_way) == {"outbound", "review"}
    assert set(searched) == {"outbound"} and _rows(searched["outbound"])[0] == (A.title, "best")


def test_the_review_waits_for_the_yes_then_says_booked_with_its_reference(
    tmp_path: Path,
) -> None:
    made = {"reference": "262307", "depart": "2026-12-17", "return_date": None, "total_sar": 900}
    later = {"bookings": [TRIP | made, *BOOKINGS["bookings"]]}
    answers = ANSWERS | {"GET bookings": {"sequence": [[200, BOOKINGS], [200, later]]}}
    shown = page(
        tmp_path,
        [
            ENGLISH,
            *call(
                receive(wire(REVIEW)),
                receive(wire(State(state="confirming"))),
                look("cards"),
                receive(wire(State(state="speaking"))),
                look("cards"),
            ),
        ],
        answers,
    )
    waiting, booked = (_segments(s)["review"] for s in shown["snapshots"])
    assert text(waiting["children"][-1]) == "Waiting for your yes"
    assert waiting["children"][-1]["attrs"]["class"] == "card-status"
    assert text(booked["children"][-1]) == "Booked · Reference 262307"

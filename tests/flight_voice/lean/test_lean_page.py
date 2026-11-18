"""The flight page's three segments (web/cards.js) filled from the lean agent's own cards, run in
the fake browser as test_page_segments.py runs it: the outbound flights from `find_flights`, the
return flights with the outbound pick marked from `choose_flights`, the trip for confirmation
once complete, then the same review marked booked with its reference by `book_trip`; and a span
of days as the outbound segment's calendar."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from t2_agentic_voice import Card
from t2_agentic_voice.voice.protocol import ShowCard, wire

from tests.browser import receive, text
from tests.flight_voice.lean.lean_support import BACK, OUT, LeanCall, ids
from tests.flight_voice.page_support import ENGLISH, call, look, page


def _shown(card: Card | None) -> dict[str, Any]:
    assert card is not None
    return receive(wire(ShowCard.of(card)))


def _segments(snapshot: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {item["attrs"]["data-slot"]: item for item in snapshot["children"]}


def _marks(segment: dict[str, Any]) -> list[str | None]:
    return [row["attrs"].get("data-mark") for row in segment["children"][1]["children"]]


def test_the_lean_cards_fill_the_three_segments_then_the_booking(tmp_path: Path) -> None:
    lean = LeanCall()
    found = lean.find(destination="Jeddah", depart=OUT, return_date=BACK)
    picked = lean.choose(outbound_id=ids(found)[1])
    complete = lean.choose(return_id=ids(picked, "return")[0])
    lean.said(f"Riyadh to Jeddah and back, economy, one traveler, {lean.total()} riyals in all.")
    lean.heard("yes")
    booked = lean.book()
    reference = lean.airline.bookings.made[0].reference
    shown = page(
        tmp_path,
        [
            ENGLISH,
            *call(
                _shown(found.card),
                look("cards"),
                _shown(picked.card),
                look("cards"),
                _shown(complete.card),
                look("cards"),
                _shown(booked.card),
                look("cards"),
            ),
        ],
    )
    listed, returns, review, done = (_segments(s) for s in shown["snapshots"])
    assert set(listed) == {"outbound"} and "best" in _marks(listed["outbound"])
    assert set(returns) == {"outbound", "return"}
    assert _marks(returns["outbound"])[1] == "chosen"  # the outbound pick, in its own segment
    assert set(review) == {"outbound", "return", "review"}
    assert _marks(review["return"])[0] == "chosen"
    rows = done["review"]["children"][1]["children"]
    assert text(rows[-1]).startswith(f"Booked · Reference {reference}")


def test_a_span_fills_the_outbound_segment_with_its_calendar(tmp_path: Path) -> None:
    found = LeanCall().find(
        destination="Dubai", depart={"first": "2026-11-20", "last": "2026-11-26"}
    )
    shown = page(tmp_path, [ENGLISH, *call(_shown(found.card), look("cards"))])
    (segments,) = (_segments(s) for s in shown["snapshots"])
    assert set(segments) == {"outbound"}
    assert _marks(segments["outbound"]).count("best") == 2

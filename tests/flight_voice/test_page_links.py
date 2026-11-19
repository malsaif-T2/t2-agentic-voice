"""The flight page's booking links (apps/flight-voice-agent/web/cards.js, D-126), run in the fake
browser: a review card with links shows each below its rows as a link styled as a button, its
label as text, opening its url in a new tab with no opener; the review then waits for no yes;
a card with no links shows none, as before; and the page builds no link from a card's text."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from t2_agentic_voice import CardLink, CardRow
from t2_agentic_voice.voice.protocol import ShowCard, State, wire

from tests.browser import descendants, receive, text
from tests.flight_voice.page_support import ENGLISH, call, look, page

GOOGLE = "https://www.google.com/travel/flights?q=Flights%20to%20JED%20from%20RUH%20on%20"
OUT_URL = GOOGLE + "2026-11-26%20one%20way%20on%20flynas&hl=en&curr=SAR&gl=sa"
BACK_URL = GOOGLE.replace("JED%20from%20RUH", "RUH%20from%20JED") + "2026-11-29&hl=en"
MARKUP = "<img src=x onerror=alert()>"
ROWS = (
    CardRow(title="06:00 to 07:45", detail="Outbound: flynas flight XY 17", value="429 SAR"),
    CardRow(title="Total", value="429 SAR"),
)


def _review(**more: Any) -> ShowCard:
    return ShowCard(title="Your trip: Riyadh to Jeddah", rows=ROWS, slot="review", **more)


def _anchors(node: dict[str, Any]) -> list[dict[str, Any]]:
    return [e for e in descendants(node) if e["tag"] == "a"]


def test_a_review_card_shows_each_link_below_its_rows_and_waits_for_no_yes(tmp_path: Path) -> None:
    links = (
        CardLink(label="Book the way out on flynas", url=OUT_URL),
        CardLink(label=MARKUP, url=BACK_URL),
    )
    shown = page(
        tmp_path,
        [
            ENGLISH,
            *call(
                receive(wire(_review())),
                look("cards"),
                receive(wire(_review(links=links))),
                receive(wire(State(state="speaking"))),
                look("cards"),
            ),
        ],
    )
    before, after = shown["snapshots"]
    (waiting,) = before["children"]
    assert text(waiting["children"][-1]) == "Waiting for your yes"
    assert _anchors(waiting) == []
    (review,) = after["children"]
    title, rows, block = review["children"]  # no status line: nothing waits for a yes
    assert (title["tag"], rows["attrs"]["class"]) == ("h3", "rows")
    assert (block["tag"], block["attrs"]) == ("div", {"class": "card-links"})
    opens = {"class": "card-link", "dir": "auto", "target": "_blank", "rel": "noopener noreferrer"}
    assert [(a["attrs"], text(a)) for a in block["children"]] == [
        (opens | {"href": OUT_URL}, "Book the way out on flynas"),
        (opens | {"href": BACK_URL}, MARKUP),
    ]
    assert {e["tag"] for e in descendants(review)} == {"h3", "ul", "li", "span", "div", "a"}


def test_the_page_builds_no_link_from_text_and_drops_one_not_https(tmp_path: Path) -> None:
    raw = wire(_review(steps=(OUT_URL,)))
    raw["rows"] = []
    odd = raw | {"links": [{"label": "Book", "url": "javascript:alert()"}]}
    shown = page(tmp_path, [ENGLISH, *call(receive(raw), receive(odd), look("cards"))])
    (review,) = shown["snapshots"][0]["children"]
    assert _anchors(review) == []
    assert OUT_URL in [text(e) for e in descendants(review)]  # shown as text, never a link


def test_a_flight_rows_own_link_is_a_small_link_button_at_its_end(tmp_path: Path) -> None:
    # D-130: every flight row on the real network carries its flight's link.
    rows = (
        CardRow(
            title="flynas · 06:00 to 07:45",
            detail="1 h 45 min · nonstop · flight XY 17",
            value="429 SAR",
            mark="best",
            link=CardLink(label="Book", url=OUT_URL),
        ),
        CardRow(
            title="Saudia · 09:00 to 10:50",
            value="610 SAR",
            link=CardLink(label=MARKUP, url=BACK_URL),
        ),
        CardRow(title="flyadeal · 12:00 to 13:45", value="455 SAR"),
    )
    listing = ShowCard(title="Outbound: Riyadh to Jeddah", rows=rows, slot="outbound")
    odd: dict[str, Any] = wire(listing)
    odd["rows"][2]["link"] = {"label": "Book", "url": "javascript:alert()"}
    shown = page(tmp_path, [ENGLISH, *call(receive(odd), look("cards"))])
    (segment,) = shown["snapshots"][0]["children"]
    first, second, third = next(e for e in descendants(segment) if e["tag"] == "ul")["children"]
    opens = {"class": "row-link", "dir": "auto", "target": "_blank", "rel": "noopener noreferrer"}
    assert [(a["attrs"], text(a)) for a in _anchors(first)] == [(opens | {"href": OUT_URL}, "Book")]
    assert [(a["attrs"], text(a)) for a in _anchors(second)] == [
        (opens | {"href": BACK_URL}, MARKUP)
    ]
    assert _anchors(third) == []  # a link that is not https is dropped, the row kept
    assert first["children"][-1]["tag"] == "a"  # at the row's end, after its mark

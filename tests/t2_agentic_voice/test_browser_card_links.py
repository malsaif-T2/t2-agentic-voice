"""A card's links on the browser side (D-126): the reference client `api/static/t2v-client.js`
hands the page each link as `CardLink` holds it (a label and an https url), drops a link that is
not one and keeps at most two, and gives a card from a session that sends none an empty list;
the dev page and the dev console show each as a link of its label to its url, opened in a new
tab with no opener, its label as text. Run in the fake browser (tests/browser.py)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from t2_agentic_voice import Card, CardLink, CardRow
from t2_agentic_voice.voice.protocol import ShowCard, wire

from tests.browser import browse, descendants, receive, text
from tests.t2_agentic_voice.test_browser_card_rows import CLIENT, DEV_PAGE, _client
from tests.t2_agentic_voice.test_browser_stt_choice import _console

URL = "https://www.google.com/travel/flights?q=Flights%20to%20JED%20from%20RUH&hl=en&gl=sa"
OPENS = {"target": "_blank", "rel": "noopener noreferrer"}
MARKUP = "<img src=x onerror=alert()>"  # markup a label may hold, with no digit


def _card(**given: Any) -> dict[str, Any]:
    return {"v": 1, "type": "card", "title": "x", "steps": [], "rows": [], "source": None} | given


def test_the_client_hands_the_page_each_link_as_the_session_sent_it(tmp_path: Path) -> None:
    links = (
        CardLink(label="Book on flynas", url=URL),
        CardLink(label="احجز على السعودية", url=URL),
    )
    message = wire(ShowCard.of(Card(title="Your trip", slot="review", links=links)))
    plain = _card()  # a session that sends no links
    shown = _client(tmp_path, [receive(message), receive(plain)])
    assert shown["events"] == [["card", message], ["card", plain | {"slot": None, "links": []}]]


def test_the_client_drops_a_link_that_is_not_one_and_keeps_at_most_two(tmp_path: Path) -> None:
    good = {"label": "Book on Saudia", "url": URL}
    broken = [
        "a link",
        None,
        [good],
        {"label": "Book"},
        {"url": URL},
        good | {"label": ""},
        good | {"label": "  "},
        good | {"label": "x" * 41},
        good | {"label": "Book SV 1020"},  # a digit
        good | {"label": "احجز ١٠٢٠"},
        good | {"label": 5},
        good | {"url": "http://www.google.com/"},
        good | {"url": "javascript:alert(1)"},
        good | {"url": "https://"},
        good | {"url": "https://www.google.com/a b"},
        good | {"url": "https://example.com/" + "a" * 2048},
        good | {"url": 7},
    ]
    kept = [*broken, good, good | {"label": "x" * 40, "extra": MARKUP}, good]
    shown = _client(tmp_path, [receive(_card(links=kept)), receive(_card(links="a link"))])
    [[name, value]] = shown["events"]  # a card whose links are no list is dropped
    assert name == "card"
    assert value["links"] == [good, good | {"label": "x" * 40}]


def _links(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    return [e for e in descendants(snapshot) if e["tag"] == "a"]


def test_the_dev_page_and_the_console_show_each_link_by_its_label(tmp_path: Path) -> None:
    links = (CardLink(label=MARKUP, url=URL),)
    card = wire(ShowCard.of(Card(title="Your trip", steps=("One traveler",), links=links)))
    look = {"do": "snapshot", "id": "card"}
    start = [{"do": "click", "id": "start"}, {"do": "open"}]
    plain = wire(ShowCard(title="Your trip"))
    dev = browse(
        tmp_path / "dev",
        {"t2v-client.js": CLIENT},
        entry="t2v-client.js",
        page=DEV_PAGE,
        location="http://127.0.0.1:7860/voice/dev",
        steps=[*start, receive(card), look, receive(plain), look],
    )
    console = _console(tmp_path / "console", [*start, receive(card), look, receive(plain), look])
    for shown in (dev, console):
        with_links, without = shown["snapshots"]
        [link] = _links(with_links)
        assert link["attrs"] == {"dir": "auto", "href": URL} | OPENS
        assert text(link) == MARKUP
        assert _links(without) == []


def test_the_client_hands_on_each_rows_link_and_drops_one_that_is_not(tmp_path: Path) -> None:
    # D-130: a row's own link, checked as a card's are; one that is not one is null, the row kept.
    good = {"label": "Book", "url": URL}
    row = {"title": "06:00 to 07:45", "detail": None, "value": "429 SAR", "mark": None}
    odd = [good | {"url": "javascript:alert(1)"}, good | {"label": "Book 17"}, "Book", [good]]
    rows = [row | {"link": good}, row, *(row | {"link": link} for link in odd)]
    shown = _client(tmp_path, [receive(_card(rows=rows))])
    [[name, value]] = shown["events"]
    assert name == "card"
    assert [r["link"] for r in value["rows"]] == [good, None, None, None, None, None]
    assert all({k: v for k, v in r.items() if k != "link"} == row for r in value["rows"])


def test_the_dev_page_and_the_console_show_a_rows_link_after_its_texts(tmp_path: Path) -> None:
    rows = (
        CardRow(title="06:00 to 07:45", value="429 SAR", link=CardLink(label=MARKUP, url=URL)),
        CardRow(title="Total", value="429 SAR"),
    )
    card = wire(ShowCard.of(Card(title="Riyadh to Jeddah", rows=rows)))
    look = {"do": "snapshot", "id": "card"}
    start = [{"do": "click", "id": "start"}, {"do": "open"}]
    dev = browse(
        tmp_path / "dev",
        {"t2v-client.js": CLIENT},
        entry="t2v-client.js",
        page=DEV_PAGE,
        location="http://127.0.0.1:7860/voice/dev",
        steps=[*start, receive(card), look],
    )
    console = _console(tmp_path / "console", [*start, receive(card), look])
    for shown in (dev, console):
        (snapshot,) = shown["snapshots"]
        listed = next(e for e in descendants(snapshot) if e["tag"] == "ul")
        first, second = listed["children"]
        [link] = _links(first)
        assert link["attrs"] == {"dir": "auto", "href": URL} | OPENS
        assert text(link) == MARKUP
        assert text(first) == f"06:00 to 07:45 · 429 SAR {MARKUP}"
        assert _links(second) == []

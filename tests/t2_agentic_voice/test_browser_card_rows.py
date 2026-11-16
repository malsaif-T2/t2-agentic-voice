"""A card's option rows on the browser side: the reference client `api/static/t2v-client.js`
hands the page each row as `CardRow` holds it (a title, a detail, a value and a mark of the
closed set), drops a row that is not one and keeps at most eight, and gives a card from a session
that sends none an empty list; the dev page shows each row as one line of text, its mark as the
line's `data-mark`, never as markup. Run in the fake browser (tests/browser.py)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from t2_agentic_voice.domain.cards import Card, CardRow
from t2_agentic_voice.voice.protocol import ShowCard, wire

from tests.browser import Shown, Step, browse, descendants, receive, text
from tests.t2_agentic_voice.test_browser_stt_choice import _console

ROOT = Path(__file__).resolve().parents[2]
STATIC = ROOT / "packages" / "t2-agentic-voice" / "src" / "t2_agentic_voice" / "api" / "static"
CLIENT = STATIC / "t2v-client.js"
DEV_PAGE = STATIC / "dev.html"
START = [{"do": "start"}, {"do": "open"}]
IMAGE = "<img src=x onerror=alert(1)>"


def _client(folder: Path, steps: list[Step]) -> Shown:
    return browse(
        folder,
        {"t2v-client.js": CLIENT},
        entry="t2v-client.js",
        location="http://127.0.0.1:7860/",
        steps=[*START, *steps],
    )


def _row(**given: Any) -> dict[str, Any]:
    return {"title": "09:10 to 16:15", "detail": None, "value": None, "mark": None} | given


def test_the_client_hands_the_page_each_row_as_the_session_sent_it(tmp_path: Path) -> None:
    rows = (
        CardRow(title="09:10 to 16:15", detail="flight T2 401", value="2,450 SAR", mark="best"),
        CardRow(title="14:40 to 21:45", mark="unavailable"),
        CardRow(title="الساعة ٩", detail="مباشرة"),
    )
    message = wire(ShowCard.of(Card(title="Riyadh to London", rows=rows)))
    shown = _client(tmp_path, [receive(message)])
    assert shown["events"] == [["card", message]]


def test_the_client_drops_a_row_that_is_not_one_and_keeps_at_most_eight(tmp_path: Path) -> None:
    good = _row()
    broken = [
        "a row",
        None,
        [good],
        {k: v for k, v in good.items() if k != "title"},
        _row(title=""),
        _row(title="   "),
        _row(title=5),
        _row(title="x" * 81),
        _row(detail="x" * 121),
        _row(value="x" * 41),
        _row(detail=7),
        _row(mark="top"),  # not one of the closed set
        _row(mark="<b>best</b>"),
    ]
    card = {"v": 1, "type": "card", "title": "x", "steps": [], "source": None}
    sparse = {"title": "x" * 80}  # a row with no detail, value or mark: each null
    kept = [*broken, good | {"mark": "chosen"}, sparse, *([good] * 9)]
    shown = _client(tmp_path, [receive(card | {"rows": kept})])
    [[name, value]] = shown["events"]
    assert name == "card"
    assert value["rows"] == [good | {"mark": "chosen"}, _row(title="x" * 80), *([good] * 6)]


def test_the_dev_page_shows_each_row_as_one_line_of_text(tmp_path: Path) -> None:
    rows = (
        CardRow(title=IMAGE, detail="flight T2 401", value="2,450 SAR", mark="best"),
        CardRow(title="14:40 to 21:45"),
    )
    card = ShowCard.of(Card(title="Riyadh to London", steps=("Nonstop",), rows=rows))
    shown = browse(
        tmp_path,
        {"t2v-client.js": CLIENT},
        entry="t2v-client.js",
        page=DEV_PAGE,
        location="http://127.0.0.1:7860/voice/dev",
        steps=[
            {"do": "click", "id": "start"},
            {"do": "open"},
            receive(wire(card)),
            {"do": "snapshot", "id": "card"},
            receive(wire(ShowCard(title="Your trip", steps=("One traveler",)))),
            {"do": "snapshot", "id": "card"},
        ],
    )
    with_rows, without = shown["snapshots"]
    title, steps, listed = with_rows["children"]
    assert (title["tag"], steps["tag"], listed["tag"]) == ("h3", "ol", "ul")
    assert [(r["tag"], r["attrs"], text(r)) for r in listed["children"]] == [
        ("li", {"dir": "auto", "data-mark": "best"}, f"{IMAGE} · flight T2 401 · 2,450 SAR"),
        ("li", {"dir": "auto"}, "14:40 to 21:45"),
    ]
    assert {e["tag"] for e in descendants(with_rows)} == {"h3", "ol", "ul", "li"}
    assert [e["tag"] for e in without["children"]] == ["h3", "ol"]  # no rows, no list


def test_the_dev_console_shows_each_row_as_one_line_of_text(tmp_path: Path) -> None:
    rows = (CardRow(title=IMAGE, value="2,450 SAR", mark="chosen"), CardRow(title="14:40"))
    card = ShowCard.of(Card(title="Riyadh to London", rows=rows))
    look = {"do": "snapshot", "id": "card"}
    steps = [{"do": "click", "id": "start"}, {"do": "open"}, receive(wire(card)), look]
    plain = ShowCard(title="Your trip", steps=("One traveler",))
    shown = _console(tmp_path, [*steps, receive(wire(plain)), look])
    with_rows, without = shown["snapshots"]
    title, steps_list, listed = with_rows["children"]
    assert (title["tag"], steps_list["tag"], listed["tag"]) == ("h3", "ol", "ul")
    assert [(r["attrs"], text(r)) for r in listed["children"]] == [
        ({"dir": "auto", "data-mark": "chosen"}, f"{IMAGE} · 2,450 SAR"),
        ({"dir": "auto"}, "14:40"),
    ]
    assert {e["tag"] for e in descendants(with_rows)} == {"h3", "ol", "ul", "li"}
    assert [e["tag"] for e in without["children"]] == ["h3", "ol"]

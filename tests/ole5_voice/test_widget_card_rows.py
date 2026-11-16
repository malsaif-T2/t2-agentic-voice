"""Ole5's widget shows a card's option rows (the library's `CardRow`) when a card has them: a
list between the steps and the source, each row one line of text in its own direction, its mark
as the line's `data-mark` for widget.css, never as markup; a card with no rows shows as it did
(test_widget_cards.py), and the next card drops the last one's rows. Run in the fake browser
(tests/browser.py) on the widget's own page."""

from __future__ import annotations

from pathlib import Path

from ole5_voice.server import WEB
from t2_agentic_voice import Card, CardRow
from t2_agentic_voice.voice.protocol import ShowCard, wire

from tests.browser import descendants, receive, text
from tests.ole5_voice.test_widget_cards import _call, _widget

SCRIPT = "<script>alert(1)</script>"


def test_a_cards_rows_show_as_text_between_its_steps_and_its_source(tmp_path: Path) -> None:
    rows = (
        CardRow(title="الخطة الأساسية", detail=SCRIPT, value="٤٩ ريال", mark="best"),
        CardRow(title="Business plan", mark="unavailable"),
        CardRow(title="Your plan", mark="chosen"),
    )
    first = ShowCard.of(Card(title="Plans", steps=("Pick one",), rows=rows, source="plans.pdf"))
    second = ShowCard(title="Archive a ticket", steps=("Open the ticket",))
    look = {"do": "snapshot", "id": "card"}
    shown = _widget(tmp_path, _call(receive(wire(first)), look, receive(wire(second)), look))
    with_rows, without = shown["snapshots"]
    title, steps, listed, source = with_rows["children"]
    assert (title["attrs"]["id"], steps["attrs"]["id"], source["attrs"]["id"]) == (
        "card-title",
        "card-steps",
        "card-source",
    )
    assert (listed["tag"], listed["attrs"]) == ("ul", {"class": "rows"})
    assert [(r["tag"], r["attrs"], text(r)) for r in listed["children"]] == [
        ("li", {"dir": "auto", "data-mark": "best"}, f"الخطة الأساسية · {SCRIPT} · ٤٩ ريال"),
        ("li", {"dir": "auto", "data-mark": "unavailable"}, "Business plan"),
        ("li", {"dir": "auto", "data-mark": "chosen"}, "Your plan"),
    ]
    assert "script" not in {e["tag"] for e in descendants(with_rows)}
    assert [e["attrs"].get("id") for e in without["children"]] == [
        "card-title",
        "card-steps",
        "card-source",
    ]


def test_each_mark_has_a_style_and_none_is_physical() -> None:
    css = (WEB / "widget.css").read_text(encoding="utf-8")
    for mark in ("best", "chosen", "unavailable"):
        assert f'.card .rows li[data-mark="{mark}"]' in css
    rules = css[css.index(".card .rows") : css.index(".message")]
    assert "left" not in rules and "right" not in rules

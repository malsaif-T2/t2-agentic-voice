"""The browser side of plan 006's cards and `thinking`: the reference client
`api/static/t2v-client.js` hands the page every message of the session's, a `card` (voice/
protocol.py's `ShowCard`) as one `card` event and a `state` among t2v/1's four, `thinking`
included, and drops a card or a state that is not one; the dev page shows the agent's state and
its newest card above the captions, in place of the last, each line in its own direction, kept
once the call ends and cleared by a new call, every text of it as text, never as markup. Run in
the fake browser (tests/browser.py) with the session's messages as voice/protocol.py writes
them."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from t2_agentic_voice.voice.protocol import (
    SESSION_MESSAGES,
    Caption,
    Duck,
    Ended,
    Notice,
    SessionHello,
    SessionMessage,
    ShowCard,
    State,
    Unduck,
    wire,
)

from tests.browser import Shown, Step, browse, descendants, receive, text

ROOT = Path(__file__).resolve().parents[2]
STATIC = ROOT / "packages" / "t2-agentic-voice" / "src" / "t2_agentic_voice" / "api" / "static"
CLIENT = STATIC / "t2v-client.js"
DEV_PAGE = STATIC / "dev.html"
FIXTURE = Path(__file__).parent / "fixtures" / "t2v_protocol.json"
START = [{"do": "start"}, {"do": "open"}]
# A card's text as a page could take it for markup, which shows as text.
SCRIPT = "<script>alert(1)</script>"
BOLD = "<b>Open</b> Settings, then <i>Security</i>"
IMAGE = "<img src=x onerror=alert(1)>"


def _client(folder: Path, steps: list[Step]) -> Shown:
    return browse(
        folder,
        {"t2v-client.js": CLIENT},
        entry="t2v-client.js",
        location="http://127.0.0.1:7860/",
        steps=[*START, *steps],
    )


def _dev_page(folder: Path, steps: list[Step]) -> Shown:
    return browse(
        folder,
        {"t2v-client.js": CLIENT},
        entry="t2v-client.js",
        page=DEV_PAGE,
        location="http://127.0.0.1:7860/voice/dev",
        steps=steps,
    )


def _one_of_each() -> list[SessionMessage]:
    return [
        SessionHello(call_id="c-1", languages=("ar-SA", "en")),
        State(state="thinking"),
        Caption(speaker="agent", text="افتح الإعدادات", final=True, reply_id=0, clause=0),
        ShowCard(title="Reset a password", steps=("Open Settings", "افتح الأمان"), source="a.pdf"),
        Duck(level=0.25),
        Unduck(),
        Notice(kind="busy", text="Busy now."),
        Ended(reason="hangup"),
    ]


def test_the_client_hands_the_page_every_message_of_the_sessions(tmp_path: Path) -> None:
    messages = _one_of_each()
    assert [type(m) for m in messages] == list(SESSION_MESSAGES)
    shown = _client(tmp_path, [receive(wire(m)) for m in messages])
    events = [(name, value) for name, value in shown["events"] if name != "volume"]
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))["data_channel"]
    assert [name for name, _ in events] == list(fixture["session_to_client"])
    # Each as the session sent it, the card as one event with its title, steps and source; the
    # call's end as the client's own `ended`, with the session's reason.
    assert [value for _, value in events[:-1]] == [wire(m) for m in messages[:-1]]
    assert events[-1] == ("ended", {"reason": "hangup"})
    assert [v["level"] for name, v in shown["events"] if name == "volume"] == [0.25, 1]


def test_the_client_drops_a_card_or_a_state_that_is_not_one(tmp_path: Path) -> None:
    card = {"v": 1, "type": "card", "title": "x", "steps": ["a"], "source": None}
    broken: list[dict[str, Any]] = [
        card | {"title": ""},
        card | {"title": 5},
        {k: v for k, v in card.items() if k != "title"},
        card | {"steps": "a"},
        card | {"steps": ["a", 1]},
        {k: v for k, v in card.items() if k != "steps"},
        card | {"source": 5},
        {k: v for k, v in card.items() if k != "source"},
        card | {"v": 2},
        card | {"rows": "a"},
        {"v": 1, "type": "state", "state": "dozing"},
        {"v": 1, "type": "state", "state": 1},
        {"v": 1, "type": "state"},
        {"v": 1, "type": "toast", "text": "x"},
    ]
    kept = [card | {"steps": [], "source": "a.pdf"}, {"v": 1, "type": "state", "state": "thinking"}]
    shown = _client(tmp_path, [receive(message) for message in [*broken, *kept]])
    # A card from a session that sends no rows has none (test_browser_card_rows.py).
    assert shown["events"] == [["card", kept[0] | {"rows": []}], ["state", kept[1]]]


def test_the_dev_page_shows_the_newest_card_as_text_and_a_new_call_clears_it(
    tmp_path: Path,
) -> None:
    first = ShowCard(title=SCRIPT, steps=(BOLD, "افتح <i>الأمان</i>", "Done."), source=IMAGE)
    second = ShowCard(title="أرشفة تذكرة", steps=("افتح التذكرة",))
    snapshot = {"do": "snapshot", "id": "card"}
    shown = _dev_page(
        tmp_path,
        [
            {"do": "click", "id": "start"},
            {"do": "open"},
            receive(wire(State(state="thinking"))),
            {"do": "snapshot", "id": "state"},
            receive(wire(first)),
            snapshot,
            receive(wire(second)),
            snapshot,
            receive(wire(Ended(reason="hangup"))),
            snapshot,
            {"do": "click", "id": "start"},
            snapshot,
        ],
    )
    state, shown_first, shown_second, after_the_end, new_call = shown["snapshots"]
    assert text(state) == "thinking"
    title, steps, source = shown_first["children"]
    assert (title["tag"], title["attrs"], text(title)) == ("h3", {"dir": "auto"}, SCRIPT)
    assert (steps["tag"], steps["attrs"]) == ("ol", {})
    assert [(s["tag"], s["attrs"], text(s)) for s in steps["children"]] == [
        ("li", {"dir": "auto"}, BOLD),
        ("li", {"dir": "auto"}, "افتح <i>الأمان</i>"),
        ("li", {"dir": "auto"}, "Done."),
    ]
    assert (source["tag"], text(source)) == ("p", f"Source: {IMAGE}")
    # Nothing of the card's text became an element.
    assert {e["tag"] for e in descendants(shown_first)} == {"h3", "ol", "li", "p"}
    # The second card in place of the first, with no source line when it has none.
    assert [e["tag"] for e in shown_second["children"]] == ["h3", "ol"]
    assert text(shown_second) == "أرشفة تذكرةافتح التذكرة"
    assert after_the_end == shown_second
    assert new_call["children"] == []


def test_the_dev_page_holds_the_card_above_the_captions() -> None:
    page = DEV_PAGE.read_text(encoding="utf-8")
    assert page.index('<section id="card"') < page.index('<ol id="captions"')
    source = CLIENT.read_text(encoding="utf-8")
    dev = source[source.index("function devPage(page) {") :]
    assert "          card,\n" in dev  # the client's `card` event, to the page's `card`

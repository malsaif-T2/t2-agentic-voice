"""Ole5's widget in plan 006: the agent's `thinking` on the state line, beside a dot
that pulses (still for a caller who asks for less motion), and a reply's card above the
captions: its title, its steps numbered and its source with the label in the widget's language,
each line in the direction of its own first strong character (`dir="auto"`: an Arabic step right
to left, an English one left to right, in either language), a new card in place of the last,
kept once the call ends and cleared by a new call, every text of it as text, never as markup.
Run in the fake browser (tests/browser.py) on the widget's own page, with the library's client
where the app's server serves it; the styles read as text."""

from __future__ import annotations

from pathlib import Path

from ole5_voice.server import VOICE_PREFIX, WEB
from t2_agentic_voice.voice.protocol import Ended, ShowCard, State, wire

from tests.browser import Shown, Step, browse, descendants, receive, text

ROOT = Path(__file__).resolve().parents[2]
CLIENT = (
    ROOT / "packages" / "t2-agentic-voice" / "src" / "t2_agentic_voice" / "api" / "static"
) / "t2v-client.js"
SCRIPT = "<script>alert(1)</script>"
STEPS = (
    "افتح <b>Settings</b> ثم اختر الأمان",
    "Choose Reset password",
    "<img src=x onerror=alert(1)>",
)


def _widget(folder: Path, steps: list[Step]) -> Shown:
    return browse(
        folder,
        {"widget.js": WEB / "widget.js", f"{VOICE_PREFIX[1:]}/client/1/t2v-client.js": CLIENT},
        entry="widget.js",
        page=WEB / "index.html",
        location="http://127.0.0.1:7861/",
        steps=steps,
    )


def _call(*steps: Step) -> list[Step]:
    """A made-up code typed and the call started, then `steps`."""
    return [
        {"do": "set", "id": "code", "value": "made-up-code"},
        {"do": "click", "id": "start"},
        {"do": "open"},
        *steps,
    ]


def test_the_state_line_shows_thinking_and_the_call_s_end_clears_it(tmp_path: Path) -> None:
    look = {"do": "snapshot", "id": "state"}
    shown = _widget(
        tmp_path,
        _call(
            receive(wire(State(state="thinking"))),
            look,
            receive(wire(State(state="speaking"))),
            look,
            receive(wire(Ended(reason="hangup"))),
            look,
        ),
    )
    thinking, speaking, ended = shown["snapshots"]
    assert (text(thinking), thinking["attrs"]["data-state"]) == ("يفكر", "thinking")
    assert (text(speaking), speaking["attrs"]["data-state"]) == ("يتكلم", "speaking")
    assert (text(ended), ended["attrs"]["data-state"]) == ("انتهت المكالمة.", "")
    style = (WEB / "widget.css").read_text(encoding="utf-8")
    assert '.state[data-state="thinking"]::before {' in style
    assert "animation: thinking 0.9s ease-in-out infinite alternate;" in style
    calm = style[style.index("@media (prefers-reduced-motion: reduce) {") :]
    assert '.state[data-state="thinking"]::before { animation: none; }' in calm


def test_the_card_shows_its_text_as_text_each_line_in_its_own_direction(tmp_path: Path) -> None:
    first = ShowCard(title=SCRIPT, steps=STEPS, source="دليل Ole5.pdf")
    second = ShowCard(title="Archive a ticket", steps=("Open the ticket",))
    look = {"do": "snapshot", "id": "card"}
    shown = _widget(
        tmp_path,
        [
            {"do": "snapshot", "id": "card"},
            *_call(receive(wire(first)), look, receive(wire(second)), look),
            receive(wire(Ended(reason="hangup"))),
            look,
            {"do": "click", "id": "start"},
            look,
        ],
    )
    before, shown_first, shown_second, after_the_end, new_call = shown["snapshots"]
    assert "hidden" in before["attrs"]
    assert "hidden" not in shown_first["attrs"]
    title, steps, source = shown_first["children"]
    assert (title["attrs"]["id"], title["attrs"]["dir"], text(title)) == (
        "card-title",
        "auto",
        SCRIPT,
    )
    assert [(s["tag"], s["attrs"], text(s)) for s in steps["children"]] == [
        ("li", {"dir": "auto"}, step) for step in STEPS
    ]
    assert "hidden" not in source["attrs"]
    label, name = source["children"]
    assert (text(label), name["attrs"]["dir"], text(name)) == ("المصدر:", "auto", "دليل Ole5.pdf")
    # Nothing of the card's text became an element: only the page's own and the steps.
    assert [e["tag"] for e in descendants(shown_first)] == [
        "h2",
        "ol",
        *["li"] * 3,
        "p",
        "span",
        "span",
    ]
    # The second card in place of the first, its source line hidden when it has none.
    title, steps, source = shown_second["children"]
    assert (text(title), [text(s) for s in steps["children"]]) == (
        "Archive a ticket",
        ["Open the ticket"],
    )
    assert "hidden" in source["attrs"] and text(source) == "المصدر:"
    assert after_the_end == shown_second
    assert "hidden" in new_call["attrs"] and text(new_call) == "المصدر:"


def test_the_source_s_label_follows_the_widget_s_language(tmp_path: Path) -> None:
    card = ShowCard(title="Reset a password", steps=("Open Settings",), source="guide.pdf")
    shown = _widget(
        tmp_path,
        [
            {"do": "click", "query": ["button.language", 1]},
            *_call(receive(wire(card)), {"do": "snapshot", "id": "card-source"}),
        ],
    )
    [source] = shown["snapshots"]
    assert text(source) == "Source:guide.pdf"


def test_the_card_sits_above_the_captions_and_wraps_on_a_phone() -> None:
    page = (WEB / "index.html").read_text(encoding="utf-8")
    assert page.index('<p id="message"') < page.index('<section id="card"')
    assert page.index('<section id="card"') < page.index('<ol id="captions"')
    style = (WEB / "widget.css").read_text(encoding="utf-8")
    card = style[style.index(".card {") :]
    assert "overflow-wrap: anywhere;" in card[: card.index("}")]
    # Each number in its step's own margin, on the side the step's direction starts.
    assert ".card .steps li { margin-block: 4px; margin-inline-start: 1.8em; }" in style
    assert ".card .steps { margin: 0; padding: 0; }" in style

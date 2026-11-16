"""The flight agent's page (apps/flight-voice-agent/web/), run in the fake browser
(tests/browser.py) on its own markup, with the library's client where the server serves it: the
page right to left in Arabic and left to right in English, its toggle setting the call's starting
language; the profile's names and the lines the caller could say shown as text; the orb and the
state line following the call's state; cards newest first, at most three, each line `dir="auto"`,
every text as text, never as markup; "Your trips" listed and filtered by reference on the page;
"Start over" asking first; and no call started without the access code."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from flight_voice.server import VOICE_PREFIX, WEB
from t2_agentic_voice.voice.protocol import ShowCard, State, wire

from tests.browser import Shown, Step, browse, descendants, receive, text

ROOT = Path(__file__).resolve().parents[2]
CLIENT = (
    ROOT / "packages" / "t2-agentic-voice" / "src" / "t2_agentic_voice" / "api" / "static"
) / "t2v-client.js"
SCRIPT = "<script>alert(1)</script>"
PROFILE = {
    "first_name": {"ar": "خالد", "en": SCRIPT},
    "tier": {"ar": "ذهبي", "en": "Gold"},
    "persona": {"ar": "سعد", "en": "Saad"},
    "airline": {"ar": "طيران تي تو", "en": "T2 Air"},
    "lines": {"ar": ["ودي أرجع لدبي"], "en": ["Back to Dubai", "<b>Business</b> to Paris"]},
}
TRIP = {
    "from": {"ar": "الرياض", "en": "Riyadh"},
    "to": {"ar": "دبي", "en": "Dubai"},
    "travelers": 1,
    "cabin": "economy",
    "flown": False,
}
BOOKINGS = {
    "bookings": [
        TRIP
        | {"reference": "731205", "depart": "2026-11-17", "return_date": None, "total_sar": 640},
        TRIP
        | {
            "reference": "482913",
            "depart": "2026-10-08",
            "return_date": "2026-10-11",
            "total_sar": 1380,
            "flown": True,
        },
    ]
}
ANSWERS = {
    "GET profile": [200, PROFILE],
    "GET bookings": [200, BOOKINGS],
    "POST reset": [200, {"reset": True}],
}
ENGLISH = {"do": "click", "query": ["button.language", 1]}


def _page(folder: Path, steps: list[Step], answers: dict[str, Any] | None = None) -> Shown:
    names = ("app.js", "cards.js", "bookings.js", "texts.js")
    files = {name: WEB / name for name in names}
    files[f"{VOICE_PREFIX[1:]}/client/1/t2v-client.js"] = CLIENT
    return browse(
        folder,
        files,
        entry="app.js",
        page=WEB / "index.html",
        location="http://127.0.0.1:7862/",
        steps=steps,
        answers=ANSWERS if answers is None else answers,
    )


def _call(*steps: Step) -> list[Step]:
    return [
        {"do": "set", "id": "code", "value": "made-up-code"},
        {"do": "click", "id": "start"},
        {"do": "open"},
        *steps,
    ]


def _look(name: str) -> Step:
    return {"do": "snapshot", "id": name}


def _html() -> Step:
    return {"do": "snapshot", "query": ["html", 0]}


def test_the_page_is_arabic_right_to_left_and_the_toggle_sets_the_calls_language(
    tmp_path: Path,
) -> None:
    shown = _page(tmp_path, [_html(), _look("heading"), ENGLISH, _html(), *_call()])
    arabic, heading, english = shown["snapshots"]
    assert (arabic["attrs"]["lang"], arabic["attrs"]["dir"]) == ("ar", "rtl")
    assert text(heading) == "وين ناوي تسافر يا خالد؟"
    assert (english["attrs"]["lang"], english["attrs"]["dir"]) == ("en", "ltr")
    (join,) = [r for r in shown["requests"] if r["path"] == "/voice/join"]
    assert join["body"]["language"] == "en"
    (minted,) = [r for r in shown["requests"] if r["path"] == "/token"]
    assert minted["body"]["code"] == "made-up-code"


def test_the_profiles_texts_are_shown_as_text(tmp_path: Path) -> None:
    shown = _page(tmp_path, [ENGLISH, _look("heading"), _look("lines"), _look("traveler")])
    heading, lines, traveler = shown["snapshots"]
    assert text(heading) == f"Where are you flying, {SCRIPT}?"
    assert heading["children"] == [{"text": f"Where are you flying, {SCRIPT}?"}]
    assert [text(li) for li in lines["children"]] == [
        "“Back to Dubai”",
        "“<b>Business</b> to Paris”",
    ]
    assert all(li["attrs"] == {"dir": "auto"} for li in lines["children"])
    assert [e["tag"] for e in descendants(lines)] == ["li", "li"]
    assert text(traveler) == f"{SCRIPT} · Gold"


def test_the_orb_and_the_state_line_follow_the_call(tmp_path: Path) -> None:
    shown = _page(
        tmp_path,
        _call(receive(wire(State(state="confirming"))), _look("orb"), _look("state")),
    )
    orb, state = shown["snapshots"]
    assert orb["attrs"]["data-state"] == "confirming"
    assert text(state) == "ينتظر موافقتك"


def test_cards_are_newest_first_at_most_three_every_text_as_text(tmp_path: Path) -> None:
    sent = [
        ShowCard(title=SCRIPT, steps=("<img src=x onerror=alert(1)>", "09:10 to 16:15")),
        ShowCard(title="الرياض إلى لندن، الخميس ١٧ ديسمبر", steps=("٠٩:١٠ إلى ١٦:١٥",)),
        ShowCard(title="Your trip", steps=("Total 5,120 SAR",)),
        ShowCard(title="Cabins on flight T2 401", steps=("Economy for 2,450 SAR",)),
    ]
    shown = _page(
        tmp_path,
        [
            _look("cards-section"),
            *_call(*(receive(wire(card)) for card in sent), _look("cards-section")),
        ],
    )
    before, after = shown["snapshots"]
    assert "hidden" in before["attrs"]
    assert "hidden" not in after["attrs"]
    (_, listed) = after["children"]
    items = listed["children"]
    assert [text(item["children"][0]) for item in items] == [
        "Cabins on flight T2 401",
        "Your trip",
        "الرياض إلى لندن، الخميس ١٧ ديسمبر",
    ]
    for item in items:
        title, lines = item["children"]
        assert title["attrs"]["dir"] == "auto"
        assert all(line["attrs"] == {"dir": "auto"} for line in lines["children"])
    shown = _page(tmp_path / "again", _call(receive(wire(sent[0])), _look("cards")))
    (only,) = shown["snapshots"][0]["children"]
    title, lines = only["children"]
    assert text(title) == SCRIPT
    assert [text(line) for line in lines["children"]] == list(sent[0].steps)
    assert [e["tag"] for e in descendants(only)] == ["h3", "ul", "li", "li"]


def test_your_trips_lists_the_bookings_and_filters_them_by_reference(tmp_path: Path) -> None:
    shown = _page(
        tmp_path,
        [
            ENGLISH,
            {"do": "click", "id": "trips-toggle"},
            _look("trips"),
            _look("trips-list"),
            {"do": "set", "id": "trips-filter", "value": "4829"},
            {"do": "change", "id": "trips-filter"},
            _look("trips-list"),
            {"do": "set", "id": "trips-filter", "value": "999"},
            {"do": "change", "id": "trips-filter"},
            _look("trips-list"),
            _look("trips-note"),
        ],
    )
    panel, both, filtered, none, note = shown["snapshots"]
    assert "hidden" not in panel["attrs"]
    first, second = both["children"]
    assert [text(line) for line in first["children"]] == [
        "Riyadh to Dubai",
        "One way · 2026-11-17",
        "1 traveler · Economy",
        "640 SAR · Reference 731205",
        "Booked",
    ]
    assert text(second["children"][1]) == "Round trip · 2026-10-08 – 2026-10-11"
    assert second["attrs"]["class"] == "trip flown"
    assert [text(item["children"][-1]) for item in filtered["children"]] == ["Past trip"]
    assert none["children"] == []
    assert text(note) == "No trip has that reference."
    assert [r["path"] for r in shown["requests"]].count("/api/bookings") >= 1


def test_start_over_asks_first_and_resets_only_on_yes(tmp_path: Path) -> None:
    shown = _page(
        tmp_path,
        [
            {"do": "click", "id": "start-over"},
            _look("reset-ask"),
            {"do": "click", "id": "reset-no"},
            _look("reset-ask"),
            {"do": "click", "id": "start-over"},
            {"do": "click", "id": "reset-yes"},
            _look("reset-ask"),
        ],
    )
    asked, kept, done = shown["snapshots"]
    assert "hidden" not in asked["attrs"]
    assert text(asked["children"][0]) == "نمسح الرحلات المحجوزة في هذه التجربة؟"
    assert "hidden" in kept["attrs"] and "hidden" in done["attrs"]
    resets = [r for r in shown["requests"] if r["path"] == "/api/demo/reset"]
    assert [(r["method"], r["body"]) for r in resets] == [("POST", {})]


def test_no_call_starts_without_the_access_code(tmp_path: Path) -> None:
    shown = _page(tmp_path, [{"do": "click", "id": "start"}, _look("message"), _look("options")])
    said, options = shown["snapshots"]
    assert text(said) == "اكتب رمز الدخول في الخيارات، ثم ابدأ المكالمة."
    assert "open" in options["attrs"]
    assert not [r for r in shown["requests"] if r["path"] == "/token"]

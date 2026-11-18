"""The flight agent's page (apps/flight-voice-agent/web/), run in the fake browser
(tests/browser.py) on its own markup, with the library's client where the server serves it: the
page right to left in Arabic and left to right in English, its toggle setting the call's starting
language; the profile's names and the lines the caller could say shown as text; the orb and the
state line following the call's state; a card's option rows in place of its steps, each part as
text and its mark as `data-mark` with the page's own word for it, a mark not in the set dropped
(the segments the cards fill are test_page_segments.py's); "Your trips" listed and filtered by
reference on the page; "Start over" asking first; a line that books nothing (real flights)
naming no traveler, asking anyone where to fly, branding the assistant with its company and
asking no booking route; a flight row's airline apart from its times; the one round button
starting, then ending the call; and no call started without the access code."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from t2_agentic_voice import CardRow
from t2_agentic_voice.voice.protocol import Ended, ShowCard, State, wire

from tests.browser import descendants, receive, text
from tests.flight_voice.page_support import (
    ANSWERS,
    ENGLISH,
    REAL,
    SCRIPT,
    call,
    html,
    look,
    page,
)


def test_the_page_is_arabic_right_to_left_and_the_toggle_sets_the_calls_language(
    tmp_path: Path,
) -> None:
    shown = page(tmp_path, [html(), look("heading"), ENGLISH, html(), *call()])
    arabic, heading, english = shown["snapshots"]
    assert (arabic["attrs"]["lang"], arabic["attrs"]["dir"]) == ("ar", "rtl")
    assert text(heading) == "وين ناوي تسافر يا خالد؟"
    assert (english["attrs"]["lang"], english["attrs"]["dir"]) == ("en", "ltr")
    (join,) = [r for r in shown["requests"] if r["path"] == "/voice/join"]
    assert join["body"]["language"] == "en"
    (minted,) = [r for r in shown["requests"] if r["path"] == "/token"]
    assert minted["body"]["code"] == "made-up-code"


def test_the_profiles_texts_are_shown_as_text(tmp_path: Path) -> None:
    shown = page(tmp_path, [ENGLISH, look("heading"), look("lines"), look("traveler")])
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
    shown = page(
        tmp_path,
        call(receive(wire(State(state="confirming"))), look("orb"), look("state")),
    )
    orb, state = shown["snapshots"]
    assert orb["attrs"]["data-state"] == "confirming"
    assert text(state) == "ينتظر موافقتك"


def test_a_cards_rows_show_their_parts_as_text_and_their_mark_as_data(tmp_path: Path) -> None:
    rows = (
        CardRow(title="09:10 to 13:15", detail=SCRIPT, value="3,560 SAR", mark="best"),
        CardRow(title="14:40 to 18:45", value="3,780 SAR", mark="unavailable"),
        CardRow(title="Riyadh to London, Thu 17 Dec", mark="chosen"),
        CardRow(title="<i>1 traveler</i> in economy"),
    )
    listed = wire(ShowCard(title="Riyadh to London", steps=("not shown",), rows=rows))
    odd = {"title": "a mark not in the set", "detail": None, "value": None, "mark": "<b>"}
    forged = wire(ShowCard(title="Forged", rows=rows[:1], slot="outbound")) | {
        "rows": [odd, wire_row(rows[0])]
    }
    shown = page(
        tmp_path,
        [ENGLISH, *call(receive(forged), receive(listed), look("cards"))],
    )
    (cards,) = shown["snapshots"]
    oldest, newest = cards["children"]
    title, lines = newest["children"]
    assert text(title) == "Riyadh to London" and lines["attrs"]["class"] == "rows"
    best, full, chosen, plain = lines["children"]
    assert best["attrs"] == {"class": "row", "data-mark": "best"}
    assert [(part["attrs"]["class"], text(part)) for part in best["children"]] == [
        ("row-title", "09:10 to 13:15"),
        ("row-detail", SCRIPT),
        ("row-value", "3,560 SAR"),
        ("row-mark", "Lowest fare"),
    ]
    assert all(part["attrs"]["dir"] == "auto" for part in best["children"])
    assert full["attrs"]["data-mark"] == "unavailable" and text(full).endswith("Not available")
    assert chosen["attrs"]["data-mark"] == "chosen" and text(chosen).endswith("Your pick")
    assert plain["attrs"] == {"class": "row"} and text(plain) == "<i>1 traveler</i> in economy"
    spans = [len(row["children"]) for row in lines["children"]]
    assert spans == [4, 3, 2, 1]
    assert {e["tag"] for e in descendants(lines)} == {"li", "span"}
    (only,) = oldest["children"][1]["children"]  # the client drops a row of no closed mark
    assert only["attrs"]["data-mark"] == "best" and oldest["attrs"]["data-slot"] == "outbound"


def wire_row(row: CardRow) -> dict[str, Any]:
    """`row` as the session's JSON holds it."""
    return row.model_dump(mode="json")


def test_your_trips_lists_the_bookings_and_filters_them_by_reference(tmp_path: Path) -> None:
    shown = page(
        tmp_path,
        [
            ENGLISH,
            {"do": "click", "id": "trips-toggle"},
            look("trips"),
            look("trips-list"),
            {"do": "set", "id": "trips-filter", "value": "4829"},
            {"do": "change", "id": "trips-filter"},
            look("trips-list"),
            {"do": "set", "id": "trips-filter", "value": "999"},
            {"do": "change", "id": "trips-filter"},
            look("trips-list"),
            look("trips-note"),
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
    shown = page(
        tmp_path,
        [
            {"do": "click", "id": "start-over"},
            look("reset-ask"),
            {"do": "click", "id": "reset-no"},
            look("reset-ask"),
            {"do": "click", "id": "start-over"},
            {"do": "click", "id": "reset-yes"},
            look("reset-ask"),
        ],
    )
    asked, kept, done = shown["snapshots"]
    assert "hidden" not in asked["attrs"]
    assert text(asked["children"][0]) == "نمسح الرحلات المحجوزة في هذه التجربة؟"
    assert "hidden" in kept["attrs"] and "hidden" in done["attrs"]
    resets = [r for r in shown["requests"] if r["path"] == "/api/demo/reset"]
    assert [(r["method"], r["body"]) for r in resets] == [("POST", {})]


def test_a_line_that_books_nothing_names_no_traveler_and_asks_no_booking_route(
    tmp_path: Path,
) -> None:
    review = ShowCard(
        title="Your trip", rows=(CardRow(title="Total", value="SAR 499"),), slot="review"
    )
    shown = page(
        tmp_path,
        [
            *(
                look(name)
                for name in ("heading", "brand", "traveler", "trips-toggle", "start-over")
            ),
            {"do": "click", "id": "trips-toggle"},
            {"do": "click", "id": "start-over"},
            {"do": "click", "id": "reset-yes"},
            look("trips"),
            look("reset-ask"),
            ENGLISH,
            look("heading"),
            look("brand"),
            *call(
                look("start"),
                look("end"),
                receive(wire(review)),
                receive(wire(State(state="confirming"))),
                receive(wire(State(state="speaking"))),
                look("cards"),
                receive(wire(Ended(reason="hangup"))),
                look("start"),
                look("end"),
            ),
        ],
        ANSWERS | {"GET profile": [200, REAL]},
    )
    heading, brand, traveler, toggle, start_over, trips, ask, *rest = shown["snapshots"]
    english, english_brand, calling, ending, cards, started, ended = rest
    assert text(heading) == "وين ودك تسافر؟" and text(brand) == "سعد · مساعد الرحلات في تي تو"
    assert text(traveler) == "" and "hidden" in traveler["attrs"]
    assert all("hidden" in each["attrs"] for each in (toggle, start_over, trips, ask))
    assert text(english) == "Where would you like to fly?"
    assert text(english_brand) == "Saad · T2 flight assistant"
    assert "hidden" in calling["attrs"] and "hidden" not in ending["attrs"]  # one round button
    assert "hidden" not in started["attrs"] and "hidden" in ended["attrs"]
    (card,) = cards["children"]
    assert [child["tag"] for child in card["children"]] == ["h3", "ul"]  # no status line
    asked = {r["path"] for r in shown["requests"]}
    assert not asked & {"/api/bookings", "/api/demo/reset"}


def test_a_flight_rows_airline_stands_apart_from_its_times(tmp_path: Path) -> None:
    rows = (
        CardRow(
            title="flyadeal · 08:15 to 10:10",
            detail="F3 111 · 1 h 55 min · nonstop · A320neo",
            value="SAR 499",
            mark="best",
        ),
        CardRow(title="طيران أديل · ٠٨:١٥ إلى ١٠:١٠", value="٤٩٩ ريال"),
        CardRow(title="Booked · Reference 262307"),
    )
    listed = wire(ShowCard(title="Riyadh to Jeddah", rows=rows, slot="outbound"))
    shown = page(
        tmp_path,
        [ENGLISH, *call(receive(listed), look("cards"))],
        ANSWERS | {"GET profile": [200, REAL]},
    )
    (card,) = shown["snapshots"][0]["children"]
    english, arabic, booked = card["children"][1]["children"]
    title, detail, value, mark = english["children"]
    assert title["attrs"]["class"] == "row-title row-flight" and text(title) == rows[0].title
    parts = [(part["attrs"]["class"], text(part)) for part in title["children"]]
    assert parts == [
        ("row-airline", "flyadeal"),
        ("row-sep", " · "),
        ("row-times", "08:15 to 10:10"),
    ]
    assert [text(detail), text(value), text(mark)] == [
        "F3 111 · 1 h 55 min · nonstop · A320neo",
        "SAR 499",
        "Lowest fare",
    ]
    assert [text(part) for part in arabic["children"][0]["children"]] == [
        "طيران أديل",
        " · ",
        "٠٨:١٥ إلى ١٠:١٠",
    ]
    assert booked["children"] == [
        {
            "tag": "span",
            "attrs": {"class": "row-title", "dir": "auto"},
            "children": [{"text": rows[2].title}],
        }
    ]


def test_no_call_starts_without_the_access_code(tmp_path: Path) -> None:
    shown = page(tmp_path, [{"do": "click", "id": "start"}, look("message"), look("options")])
    said, options = shown["snapshots"]
    assert text(said) == "اكتب رمز الدخول في الخيارات، ثم ابدأ المكالمة."
    assert "open" in options["attrs"]
    assert not [r for r in shown["requests"] if r["path"] == "/token"]

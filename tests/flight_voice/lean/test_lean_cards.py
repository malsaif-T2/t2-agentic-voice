"""The lean tools' cards (flight_voice/lean/offer_cards.py): an offer's row says its stops, its
connection's city and wait and a road leg by bus, its airline and flights; two rows sharing their
times are told apart by their flights; a card holds at most eight rows; Arabic cards write their
times, lengths and prices in Arabic-Indic digits; and every number a card shows is in the data."""

from __future__ import annotations

from datetime import datetime

from flight_voice.flight_data.model import Layover
from flight_voice.lean.offer_cards import MAX_ROWS, options_card
from flight_voice.lean.results import option_of

from tests.flight_voice.flight_data.fake import (
    FLYADEAL,
    JEDDAH,
    RIYADH,
    SAUDIA,
    FakePlaces,
    nonstop,
    offer,
    segment,
)
from tests.flight_voice.lean.real_support import OUT, real_call
from tests.flight_voice.tools.tool_support import card_passes

AT = datetime(2026, 12, 3, 8, 15)
PLACES = FakePlaces()


def test_a_row_says_the_stops_the_wait_and_a_road_leg() -> None:
    fast = nonstop(FLYADEAL, "111", ("RUH", "JED"), AT, 115, 899)
    road = offer(
        segment(SAUDIA, "3079", ("RUH", "ULH"), AT.replace(hour=9), 60, bus=True),
        segment(SAUDIA, "8607", ("ULH", "JED"), AT.replace(hour=11), 100),
        layovers=(Layover(airport="ULH", minutes=60),),
        price=1142,
    )
    options = tuple(option_of(o, "en", 1, PLACES.get) for o in (fast, road))
    card = options_card("outbound", options, (RIYADH, JEDDAH), OUT, "economy", "en")
    first, second = card.rows
    assert first.detail == "1 h 55 min, nonstop, flyadeal flight F3 111"
    assert second.detail == (
        "3 h 40 min, 1 stop in Al-Ula, 1 h, partly by bus, Saudia flight SV 3079, SV 8607"
    )
    assert first.mark == "best" and first.value == "899 SAR"
    arabic = tuple(option_of(o, "ar-SA", 1, PLACES.get) for o in (fast, road))
    rows = options_card("outbound", arabic, (RIYADH, JEDDAH), OUT, "economy", "ar-SA").rows
    assert rows[0].detail is not None and "مباشرة" in rows[0].detail
    assert rows[1].detail is not None and "توقف واحد في العلا" in rows[1].detail
    assert rows[1].value == "١٬١٤٢ ريال" and rows[0].title.startswith("٠٨:١٥")


def test_rows_sharing_their_times_are_told_apart_and_a_card_holds_at_most_eight() -> None:
    same = [
        nonstop(c, n, ("RUH", "JED"), AT, 115, 800 + i)
        for i, (c, n) in enumerate([(SAUDIA, "1020"), (FLYADEAL, "111")] * 5)
    ]
    held = {o.id: o for o in same}  # five of each id, kept once
    options = tuple(option_of(o, "en", 1, PLACES.get) for o in held.values())
    titles = [
        r.title
        for r in options_card("outbound", options, (RIYADH, JEDDAH), OUT, "economy", "en").rows
    ]
    assert len(set(titles)) == len(titles) and titles[0].endswith("· SV 1020")
    many = tuple(
        option_of(nonstop(SAUDIA, str(1000 + n), ("RUH", "JED"), AT, 115, 900), "en", 1, PLACES.get)
        for n in range(12)
    )
    kept = option_of(nonstop(SAUDIA, "1", ("JED", "RUH"), AT, 115, 700), "en", 1, PLACES.get)
    card = options_card("return", many, (JEDDAH, RIYADH), OUT, "economy", "en", kept=kept)
    assert len(card.rows) == MAX_ROWS and card.rows[-1].mark == "chosen"


def test_every_number_a_real_card_shows_is_in_its_data() -> None:
    for tag in ("en", "ar-SA"):
        found = real_call(tag=tag).find(destination="London", depart=OUT.isoformat())
        assert found.card is not None and card_passes(found), tag

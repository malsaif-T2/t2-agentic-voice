"""A leg's booking link (flight_data/links.py, D-126): the Google Flights search for the leg, one
way, on its day, filtered to its marketing carrier(s), exactly the form checked in a browser on
2026-11-18; a place is its code with one airport, else its city's English name; a party of two
or more is named; a connection of two carriers gets no airline; the page is English (an Arabic
page is not understood with the English text); the label names the carrier, with no digit and at
most 40 characters, and falls back to a bare label."""

from __future__ import annotations

from datetime import datetime
from urllib.parse import parse_qs, urlsplit

import pytest
from flight_voice.flight_data.links import leg_link, link_label, search_text
from flight_voice.flight_data.model import Carrier, Layover

from tests.flight_voice.flight_data.fake import (
    BRITISH,
    DUBAI,
    FLYNAS,
    JEDDAH,
    LONDON,
    QATAR,
    RIYADH,
    SAUDIA,
    nonstop,
    offer,
    segment,
)

# The link checked in a browser on 2026-11-18 (plan 011's Phase 0): flynas's five flights that day.
CHECKED = (
    "https://www.google.com/travel/flights?q=Flights%20to%20JED%20from%20RUH%20on%202026-11-26"
    "%20one%20way%20on%20flynas&hl=en&curr=SAR&gl=sa"
)
DAY = datetime(2026, 11, 26, 6, 0)


def test_a_nonstop_legs_link_is_the_form_checked_in_a_browser() -> None:
    flight = nonstop(FLYNAS, "17", ("RUH", "JED"), DAY, 105, 429)
    link = leg_link(flight, "en", (RIYADH, JEDDAH))
    assert link.url == CHECKED
    assert link.label == "Book on flynas"
    assert leg_link(flight, "en").url == CHECKED  # no route: the offer's own airports


def test_a_place_of_several_airports_is_its_city_and_the_page_stays_english() -> None:
    flight = nonstop(SAUDIA, "111", ("RUH", "LGW"), DAY, 445, 3519)
    assert search_text(flight, (RIYADH, LONDON)) == (
        "Flights to London from RUH on 2026-11-26 one way on Saudia"
    )
    assert search_text(flight) == "Flights to LGW from RUH on 2026-11-26 one way on Saudia"
    link = leg_link(flight, "ar-SA", (RIYADH, LONDON), leg="outbound")
    asked = parse_qs(urlsplit(link.url).query)
    assert asked == {
        "q": ["Flights to London from RUH on 2026-11-26 one way on Saudia"],
        "hl": ["en"],
        "curr": ["SAR"],
        "gl": ["sa"],
    }
    assert link.label == "احجز الذهاب على السعودية"
    back = nonstop(SAUDIA, "120", ("DXB", "RUH"), DAY, 100, 900)
    assert search_text(back, (DUBAI, RIYADH)).startswith("Flights to RUH from Dubai on ")
    assert leg_link(back, "ar", (DUBAI, RIYADH), leg="return").label == "احجز العودة على السعودية"


def test_a_connection_of_two_carriers_names_none_and_its_label_the_first() -> None:
    by_doha = offer(
        segment(QATAR, "1163", ("RUH", "DOH"), DAY, 90),
        segment(BRITISH, "122", ("DOH", "LHR"), datetime(2026, 11, 26, 9, 0), 420),
        layovers=(Layover(airport="DOH", minutes=90),),
        price=2610,
    )
    # "on Qatar Airways and British Airways" opened Google's home page (checked 2026-11-18).
    assert search_text(by_doha, (RIYADH, LONDON)) == (
        "Flights to London from RUH on 2026-11-26 one way"
    )
    assert leg_link(by_doha, "en", (RIYADH, LONDON)).label == "Book on Qatar Airways"


@pytest.mark.parametrize(
    ("name", "label"),
    [
        ("Jet2", "Book the way back"),  # a digit
        ("Air Seychelles International Airways", "Book the way back"),  # too long
        ("Gulf Air", "Book the way back on Gulf Air"),
    ],
)
def test_a_label_that_would_not_fit_falls_back_to_a_bare_one(name: str, label: str) -> None:
    carrier = Carrier(code="ZZ", name_en=name, name_ar=name)
    flight = nonstop(carrier, "1", ("JED", "RUH"), DAY, 100, 500)
    assert link_label(flight, "en", "return") == label
    assert len(label) <= 40 and not any(c.isdigit() for c in label)
    assert leg_link(flight, "en", leg="return").label == label


def test_a_party_is_named_as_google_reads_it() -> None:
    # "...one way on flynas for 2 adults" priced flynas for two at 858, twice 429 (2026-11-18).
    pair = nonstop(FLYNAS, "17", ("RUH", "JED"), DAY, 105, 858, adults=2)
    assert search_text(pair, (RIYADH, JEDDAH)) == (
        "Flights to JED from RUH on 2026-11-26 one way on flynas for 2 adults"
    )

"""A leg's booking link (flight_data/links.py, D-126): the Google Flights `tfs=` search for the
leg, one way, on its day, from its first airport to its last (never a city), filtered to its
marketing carriers in order, in its cabin and for its adults, exactly as the four links checked
in a browser on 2026-11-19 (round 2's brief, byte for byte); the page in Arabic for an Arabic
reply; the label names the carrier, with no digit and at most 40 characters, and falls back to
a bare label."""

from __future__ import annotations

import base64
from datetime import datetime
from urllib.parse import parse_qs, urlsplit

import pytest
from flight_voice.flight_data.links import GOOGLE_FLIGHTS, leg_link, link_label, tfs
from flight_voice.flight_data.model import Carrier, Layover

from tests.flight_voice.flight_data.fake import (
    BRITISH,
    FLYNAS,
    QATAR,
    SAUDIA,
    nonstop,
    offer,
    segment,
)

DAY = datetime(2026, 11, 26, 6, 0)
# The four links checked in a browser on 2026-11-19 (round 2's brief): their `tfs` values.
RUH_JED_SV_BUSINESS = "Gh4SCjIwMjYtMTEtMjYyAlNWagUSA1JVSHIFEgNKRURAAUgDmAEC"
ELQ_ABT_SV_BUSINESS_TWO = "Gh4SCjIwMjYtMTEtMjYyAlNWagUSA0VMUXIFEgNBQlRAAUABSAOYAQI"
RUH_JED_XY_ECONOMY = "Gh4SCjIwMjYtMTEtMjYyAlhZagUSA1JVSHIFEgNKRURAAUgBmAEC"
RUH_LHR_QR_BA_ECONOMY = "GiISCjIwMjYtMTEtMjYyAlFSMgJCQWoFEgNSVUhyBRIDTEhSQAFIAZgBAg"
# The cheapest flynas flight from Riyadh to Jeddah that day, its link in English.
CHECKED = f"{GOOGLE_FLIGHTS}?tfs={RUH_JED_XY_ECONOMY}&hl=en&curr=SAR&gl=sa"


def _query(url: str) -> dict[str, list[str]]:
    return parse_qs(urlsplit(url).query)


def test_the_four_links_checked_in_a_browser_are_written_byte_for_byte() -> None:
    saudia = nonstop(SAUDIA, "1020", ("RUH", "JED"), DAY, 110, 2913, cabin="business")
    qassim = nonstop(SAUDIA, "1531", ("ELQ", "ABT"), DAY, 95, 5100, cabin="business", adults=2)
    flynas = nonstop(FLYNAS, "17", ("RUH", "JED"), DAY, 105, 429)
    by_doha = offer(
        segment(QATAR, "1163", ("RUH", "DOH"), DAY, 90),
        segment(BRITISH, "122", ("DOH", "LHR"), datetime(2026, 11, 26, 9, 0), 420),
        layovers=(Layover(airport="DOH", minutes=90),),
        price=2610,
    )
    assert tfs(saudia) == RUH_JED_SV_BUSINESS
    assert tfs(qassim) == ELQ_ABT_SV_BUSINESS_TWO  # Qassim to Al Bahah: its destination kept
    assert tfs(flynas) == RUH_JED_XY_ECONOMY
    assert tfs(by_doha) == RUH_LHR_QR_BA_ECONOMY  # both airlines, in order
    assert leg_link(flynas, "en").url == CHECKED
    assert _query(leg_link(saudia, "en").url) == {
        "tfs": [RUH_JED_SV_BUSINESS],
        "hl": ["en"],
        "curr": ["SAR"],
        "gl": ["sa"],
    }


def test_an_arabic_reply_opens_the_arabic_page() -> None:
    flynas = nonstop(FLYNAS, "17", ("RUH", "JED"), DAY, 105, 429)
    for tag in ("ar-SA", "ar"):
        link = leg_link(flynas, tag, leg="outbound")
        assert _query(link.url)["hl"] == ["ar"]
        assert link.label == "احجز الذهاب على طيران ناس"
    assert leg_link(flynas, "en").url.startswith("https://www.google.com/travel/flights/search?")


def test_the_airports_are_the_ones_the_offer_flew_and_each_airline_once() -> None:
    # A connection by one airline names it once; its airports are its first and its last.
    gatwick = offer(
        segment(SAUDIA, "111", ("RUH", "JED"), DAY, 100),
        segment(SAUDIA, "115", ("JED", "LGW"), datetime(2026, 11, 26, 9, 0), 400),
        layovers=(Layover(airport="JED", minutes=80),),
        price=3519,
    )
    message = base64.urlsafe_b64decode(tfs(gatwick) + "==")
    assert message.count(b"SV") == 1
    assert b"\x12\x03RUH" in message and b"\x12\x03LGW" in message and b"JED" not in message


def test_a_connection_of_two_carriers_is_labelled_by_the_first() -> None:
    by_doha = offer(
        segment(QATAR, "1163", ("RUH", "DOH"), DAY, 90),
        segment(BRITISH, "122", ("DOH", "LHR"), datetime(2026, 11, 26, 9, 0), 420),
        layovers=(Layover(airport="DOH", minutes=90),),
        price=2610,
    )
    assert leg_link(by_doha, "en").label == "Book on Qatar Airways"
    assert leg_link(by_doha, "en", label="Book").label == "Book"


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

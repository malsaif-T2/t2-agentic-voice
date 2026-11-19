"""The real network's links (flight_voice/lean/offer_cards.py, D-126, D-130), over the real
answer of RUH-JED on 2026-11-26 replayed and the fake London days: every option row of a
listing carries its flight's link (the `tfs=` search checked in a browser), «احجز» / "Book", its
url in no text the guard or the model reads; the mock's rows carry none."""

from __future__ import annotations

from flight_voice.flight_data.compose import real_places
from flight_voice.flight_data.links import tfs
from flight_voice.flight_data.recorded import recorded
from flight_voice.lean.booking_check import BookingCheck
from flight_voice.lean.deps import LeanDeps
from flight_voice.lean.draft import LeanBook
from flight_voice.said import Tag
from t2_agentic_voice import ToolResult
from t2_agentic_voice.voice.protocol import ShowCard, wire

from tests.flight_voice.flight_data.serpapi_support import FIXTURES
from tests.flight_voice.flight_data.test_links import CHECKED
from tests.flight_voice.lean.lean_support import OUT as MOCK_OUT
from tests.flight_voice.lean.lean_support import LeanCall, ids
from tests.flight_voice.lean.real_support import BACK, OUT, real_call
from tests.flight_voice.tools.tool_support import airline, card_passes, data

DAY = "2026-11-26"


def jeddah(tag: Tag = "en") -> LeanCall:
    """A call on the real network over the recorded RUH-JED answers."""
    places = real_places()
    deps = LeanDeps(
        data=recorded(FIXTURES),
        places=places,
        today=airline().today,
        airline=airline(),
        trips=LeanBook(places.home),
        check=BookingCheck(),
        bookable=False,
        network="real",
    )
    return LeanCall(tag, deps=deps)


def _no_address_read(result: ToolResult) -> None:
    """The links' addresses are on the card alone: in no text the guard reads, nor the data."""
    assert result.card is not None
    assert all("google" not in text for text in (*result.card.texts(), *result.evidence))
    assert "google" not in str(data(result)) and "http" not in str(data(result))


def test_every_flight_row_of_a_real_listing_carries_its_flights_link() -> None:
    call = jeddah()
    found = call.find(destination="Jeddah", depart=DAY)
    assert found.card is not None and card_passes(found)
    options = data(found)["outbound"]["options"]
    offers = {o.id: o for o in call.draft.listed_outbound.offers}  # type: ignore[union-attr]
    for row, option in zip(found.card.rows, options, strict=True):
        assert row.link is not None and row.link.label == "Book"
        assert row.link.url.endswith(f"?tfs={tfs(offers[option['id']])}&hl=en&curr=SAR&gl=sa")
    cheapest = min(options, key=lambda o: o["price"])
    row = found.card.rows[options.index(cheapest)]
    assert row.link is not None and row.link.url == CHECKED  # flynas's, checked in a browser
    _no_address_read(found)
    assert wire(ShowCard.of(found.card))["rows"][0]["link"]["label"] == "Book"


def test_the_return_listing_rows_and_the_kept_pick_carry_links_in_arabic() -> None:
    call = real_call(tag="ar-SA")
    listed = call.find(destination="London", depart=OUT.isoformat(), return_date=BACK.isoformat())
    back = call.choose(outbound_id=ids(listed)[0])
    assert back.card is not None and back.card.slot == "return"
    assert all(row.link is not None for row in back.card.rows)
    assert {row.link.label for row in back.card.rows if row.link} == {"احجز"}
    kept = back.card.rows[-1]
    assert kept.mark == "chosen" and kept.link is not None and "&hl=ar&" in kept.link.url
    _no_address_read(back)


def test_the_mocks_rows_carry_no_link() -> None:
    call = LeanCall()
    found = call.find(destination="Jeddah", depart=MOCK_OUT)
    assert found.card is not None and found.card.rows
    assert all(row.link is None for row in found.card.rows)
    back = call.find(destination="Jeddah", depart=MOCK_OUT, return_date="2026-11-21")
    picked = call.choose(outbound_id=ids(back)[0])
    assert picked.card is not None and all(row.link is None for row in picked.card.rows)

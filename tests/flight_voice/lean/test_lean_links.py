"""The real network's links (flight_voice/lean/offer_cards.py, D-126, D-130), over the real
answer of RUH-JED on 2026-11-26 replayed and the fake London days: every option row of a
listing carries its flight's link (the `tfs=` search checked in a browser), «احجز» / "Book";
the trip card carries one per chosen leg the moment a flight is chosen, with no tool to call,
and `choose_flights` says each chosen leg's link is ready; no url is in any text the guard or
the model reads; the real line declares the booking's claims and backs none; the mock's cards
carry no link. And a search's progress line waits about 1.5 s on the real network alone."""

from __future__ import annotations

from typing import Any

from flight_voice.flight_data.compose import real_places
from flight_voice.flight_data.links import tfs
from flight_voice.flight_data.recorded import recorded
from flight_voice.lean.agent import lean_tools
from flight_voice.lean.book import LEAN_CLAIMS
from flight_voice.lean.booking_check import BookingCheck
from flight_voice.lean.deps import LeanDeps
from flight_voice.lean.draft import LeanBook
from flight_voice.persona import PROGRESS_AT_S, PROGRESS_LIVE_AT_S
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
    sent: dict[str, Any] = wire(ShowCard.of(found.card))
    assert sent["rows"][0]["link"]["label"] == "Book"


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


def test_a_one_way_pick_puts_its_link_on_the_trip_card_at_once_and_says_it_is_ready() -> None:
    call = jeddah()
    found = call.find(destination="Jeddah", depart=DAY)
    cheapest = min(data(found)["outbound"]["options"], key=lambda o: o["price"])
    picked = call.choose(outbound_id=cheapest["id"])
    answer = data(picked)
    assert answer["missing"] == [] and answer["total"] == 429
    assert answer["outbound"]["link"] == "ready"
    assert picked.card is not None and picked.card.slot == "review" and card_passes(picked)
    assert [(link.label, link.url) for link in picked.card.links] == [("Book on flynas", CHECKED)]
    assert not picked.done
    _no_address_read(picked)


def test_a_round_trip_gets_a_link_per_chosen_leg_in_the_callers_language() -> None:
    call = real_call(tag="ar-SA")
    listed = call.find(destination="London", depart=OUT.isoformat(), return_date=BACK.isoformat())
    out = call.choose(outbound_id=ids(listed)[0])
    assert data(out)["outbound"]["link"] == "ready"  # its link is on its row beside the return's
    done = call.choose(return_id=ids(out, "return")[0])
    answer = data(done)
    assert (answer["outbound"]["link"], answer["return"]["link"]) == ("ready", "ready")
    assert done.card is not None and done.card.slot == "review"
    out_link, back_link = done.card.links
    assert (out_link.label, back_link.label) == (
        "احجز الذهاب على السعودية",
        "احجز العودة على السعودية",
    )
    went, came = call.draft.legs()
    assert out_link.url.endswith(f"?tfs={tfs(went)}&hl=ar&curr=SAR&gl=sa")
    assert back_link.url.endswith(f"?tfs={tfs(came)}&hl=ar&curr=SAR&gl=sa")
    # The trip made one way after: one link, of the outbound alone, with the bare label.
    call.find(destination="London", depart=OUT.isoformat())
    again = call.choose(outbound_id=ids(listed)[0]).card
    assert again is not None and [link.label for link in again.links] == ["احجز على السعودية"]


def test_the_real_line_claims_no_booking_and_the_mock_says_no_link() -> None:
    real = {t.name: t for t in lean_tools(real_call().deps)}
    assert list(real) == ["find_flights", "choose_flights"]  # no booking_link: no tool to call
    assert real["choose_flights"].claims is LEAN_CLAIMS  # declared, and no result backs one
    assert "book_trip" not in real["choose_flights"].description
    mock = {t.name: t for t in lean_tools(LeanCall().deps)}
    assert list(mock) == ["find_flights", "choose_flights", "book_trip", "traveler_profile"]
    assert mock["choose_flights"].claims is None
    call = LeanCall()
    found = call.find(destination="Jeddah", depart=MOCK_OUT)
    picked = data(call.choose(outbound_id=ids(found)[0]))
    assert "link" not in picked["outbound"]


def test_the_progress_line_waits_on_the_real_network_and_not_on_the_mock() -> None:
    # A day already searched answers from the cache at once: its reply never opens with
    # "let me check" (the owner's calls of 2026-11-19); the mock keeps run F's timing.
    real = {t.name: t for t in lean_tools(real_call().deps)}["find_flights"]
    mock = {t.name: t for t in lean_tools(LeanCall().deps)}["find_flights"]
    assert (real.progress, real.progress_after_s) == ("searching_live", PROGRESS_LIVE_AT_S)
    assert (mock.progress, mock.progress_after_s) == ("searching", PROGRESS_AT_S)
    assert PROGRESS_LIVE_AT_S == 1.5 and PROGRESS_AT_S == 0.1

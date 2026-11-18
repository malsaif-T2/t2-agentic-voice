"""The real network's `booking_link` (flight_voice/lean/booking_link.py, D-126), over the real
answer of RUH-JED on 2026-11-26 replayed and the fake London days: a trip still lacking a leg is
`incomplete` with what is missing; a complete one is `ready`, each leg as the caller heard it and
a note, with the trip's review card carrying one link per leg (the link checked in a browser for
the cheapest flynas flight), its url in no text the guard or the model reads; it is registered
on the real network alone, in place of `book_trip`, and declares the booking's claims with no
result that backs one; the real instructions offer the link after the summary."""

from __future__ import annotations

from typing import Any

from flight_voice.flight_data.compose import real_places
from flight_voice.flight_data.recorded import recorded
from flight_voice.lean.agent import lean_tools
from flight_voice.lean.book import LEAN_CLAIMS
from flight_voice.lean.booking_check import BookingCheck
from flight_voice.lean.booking_link import BOOKING_LINK, READY_NOTE, booking_link
from flight_voice.lean.deps import LeanDeps
from flight_voice.lean.draft import LeanBook
from flight_voice.lean.prompt import instructions
from flight_voice.persona import Names
from flight_voice.said import Tag
from t2_agentic_voice import ToolResult
from t2_agentic_voice.voice.protocol import ShowCard, wire

from tests.flight_voice.flight_data.serpapi_support import FIXTURES
from tests.flight_voice.flight_data.test_links import CHECKED
from tests.flight_voice.lean.lean_support import LeanCall, ids
from tests.flight_voice.lean.real_support import BACK, OUT, real_call
from tests.flight_voice.scenario_dates import TODAY
from tests.flight_voice.tools.tool_support import airline, data, run

DAY = "2026-11-26"


def _jeddah(tag: Tag = "en") -> LeanCall:
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


def _link(call: LeanCall) -> ToolResult:
    return run(booking_link(call.deps), call.tag)


def _cheapest(found: ToolResult) -> dict[str, Any]:
    options: list[dict[str, Any]] = data(found)["outbound"]["options"]
    return min(options, key=lambda o: o["price"])


def test_a_trip_not_complete_answers_what_it_misses() -> None:
    call = _jeddah()
    assert data(_link(call)) == {
        "status": "incomplete",
        "missing": ["destination", "depart", "return_date", "outbound", "return"],
    }
    call.find(destination="Jeddah", depart=DAY)
    assert data(_link(call)) == {"status": "incomplete", "missing": ["outbound"]}


def test_the_cheapest_real_flight_gets_the_link_checked_in_a_browser() -> None:
    call = _jeddah()
    found = call.find(destination="Jeddah", depart=DAY)
    cheapest = _cheapest(found)
    assert (cheapest["airline"], cheapest["price"]) == ("flynas", 429)
    call.choose(outbound_id=cheapest["id"])
    result = _link(call)
    answer = data(result)
    assert answer == {
        "status": "ready",
        "legs": [
            {
                "leg": "outbound",
                "airline": "flynas",
                "flight": cheapest["flight"],
                "flight_said": "flynas " + cheapest["flight"].split()[-1],
                "day": {"date": DAY, "weekday": "Thursday"},
                "departs": cheapest["departs"],
                "price": 429,
            }
        ],
        "note": READY_NOTE,
    }
    assert result.card is not None and result.card.slot == "review"
    assert [(link.label, link.url) for link in result.card.links] == [("Book on flynas", CHECKED)]
    assert not result.done
    # The address is on the card alone: in no text the guard reads, nor in the model's data.
    assert all("google" not in text for text in (*result.card.texts(), *result.evidence))
    assert "google" not in str(answer) and "http" not in str(answer)
    assert wire(ShowCard.of(result.card))["links"] == [{"label": "Book on flynas", "url": CHECKED}]


def test_a_round_trip_gets_a_link_per_leg_in_the_callers_language() -> None:
    call = real_call(tag="ar-SA")
    listed = call.find(destination="London", depart=OUT.isoformat(), return_date=BACK.isoformat())
    out = call.choose(outbound_id=ids(listed)[0])
    call.choose(return_id=ids(out, "return")[0])
    result = _link(call)
    answer = data(result)
    assert answer["status"] == "ready" and [leg["leg"] for leg in answer["legs"]] == [
        "outbound",
        "return",
    ]
    assert answer["legs"][0]["flight_said"].startswith("السعودية ")
    assert result.card is not None
    out_link, back_link = result.card.links
    assert (out_link.label, back_link.label) == (
        "احجز الذهاب على السعودية",
        "احجز العودة على السعودية",
    )
    assert "q=Flights%20to%20London%20from%20RUH%20on%202026-12-03" in out_link.url
    assert "q=Flights%20to%20RUH%20from%20London%20on%202026-12-10" in back_link.url
    assert out_link.url.endswith("&hl=ar&curr=SAR&gl=sa")
    # A trip made one way after: one link, of the outbound alone, with the bare label.
    call.find(destination="London", depart=OUT.isoformat())
    call.choose(outbound_id=ids(listed)[0])
    again = _link(call).card
    assert again is not None and [link.label for link in again.links] == ["احجز على السعودية"]


def test_booking_link_is_the_real_networks_in_place_of_book_trip() -> None:
    real = [t.name for t in lean_tools(real_call().deps)]
    assert real == ["find_flights", "choose_flights", BOOKING_LINK, "traveler_profile"]
    mock = [t.name for t in lean_tools(LeanCall().deps)]
    assert mock == ["find_flights", "choose_flights", "book_trip", "traveler_profile"]
    assert booking_link(real_call().deps).claims is LEAN_CLAIMS  # no booking claim is backed


def test_the_real_instructions_offer_the_link_after_the_summary() -> None:
    last = TODAY.replace(year=TODAY.year + 1)
    real = instructions(Names(), TODAY, last, network="real")
    for tag, text in real.items():
        assert 'offer the link to book it ("Want the link to book it?"' in text, tag
        assert "Call booking_link when the caller agrees or asks for the link" in text
        assert "the airline's own site books it" not in text
    assert "«تبي رابط الحجز؟»" in real["ar-SA"] and "«هل تريد رابط الحجز؟»" in real["ar-SA"]
    for text in instructions(Names(), TODAY, last).values():
        assert "booking_link" not in text

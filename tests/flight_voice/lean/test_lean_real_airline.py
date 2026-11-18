"""An airline the caller names after a listing that left flights out (plan 011: asked "And
flyadeal, what do they have?" after 6 of 15 flights, the model once answered from the 2 flyadeal
flights it was given, of 4), over the real answer of RUH-JED on 2026-11-26 replayed: the day's
answer notes that its options are some of the day's flights and that one airline's come from
find_flights with airline; that search gives all of flyadeal's, with no such note; and the real
instructions say so too."""

from __future__ import annotations

from flight_voice.flight_data.compose import real_places
from flight_voice.flight_data.recorded import recorded
from flight_voice.lean.booking_check import BookingCheck
from flight_voice.lean.deps import LeanDeps
from flight_voice.lean.draft import LeanBook
from flight_voice.lean.find import MORE_REAL
from flight_voice.lean.prompt import instructions
from flight_voice.persona import Names

from tests.flight_voice.flight_data.serpapi_support import FIXTURES
from tests.flight_voice.lean.lean_support import LeanCall
from tests.flight_voice.scenario_dates import TODAY
from tests.flight_voice.tools.tool_support import airline, data

DAY = "2026-11-26"


def _call() -> LeanCall:
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
    return LeanCall(deps=deps)


def test_a_listing_that_leaves_flights_out_says_another_search_gives_an_airlines() -> None:
    call = _call()
    answer = data(call.find(destination="Jeddah", depart=DAY))
    day = answer["outbound"]
    assert day["count"] == 22 and len(day["options"]) == 6 and day["more"] == 16
    assert MORE_REAL in answer["note"]
    counted = {a["airline"]: a["flights"] for a in day["airlines"]}
    assert counted == {"Saudia": 11, "flyadeal": 6, "flynas": 5}
    # Each airline's own times, so one airline's question is answered right from the summary.
    adeal = next(a for a in day["airlines"] if a["airline"] == "flyadeal")
    assert (adeal["first_departs"], adeal["last_departs"]) == ("05:20", "18:45")
    assert (adeal["cheapest"], adeal["cheapest_departs"]) == (499, "16:25")
    listed = [o for o in day["options"] if o["airline"] == "flyadeal"]
    assert len(listed) < counted["flyadeal"]  # the listing alone would miss some
    narrowed = data(call.find(destination="Jeddah", depart=DAY, airline="flyadeal"))
    flyadeal = narrowed["outbound"]
    assert flyadeal["count"] == 6 and len(flyadeal["options"]) == 6
    assert {o["airline"] for o in flyadeal["options"]} == {"flyadeal"}
    assert "note" not in narrowed


def test_the_real_listing_line_sends_one_airline_to_another_search() -> None:
    last = TODAY.replace(year=TODAY.year + 1)
    for tag, text in instructions(Names(), TODAY, last, network="real").items():
        assert "The options are only some of the day's flights" in text, tag
        assert "call find_flights again with airline, never answer from the options" in text
    for text in instructions(Names(), TODAY, last).values():
        assert "never answer from the options" not in text

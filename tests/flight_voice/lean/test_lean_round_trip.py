"""A round trip on the real network, its way out first and its way back after it, over the
recorded answers (recorded_support.py), as the owner's calls of 2026-11-22 broke it: the way
out listed, not chosen, then the way back asked as its own search is the trip's return (its
day alone, the way out settled first, the outbound's ids still choosable), and once the way out
is chosen the way back is listed and taken, the total the two prices summed; a return id
before the way out is chosen is `outbound_first`, both in one call allowed; a new destination
keeps the way back's day, searched from it; a search for the way out with no return day keeps
the trip round, and `one_way` makes it one way; the trip's end is noted, one way so far or
both ways chosen. The mock keeps its search as run F reads it."""

from __future__ import annotations

from datetime import date

from flight_voice.lean.agent import lean_tools
from flight_voice.lean.choose_notes import BOTH_CHOSEN, ONE_WAY_SO_FAR
from flight_voice.lean.find_return import BACK_KEPT, RETURN_ADDED, RETURN_ASKED
from flight_voice.lean.find_schema import RETURN, RETURN_REAL
from flight_voice.lean.turnaround import OUTBOUND_FIRST
from flight_voice.lean.weekday import SAID, SAID_BACK, next_weekday

from tests.flight_voice.lean.lean_support import BACK as MOCK_BACK
from tests.flight_voice.lean.lean_support import OUT as MOCK_OUT
from tests.flight_voice.lean.lean_support import LeanCall, ids
from tests.flight_voice.lean.recorded_support import (
    DAY_BACK,
    DAY_OUT,
    MORNING,
    option_ids,
    recorded_call,
)
from tests.flight_voice.tools.tool_support import card_passes, data


def test_the_owners_call_takes_the_way_back_asked_alone_as_the_trips_return() -> None:
    call = recorded_call()
    found = data(call.find(destination="Jeddah", depart=DAY_OUT))  # listed, not chosen
    outs = option_ids(found["outbound"])
    answer = data(call.find(origin="Jeddah", destination="Riyadh", depart=DAY_BACK))
    assert answer["route"] == "Riyadh to Jeddah" and option_ids(answer["outbound"]) == outs
    assert RETURN_ASKED.format(day=DAY_BACK) in answer["note"]
    assert answer["return"]["day"]["date"] == DAY_BACK and answer["return"]["options"]
    assert answer["fares_are"] == "per person, each way, as of now"
    draft = call.draft
    assert not draft.one_way and draft.return_date == date(2026, 11, 29)
    assert draft.listed_return is not None
    flynas = next(o for o in found["outbound"]["options"] if o["airline"] == "flynas")
    picked = call.choose(outbound_id=flynas["id"])  # the listed flynas id: no unknown_id
    so_far = data(picked)
    assert so_far["status"] == "ok" and so_far["missing"] == ["return"]
    listed = so_far["listed"]["return"]
    assert listed["day"]["date"] == DAY_BACK
    assert listed["count"] == len(draft.listed_return.pool)  # a later day: every flight back
    assert picked.card is not None and picked.card.slot == "return" and card_passes(picked)
    back = listed["options"][0]
    done = data(call.choose(return_id=back["id"]))
    assert done["status"] == "ok" and done["missing"] == [] and done["trip"] == "round trip"
    assert done["total"] == flynas["price"] + back["price"] == call.total()
    assert BOTH_CHOSEN in done["note"]


def test_flynas_both_ways_in_one_call_after_the_way_back_was_asked_alone() -> None:
    """The owner's «خل الذهاب مع ناس والعودة مع ناس»: the way back's flights listed when asked,
    both picked in one call, the way out first, the total the tool's."""
    call = recorded_call()
    found = data(call.find(destination="Jeddah", depart=DAY_OUT))
    answer = data(call.find(origin="Jeddah", destination="Riyadh", depart=DAY_BACK))
    out = next(o for o in found["outbound"]["options"] if o["airline"] == "flynas")
    back = next(o for o in answer["return"]["options"] if o["airline"] == "flynas")
    done = data(call.choose(outbound_id=out["id"], return_id=back["id"]))
    assert done["status"] == "ok" and done["missing"] == [] and done["trip"] == "round trip"
    assert done["total"] == out["price"] + back["price"] and BOTH_CHOSEN in done["note"]


def test_the_way_back_asked_after_the_way_out_is_chosen_lists_its_flights() -> None:
    call = recorded_call()
    call.find(destination="Jeddah", depart=DAY_OUT)
    one = data(call.choose(outbound_id=MORNING))
    assert one["missing"] == [] and one["trip"] == "one way" and ONE_WAY_SO_FAR in one["note"]
    back = call.find(origin="Jeddah", destination="Riyadh", depart=DAY_BACK)
    answer = data(back)
    assert answer["chosen"] == {"outbound": MORNING} and RETURN_ADDED in answer["note"]
    assert answer["return"]["day"]["date"] == DAY_BACK and answer["return"]["options"]
    assert back.card is not None and back.card.slot == "return" and card_passes(back)
    assert back.card.rows[-1].mark == "chosen"


def test_a_return_id_before_the_way_out_is_chosen_is_outbound_first() -> None:
    call = recorded_call()
    call.find(destination="Jeddah", depart=DAY_OUT, return_date=DAY_BACK)
    asked = data(call.choose(list_leg="return"))  # the way back asked about first: answered
    back = option_ids(asked["listed"]["return"])[0]
    before = call.draft
    refused = data(call.choose(return_id=back))
    assert refused == {"status": "outbound_first", "note": OUTBOUND_FIRST}
    assert call.draft == before  # an error writes nothing
    both = data(call.choose(outbound_id=MORNING, return_id=back))  # one call: out first
    assert both["missing"] == [] and BOTH_CHOSEN in both["note"]
    assert (both["outbound"]["id"], both["return"]["id"]) == (MORNING, back)


def test_a_new_destination_keeps_the_way_back_on_its_day_from_there() -> None:
    call = recorded_call()
    found = call.find(destination="Jeddah", depart=DAY_OUT, return_date=DAY_BACK)
    out = data(call.choose(outbound_id=ids(found)[0]))
    call.choose(return_id=option_ids(out["listed"]["return"])[0])
    moved = data(call.find(destination="Dubai", depart=DAY_OUT))  # no return_date passed
    assert moved["route"] == "Riyadh to Dubai" and "chosen" not in moved
    assert BACK_KEPT.format(day=DAY_BACK, city="Dubai") in moved["note"]
    assert moved["return"]["day"]["date"] == DAY_BACK
    assert moved["fares_are"] == "per person, each way, as of now"
    draft = call.draft
    assert not draft.one_way and draft.return_date == date(2026, 11, 29)
    assert draft.listed_return is not None
    assert {o.origin for o in draft.listed_return.offers} <= {"DXB", "DWC"}
    assert draft.chosen_outbound is None and draft.chosen_return is None
    picked = data(call.choose(outbound_id=option_ids(moved["outbound"])[0]))
    assert picked["missing"] == ["return"] and picked["route"] == "Riyadh to Dubai"
    assert picked["listed"]["return"]["day"]["date"] == DAY_BACK


def test_a_search_for_the_way_out_alone_keeps_the_trip_round() -> None:
    # The owner's second call: an airline asked for the way out, no return_date, made it one way.
    call = recorded_call()
    call.find(destination="Jeddah", depart=DAY_OUT, return_date=DAY_BACK)
    call.choose(outbound_id=MORNING)
    again = data(call.find(destination="Jeddah", depart=DAY_OUT, airline="flynas"))
    assert again["chosen"] == {"outbound": MORNING}
    assert BACK_KEPT.format(day=DAY_BACK, city="Jeddah") in again["note"]
    assert {o["airline"] for o in again["return"]["options"]} == {"flynas"}
    assert not call.draft.one_way and call.draft.return_date == date(2026, 11, 29)
    arabic = recorded_call("ar-SA")
    arabic.find(destination="جدة", depart=DAY_OUT, return_date=DAY_BACK)
    moved = data(arabic.find(destination="دبي", depart=DAY_OUT))
    assert BACK_KEPT.format(day=DAY_BACK, city="دبي") in moved["note"]


def test_one_way_makes_the_trip_one_way() -> None:
    call = recorded_call()
    call.find(destination="Jeddah", depart=DAY_OUT, return_date=DAY_BACK)
    call.choose(outbound_id=MORNING)
    alone = data(call.find(destination="Jeddah", depart=DAY_OUT, one_way=True))
    assert "return" not in alone and alone["chosen"] == {"outbound": MORNING}
    assert alone["fares_are"] == "per person, as of now"
    assert call.draft.one_way and call.draft.return_date is None
    done = data(call.choose())
    assert done["missing"] == [] and done["trip"] == "one way" and ONE_WAY_SO_FAR in done["note"]
    reverse = data(call.find(origin="Jeddah", destination="Riyadh", depart=DAY_BACK, one_way=True))
    # A way back is never one way: the search back is the trip's return, one_way or not.
    assert reverse["route"] == "Riyadh to Jeddah" and reverse["return"]["options"]


def test_the_mock_keeps_a_search_with_no_return_day_one_way() -> None:
    # Run F plays the mock: its search and its picks stay as before round 2.
    call = LeanCall()
    found = call.find(destination="Jeddah", depart=MOCK_OUT, return_date=MOCK_BACK)
    call.choose(outbound_id=ids(found)[0])
    again = data(call.find(destination="Jeddah", depart=MOCK_OUT))
    assert "return" not in again and call.draft.one_way and "note" not in again
    done = data(call.choose())
    assert done["missing"] == [] and "note" not in done  # no note on the trip's end
    trip = LeanCall()
    trip.find(destination="Jeddah", depart=MOCK_OUT, return_date=MOCK_BACK)
    backs = [o.id for o in trip.draft.listed_return.offers]  # type: ignore[union-attr]
    first = data(trip.choose(return_id=backs[0]))  # the way back first, as before
    assert first["status"] == "ok" and first["missing"] == ["outbound"]
    refused = LeanCall().find(destination="Jeddah", depart=MOCK_OUT, one_way=True)
    assert not refused.ok and refused.failure == "bad_arguments"  # not in the mock's schema


def test_a_way_back_said_by_its_weekday_alone_is_its_first_after_the_day_out() -> None:
    """The replays of 2026-11-22: «والرجعة السبت» after «بكرة» searched as Wednesday the 25th;
    the weekday alone is enough, its date worked out in code (weekday.py's `next_weekday`)."""
    assert next_weekday("saturday", after=date(2026, 11, 23)) == date(2026, 11, 28)
    assert next_weekday("saturday", after=date(2026, 11, 28)) == date(2026, 12, 5)
    call = recorded_call()
    answer = data(call.find(destination="Jeddah", depart=DAY_OUT, return_weekday="sunday"))
    assert answer["return"]["day"]["date"] == DAY_BACK == call.draft.return_date.isoformat()  # type: ignore[union-attr]


def test_the_mocks_schema_keeps_run_fs_descriptions() -> None:
    real = {t.name: t for t in lean_tools(recorded_call().deps)}["find_flights"]
    mock = {t.name: t for t in lean_tools(LeanCall().deps)}["find_flights"]
    for name, said in (("return_weekday", SAID_BACK), ("return_date", RETURN_REAL)):
        assert real.parameters.model_fields[name].description == said
    assert mock.parameters.model_fields["return_weekday"].description == SAID
    assert mock.parameters.model_fields["return_date"].description == RETURN


def test_a_way_back_searched_with_one_way_is_still_the_trips_return() -> None:
    """Replayed on 2026-11-22: the model passed one_way for the way back's own search."""
    call = recorded_call()
    found = data(call.find(destination="Jeddah", depart=DAY_OUT))
    answer = data(call.find(origin="Jeddah", destination="Riyadh", depart=DAY_BACK, one_way=True))
    assert answer["route"] == "Riyadh to Jeddah" and answer["return"]["options"]
    assert option_ids(answer["outbound"]) == option_ids(found["outbound"])
    assert not call.draft.one_way and call.draft.return_date == date(2026, 11, 29)

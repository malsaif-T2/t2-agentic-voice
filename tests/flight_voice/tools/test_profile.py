"""`traveler_profile`: the verified caller's profile with every count worked out in code, in the
reply's language; a booking made since listed apart from the trips flown; a profile that does
not load said as a failure, never as no trips; and, adversarially, no argument from the talker
or the caller's words can read another traveler's profile, and the tool backs up no booking
claim (no `reports_on`)."""

from __future__ import annotations

import asyncio
import json
from datetime import date

import pytest
from flight_voice.airline.bookings import Leg, NewBooking, priced
from flight_voice.said import Tag
from flight_voice.tools.profile import PROFILE_UNKNOWN, TRAVELER_PROFILE, traveler_profile
from flight_voice.tools.results import PROFILE_FAILED, SAY
from t2_agentic_voice import Caller

from tests.flight_voice.scenario_dates import TODAY
from tests.flight_voice.tools.tool_support import TAGS, airline, data, run


def test_the_profile_gives_the_counts_and_the_trips_flown_newest_first() -> None:
    made = run(traveler_profile(airline()))
    found = data(made)
    assert (found["status"], found["say"]) == ("ok", SAY["profile"])
    assert (found["first_name"], found["tier"], found["home_said"]) == ("Khalid", "Gold", "Riyadh")
    assert (found["trips_flown"], found["most_visited_said"]) == (5, "Dubai")
    assert found["cabin_most_used_said"] == "economy"
    assert found["by_city"][0] == {
        "city_said": "Dubai",
        "trips": 2,
        "last_depart": "2026-10-08",
        "last_month_said": "October",
    }
    refs = [t["reference"] for t in found["flown"]]
    assert refs == ["482913", "517204", "390655", "604118", "275930"]
    cairo = found["flown"][3]
    assert (cairo["city_said"], cairo["trip_kind_said"], cairo["total_sar"]) == (
        "Cairo",
        "one way",
        1040,
    )
    assert found["booked"] == [] and made.card is None
    assert "booked" in SAY["profile"] and "reference" in SAY["profile"]


@pytest.mark.parametrize("tag", TAGS)
def test_the_profile_is_said_in_the_replys_language_and_kept_short(tag: Tag) -> None:
    found = data(run(traveler_profile(airline()), tag))
    if tag != "en":
        assert (found["first_name"], found["tier_said"]) == ("خالد", "ذهبي")
        assert found["most_visited_said"] == "دبي" and found["flown"][0]["month_said"] == "أكتوبر"
    if tag == "ar-SA":
        trip = found["flown"][0]
        assert (trip["trip_kind_said"], trip["trip_kind_said_msa"]) == ("رايح جاي", "ذهاب وعودة")
    assert len(json.dumps(found, ensure_ascii=False)) < 2400


def test_a_booking_made_since_is_listed_apart_from_the_trips_flown() -> None:
    flights = airline()
    legs = (Leg(flight=401, day=date(2026, 12, 17)),)
    total = priced(legs, "economy", 1, TODAY)
    new = NewBooking(
        request_id="r-1",
        traveler_id="T-0001",
        legs=legs,
        cabin="economy",
        travelers=1,
        total_sar=total,
    )
    made = asyncio.run(flights.bookings.create(new))
    found = data(run(traveler_profile(flights)))
    assert [t["reference"] for t in found["booked"]] == [made.reference]
    assert found["trips_flown"] == 5 and found["booked"][0]["city_said"] == "London"


@pytest.mark.parametrize("tag", TAGS)
def test_a_profile_that_does_not_load_is_said_as_a_failure_never_as_no_trips(tag: Tag) -> None:
    failed = run(traveler_profile(airline(profile_mode="fail")), tag)
    assert not failed.ok and failed.data == {"error": PROFILE_FAILED}
    assert "Do not say they have no trips" in PROFILE_FAILED


def test_a_caller_the_airline_does_not_know_reads_no_profile() -> None:
    tool = traveler_profile(airline())
    stranger = Caller(subject="owner", attributes={"traveler_id": "T-0002"})
    unknown = run(tool, caller=stranger)
    assert not unknown.ok and unknown.data == {"error": PROFILE_UNKNOWN}
    nobody = run(tool, caller=Caller(subject="owner"))
    assert not nobody.ok and "482913" not in json.dumps(nobody.data)


def test_the_talker_cannot_name_the_traveler_whose_profile_is_read() -> None:
    tool = traveler_profile(airline())
    schema = tool.tool_schema()
    assert schema.name == TRAVELER_PROFILE
    assert json.loads(json.dumps(dict(schema.parameters))).get("properties", {}) == {}
    forced = run(tool, traveler="T-0002")
    assert not forced.ok
    stranger = Caller(subject="owner", attributes={"traveler_id": "T-0002"})
    asked = run(tool, caller=stranger, traveler="T-0001")
    assert not asked.ok and "482913" not in json.dumps(asked.data)


def test_the_profile_backs_up_no_booking_claim() -> None:
    assert traveler_profile(airline()).reports_on == ()

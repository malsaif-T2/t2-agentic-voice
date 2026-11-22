"""The way back leaves after the way out lands (flight_voice/lean/turnaround.py), on the real
network: with the outbound chosen, the return's flights listed, carded, counted and taken are
those leaving at least two hours after it lands, compared in local time at the trip's
destination (the recorded Riyadh-Jeddah day, recorded_support.py); a return id leaving sooner
is `too_early`, with the outbound's arrival and the valid others; another outbound keeps a
chosen return only while it still leaves late enough, else drops it as lost and lists the way
back again; none left says to offer another day back, in `choose_flights` and in
`find_flights`' way back alike; a search that keeps both picks checks them too; and a new day
out after the way back's day keeps the trip round, its way back's day asked again."""

from __future__ import annotations

from datetime import date, datetime

from flight_voice.lean.find_return import BACK_BEFORE, NO_BACK_DAY, RETURN_ADDED
from flight_voice.lean.turnaround import (
    MIN_TURNAROUND,
    NONE_LATE_ENOUGH,
    RETURN_DROPPED,
    TOO_EARLY,
)

from tests.flight_voice.flight_data.fake import (
    JEDDAH,
    LONDON,
    RIYADH,
    SAUDIA,
    FakeFlightData,
    answered,
    nonstop,
    query,
)
from tests.flight_voice.lean.real_support import BACK, OUT, london_back, london_day, real_call
from tests.flight_voice.lean.recorded_support import (
    DAY_OUT,
    EVENING,
    LATE,
    LATE_BACK,
    MORNING,
    NIGHT_BACK,
    option_ids,
    recorded_call,
)
from tests.flight_voice.tools.tool_support import card_passes, data


def test_the_way_back_on_the_day_out_leaves_two_hours_after_it_lands() -> None:
    assert MIN_TURNAROUND.total_seconds() == 2 * 3600
    call = recorded_call()
    call.find(destination="Jeddah", depart=DAY_OUT, return_date=DAY_OUT)
    assert NIGHT_BACK in {o.id for o in call.draft.listed_return.offers}  # type: ignore[union-attr]
    picked = call.choose(outbound_id=EVENING)  # 17:00, lands 18:55
    listed = data(picked)["listed"]["return"]
    assert [o["departs"] for o in listed["options"]] == ["21:00", "21:20", "22:00"]
    assert (listed["count"], listed["first_departs"]) == (3, "21:00") and "more" not in listed
    assert [a["airline"] for a in listed["airlines"]] == ["Saudia", "flyadeal", "flynas"]
    assert picked.card is not None and card_passes(picked)
    assert [r.mark for r in picked.card.rows][-1] == "chosen" and len(picked.card.rows) == 4
    early = data(call.choose(return_id=NIGHT_BACK))  # 00:25, listed before the way out
    assert early["status"] == "too_early" and early["outbound_arrives"] == "18:55"
    assert [o["id"] for o in early["others"]] == option_ids(listed)
    assert early["note"] == TOO_EARLY and call.draft.chosen_return is None
    done = data(call.choose(return_id=LATE_BACK))
    assert done["missing"] == [] and done["total"] == 1537 + 540 == call.total()


def test_another_way_out_keeps_the_way_back_only_while_it_still_leaves_after() -> None:
    call = recorded_call()
    call.find(destination="Jeddah", depart=DAY_OUT, return_date=DAY_OUT)
    both = data(call.choose(outbound_id=EVENING, return_id=LATE_BACK))  # out first, then back
    assert both["missing"] == []
    kept = data(call.choose(outbound_id=MORNING))  # lands 11:35: 21:20 still leaves after
    assert kept["missing"] == [] and kept["return"]["id"] == LATE_BACK and "lost" not in kept
    late = call.choose(outbound_id=LATE)  # lands 00:55 the next day
    answer = data(late)
    assert answer["lost"] == [{"leg": "return", "departs": "21:20"}]
    assert answer["missing"] == ["return"] and answer["listed"]["return"]["count"] == 0
    assert RETURN_DROPPED in answer["note"] and NONE_LATE_ENOUGH in answer["note"]
    assert call.draft.chosen_return is None and "total" not in answer
    assert late.card is not None and card_passes(late)
    early = data(call.choose(return_id=LATE_BACK))
    assert early["status"] == "too_early" and early["others"] == []
    assert early["outbound_arrives"] == "00:55" and early["outbound_next_day"] is True
    assert early["note"] == NONE_LATE_ENOUGH


def test_the_way_back_asked_alone_is_filtered_by_the_chosen_way_out() -> None:
    call = recorded_call()
    call.find(destination="Jeddah", depart=DAY_OUT)
    call.choose(outbound_id=EVENING)
    back = call.find(origin="Jeddah", destination="Riyadh", depart=DAY_OUT)
    answer = data(back)
    assert answer["chosen"] == {"outbound": EVENING} and RETURN_ADDED in answer["note"]
    assert [o["departs"] for o in answer["return"]["options"]] == ["21:00", "21:20", "22:00"]
    assert answer["return"]["count"] == 3
    assert back.card is not None and back.card.slot == "return" and card_passes(back)
    assert len(back.card.rows) == 4 and back.card.rows[-1].mark == "chosen"
    call.choose(outbound_id=LATE)
    none = data(call.find(origin="Jeddah", destination="Riyadh", depart=DAY_OUT))
    assert none["chosen"] == {"outbound": LATE} and none["return"]["options"] == []
    assert NONE_LATE_ENOUGH in none["note"]
    assert call.draft.listed_return is not None and call.draft.listed_return.offers  # kept whole


def test_a_search_that_keeps_both_picks_checks_the_way_back_too() -> None:
    day = date(2026, 12, 3)
    source = FakeFlightData()

    def out(minutes: int) -> None:
        flight = nonstop(SAUDIA, "100", ("RUH", "JED"), datetime(2026, 12, 3, 8, 0), minutes, 500)
        source.set(answered(query(RIYADH, JEDDAH, day), (flight,)))

    out(120)  # lands 10:00
    backs = (
        nonstop(SAUDIA, "200", ("JED", "RUH"), datetime(2026, 12, 3, 12, 30), 100, 450),
        nonstop(SAUDIA, "202", ("JED", "RUH"), datetime(2026, 12, 3, 16, 0), 100, 470),
    )
    source.set(answered(query(JEDDAH, RIYADH, day), backs))
    call = real_call(source)
    days = {"destination": "Jeddah", "depart": day.isoformat(), "return_date": day.isoformat()}
    call.find(**days)
    picked = data(call.choose(outbound_id="SV100-2026-12-03", return_id="SV200-2026-12-03"))
    assert picked["missing"] == []
    out(200)  # the same flight now lands 11:20: 12:30 is too soon
    again = data(call.find(**days))
    assert again["chosen"] == {"outbound": "SV100-2026-12-03"}
    assert again["lost"] == [{"leg": "return", "departs": "12:30"}]
    assert RETURN_DROPPED in again["note"]
    assert option_ids(again["return"]) == ["SV202-2026-12-03"]


def test_a_new_day_out_after_the_way_back_asks_its_day_again() -> None:
    later = date(2026, 12, 12)
    source = FakeFlightData()
    source.set(answered(query(RIYADH, LONDON, OUT), london_day()))
    source.set(answered(query(LONDON, RIYADH, BACK), london_back()))
    flight = nonstop(SAUDIA, "119", ("RUH", "LHR"), datetime(2026, 12, 12, 1, 40), 445, 3150)
    source.set(answered(query(RIYADH, LONDON, later), (flight,)))
    call = real_call(source)
    call.find(destination="London", depart=OUT.isoformat(), return_date=BACK.isoformat())
    moved = data(call.find(destination="London", depart=later.isoformat()))
    assert BACK_BEFORE.format(day=BACK.isoformat()) in moved["note"] and "return" not in moved
    assert moved["fares_are"] == "per person, each way, as of now"
    draft = call.draft
    assert not draft.one_way and draft.return_date is None and draft.depart == later
    assert "return_date" in draft.missing()
    picked = data(call.choose(outbound_id=option_ids(moved["outbound"])[0]))
    assert picked["missing"] == ["return"] and "listed" not in picked
    assert NO_BACK_DAY in picked["note"] and picked["trip"] == "round trip"
    still = data(call.find(destination="London", depart=later.isoformat()))
    assert NO_BACK_DAY in still["note"] and not call.draft.one_way


def test_a_way_out_chosen_beside_a_refused_way_back_is_kept() -> None:
    """Both ways in one call, the way back too early: the way out is kept, so the way back the
    caller picks next, passed alone, is taken (the review of 2026-11-22)."""
    call = recorded_call()
    call.find(destination="Jeddah", depart=DAY_OUT, return_date=DAY_OUT)
    early = data(call.choose(outbound_id=EVENING, return_id=NIGHT_BACK))
    assert early["status"] == "too_early"
    assert call.draft.chosen_outbound is not None and call.draft.chosen_outbound.id == EVENING
    picked = data(call.choose(return_id=LATE_BACK))
    assert picked["status"] == "ok" and picked["return"]["id"] == LATE_BACK

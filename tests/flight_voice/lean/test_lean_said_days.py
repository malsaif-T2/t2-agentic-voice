"""The way back's weekday as the caller named it (flight_voice/lean/said_days.py, D-138): a
weekday with a return word before it is the way back's, none after a negation or an anchor; the
way back held to the one weekday named for it when the model passed none and put it on another,
never before the day out; the way out never moved; a search back alone held to the one weekday
named, never before the trip's day out; dates, counts of days and two weekdays left as the
model wrote them; and `find_flights` reads the caller's words from its context
(`CallContext.hearing`), a weekday passed alone for the way back's own search its day, the mock
as run F reads it. The review of 2026-11-22 found each of these broken in the first version."""

from __future__ import annotations

from datetime import date

import pytest
from flight_voice.lean.said_days import held_days, named_days
from t2_agentic_voice import CallContext

from tests.flight_voice.lean.lean_support import OUT as MOCK_OUT
from tests.flight_voice.lean.lean_support import LeanCall
from tests.flight_voice.lean.recorded_support import DAY_BACK, DAY_OUT, EVENING, recorded_call
from tests.flight_voice.tools.tool_support import data

MON, WED, THU, FRI, SAT, SUN = (date(2026, 11, d) for d in (23, 25, 26, 27, 28, 29))


@pytest.mark.parametrize(
    ("heard", "named"),
    [
        ("أبي من القصيم لإسطنبول بكرة، والرجعة السبت", (("saturday", True),)),
        ("خل نقول بكرة، والعودة يوم السبت", (("saturday", True),)),
        ("أبي أسافر يوم الخميس وأرجع الأحد", (("thursday", False), ("sunday", True))),
        ("بسافر بكرة وبرجع الخميس", (("thursday", True),)),
        ("بسافر بكرة ورجوعي الخميس", (("thursday", True),)),
        ("Riyadh to Jeddah on Thursday, back on Sunday", (("thursday", False), ("sunday", True))),
        ("I leave tomorrow and fly home Friday", (("friday", True),)),
        ("لا، شوف لي يوم السبت", (("saturday", False),)),
        ("مو الجمعة", ()),
        ("أبي أوصل جدة قبل الجمعة", ()),
        ("the day after Thursday", ()),
        ("أبي أحد يساعدني", ()),  # «أحد», someone, is no weekday
    ],
)
def test_the_weekdays_named_are_read_with_a_return_word_before_them(
    heard: str, named: tuple[tuple[str, bool], ...]
) -> None:
    assert named_days(heard) == named


@pytest.mark.parametrize(
    ("heard", "depart", "back", "held"),
    [
        ("أبي من القصيم لإسطنبول بكرة، والرجعة السبت", MON, WED, (MON, SAT)),
        ("أبي من القصيم لإسطنبول بكرة، والرجعة السبت", MON, SAT, (MON, SAT)),
        ("أبي أسافر الخميس وأرجع السبت", WED, WED, (WED, SAT)),  # the way out: the model's
        ("السبت", THU, SAT, (THU, SAT)),  # a lone weekday never moves the way out
        ("يوم السبت إن شاء الله", THU, WED, (THU, WED)),  # nor the way back, with no return word
        ("أبي أسافر الخميس وأرجع بعد يومين", THU, SAT, (THU, SAT)),  # a count of days
        ("وأرجع قبل الجمعة", MON, THU, (MON, THU)),  # an anchor names no day
        ("أرجع السبت أو الأحد", MON, WED, (MON, WED)),  # two for the way back
        ("الرجعة يوم ٥ ديسمبر", MON, date(2026, 12, 5), (MON, date(2026, 12, 5))),  # a date
    ],
)
def test_only_the_way_back_is_held_to_the_weekday_named_for_it(
    heard: str, depart: date, back: date, held: tuple[date, date]
) -> None:
    assert held_days(heard, depart, back, said=None) == held


def test_the_weekday_the_model_passed_wins() -> None:
    heard = "بكرة، والرجعة السبت"
    assert held_days(heard, MON, WED, said="wednesday") == (MON, WED)


def test_a_search_back_alone_takes_the_weekday_named_never_before_the_day_out() -> None:
    assert held_days("لا، شوف لي يوم السبت", WED, None, said=None, reverse=True, day_out=MON) == (
        SAT,
        None,
    )
    # «والرجعة الخميس» after a way out on Saturday: the next Thursday, never before it.
    held = held_days("والرجعة الخميس", SUN, None, said=None, reverse=True, day_out=SAT)
    assert held == (date(2026, 12, 3), None)


def test_find_flights_reads_the_callers_words_from_its_context() -> None:
    call = recorded_call()
    heard = "أبي أسافر لجدة الخميس، والرجعة يوم الأحد"
    wrong = data(
        call.find(destination="Jeddah", depart=DAY_OUT, return_date="2026-11-27", heard=heard)
    )
    assert wrong["return"]["day"]["date"] == DAY_BACK  # Friday 27 held to Sunday 29
    assert CallContext.model_fields["heard"].default == ""


def test_a_weekday_passed_for_the_way_backs_own_search_is_its_day() -> None:
    """The review of 2026-11-22: return_weekday on a search back made it a new round trip."""
    call = recorded_call()
    call.find(destination="Jeddah", depart=DAY_OUT)
    call.choose(outbound_id=EVENING)
    found = call.find(
        origin="Jeddah", destination="Riyadh", depart="2026-11-28", return_weekday="sunday"
    )
    back = data(found)
    assert back["route"] == "Riyadh to Jeddah" and back["chosen"] == {"outbound": EVENING}
    assert back["return"]["day"]["date"] == DAY_BACK and call.draft.chosen_outbound is not None


def test_the_mock_reads_no_weekday_alone() -> None:
    call = LeanCall()
    found = data(call.find(destination="Jeddah", depart=MOCK_OUT, return_weekday="sunday"))
    assert "return" not in found and call.draft.one_way  # as run F reads it, before round 2

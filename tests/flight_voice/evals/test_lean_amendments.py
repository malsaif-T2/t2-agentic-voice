"""The lead's amendments of 2026-11-18 to run F's lean outcome mode (flight_voice/evals/
lean_checks.py, lean_repeats.py; the flight spec's 13), each on a real play of f-dev-lean-3 it
changes, beside a true failure it keeps: `booked` takes f30's tied dearest flight, never a
wrong one; `repeat` lets a read-back after a change, another day's listing and a first clause
said again with a new sentence go, never a true repeat (one that only leaves a fact out, or
says "Which one"); `max_words` counts the reply as
written, never its captions, and a long reply still fails; a lean play's record keeps the reply
as written. The scripted mode's checks are unchanged."""

from __future__ import annotations

import tomllib
from datetime import date
from typing import Any, Literal

from flight_voice.airline.bookings import Booking, Leg
from flight_voice.evals.call import PlayRead, TurnRead
from flight_voice.evals.checks import booking_checks
from flight_voice.evals.lean_call import LeanRead
from flight_voice.evals.lean_checks import lean_booking_checks, lean_turn_checks, tied
from flight_voice.evals.lean_repeats import NEAR_REPEAT_OVERLAP, Facts, Said, facts, lean_repeat
from flight_voice.evals.scenarios import CALLS, FlightOn, Scenario
from flight_voice.evals.score import record_of
from t2_agentic_voice.evals import HeardClause, find_repeat
from t2_agentic_voice.testing import repeats

F30 = Scenario.model_validate(
    tomllib.loads((CALLS / "f30_dearest_saudi.toml").read_text(encoding="utf-8"))
)
OUT, BACK = date(2026, 11, 17), date(2026, 11, 19)
Tag = Literal["ar-SA", "ar", "en"]


def _booked(out: int, back: int, *, day: date = BACK, **fields: Any) -> PlayRead:
    booking = Booking(
        reference="883840",
        origin="RUH",
        destination="JED",
        depart=OUT,
        return_date=day,
        travelers=fields.pop("travelers", 1),
        cabin=fields.pop("cabin", "economy"),
        total_sar=730,
        traveler_id="T-0001",
        legs=(Leg(flight=out, day=OUT), Leg(flight=back, day=day)),
        request_id="r1",
    )
    return PlayRead(turns=(), violations=(), made=(booking,))


def test_the_dearest_of_two_at_one_fare_is_booked_as_either_and_a_wrong_booking_still_fails() -> (
    None
):
    assert tied(FlightOn(number=102, day=BACK), "economy") == {102, 106}  # 470 each, 19 Nov
    # f30 p1 chose T2 106 as "the dearest"; the read-back names T2 102, the first listed.
    p1 = _booked(105, 106)
    assert list(lean_booking_checks(F30, p1)) == []
    assert list(booking_checks(F30, p1)) == ["booked"]  # the scripted mode's, as it was
    assert list(lean_booking_checks(F30, _booked(105, 102))) == []
    wrong = (
        _booked(105, 104),  # the 12:30 at 450, chosen before "the dearest"
        _booked(105, 102, day=date(2026, 11, 21)),  # p2's Saturday
        _booked(105, 106, travelers=2),
        _booked(105, 106, cabin="business"),
        _booked(103, 106),  # ties T2 105 at 260, but "the afternoon one" is no pick by fare
    )
    assert [list(lean_booking_checks(F30, read)) for read in wrong] == [["booked"]] * 5


def test_the_near_repeat_threshold_is_the_librarys() -> None:
    assert NEAR_REPEAT_OVERLAP == repeats.NEAR_REPEAT_OVERLAP


def test_a_replys_facts_are_its_numbers_weekdays_and_cities_in_either_script() -> None:
    found = facts("Riyadh to London on Thursday at 09:10, 1 traveler, total 2,290.")
    assert found == Facts(
        numbers=frozenset({"9:10", "1", "2290"}),
        weekdays=frozenset({"thursday"}),
        cities=frozenset({"RUH", "LHR"}),
    )
    arabic = facts("من الرياض لجدة والخميس 19 نوفمبر، مسافرين اثنين")
    assert arabic == Facts(
        numbers=frozenset({"19", "2"}),
        weekdays=frozenset({"الخميس"}),
        cities=frozenset({"RUH", "JED"}),
    )
    # The word one is no fact, in either language: a pronoun, or travelers the total moves with.
    assert facts("Which one would you like, one-way? One traveler.").numbers == frozenset()
    assert facts("أي واحد تبي؟ شخص واحد، للراكب الواحد").numbers == frozenset()


# f14 p2, turns 2 and 3: one traveler made two, the total 260 made 520.
F14_BEFORE = (
    "من الرياض إلى جدة يوم الثلاثاء 17 نوفمبر يطلع 15:00، كابينة اقتصاد، مسافر واحد، "
    "المجموع 260 ريال. تبي نحجز؟"
)
F14_AFTER = (
    "من الرياض إلى جدة يوم الثلاثاء 17 نوفمبر يطلع 15:00، كابينة اقتصاد، مسافرين اثنين، "
    "المجموع 520 ريال. تبي نحجز؟"
)
# f25 p2, turns 4 and 5: the next day's listing, in the same frame.
F25_BEFORE = (
    "في يوم الثلاثاء 8 ديسمبر فيه رحلتين، الأولى تطلع 09:30 وسعرها 830 ريال والثانية تطلع "
    "18:15 وسعرها 830 ريال. أي وحدة تبي؟"
)
F25_AFTER = (
    "في يوم الأربعاء 9 ديسمبر فيه رحلتين، الأولى تطلع 09:30 وسعرها 900 ريال والثانية تطلع "
    "18:15 وسعرها 930 ريال. أي وحدة تبي؟"
)
# f19 p2, turns 3 and 4: the required line said again, with a new sentence.
F19_BEFORE = "ما أقدر أأكد إذا تم الحجز ولا لا. تبي شيء ثاني؟"
F19_AFTER = "ما أقدر أأكد إذا تم الحجز ولا لا. ما أقدر أحاول مرة ثانية الآن. هل تبي شيء ثاني؟"
# f06 p3, turns 3 and 4: the same trip said again (a true near repeat).
F06_BEFORE = (
    "الرحلة من الرياض إلى باريس يوم الأحد 20 ديسمبر 08:35 والعودة يوم الأحد 27 ديسمبر 11:30، "
    "درجة سياحية لراكب واحد بإجمالي 5860. تبي نحجزها الآن؟"
)
F06_AFTER = (
    "الرحلة الأولى من الرياض إلى باريس يوم الأحد 20 ديسمبر تطلع 08:35 والعودة يوم الأحد 27 "
    "ديسمبر 11:30، درجة سياحية لراكب واحد بإجمالي 5860. تبي نحجزها الآن؟"
)
# f05 p2, turns 2 and 3: the same read-back, a new last clause (first clause, overlap 0.88).
F05 = (
    "Your round‑trip from Riyadh to London departs Thursday, November 19 at 09:10 and "
    "returns Sunday, November 22 at 16:00, economy for 1 traveler, total 4470. "
)


def _again(before: str, after: str) -> bool:
    return lean_repeat(Said(after, after), [Said(before, before)], asks_repeat=False) is not None


def test_a_reply_with_new_facts_is_no_repeat_where_the_library_finds_one() -> None:
    for before, after in ((F14_BEFORE, F14_AFTER), (F25_BEFORE, F25_AFTER)):
        assert find_repeat(after, [before]) is not None
        assert not _again(before, after)


def test_a_first_clause_alone_is_no_repeat_and_a_true_repeat_still_is() -> None:
    found = find_repeat(F19_AFTER, [F19_BEFORE])
    assert found is not None and found.by == "first_clause" and found.overlap < 0.8
    assert not _again(F19_BEFORE, F19_AFTER)
    assert _again(F06_BEFORE, F06_AFTER)  # by overlap, the same facts
    assert _again(F05 + "Would you like to book it?", F05 + "Shall I book it?")  # first clause
    assert _again(F14_BEFORE, F14_BEFORE)  # identical
    said = Said(F06_AFTER, F06_AFTER)
    assert lean_repeat(said, [Said(F06_BEFORE, F06_BEFORE)], asks_repeat=True) is None
    older = [Said(F06_BEFORE, F06_BEFORE), Said(F25_BEFORE, F25_BEFORE)]
    assert lean_repeat(said, older, asks_repeat=False) is not None  # not only the latest


# f22 p3, turns 2 and 3: the trip read back, then booked and said again (a true near repeat).
F22_READ_BACK = (
    "رحلتك من الرياض لمومباي يوم الخميس 10 ديسمبر، تطلع الساعة 16:45 وتوصل 23:15، اقتصاد، "
    "شخص واحد، الإجمالي 1670 ريال للرايح بس. تبي نحجزها؟"
)
F22_BOOKED = (
    "تم حجز رحلتك من الرياض لمومباي يوم الخميس 10 ديسمبر، تطلع الساعة 16:45 وتوصل 23:15، "
    "اقتصاد، شخص واحد، إجمالي 1670 ريال للرايح بس. تبي شيء ثاني؟"
)
# f20 p2, turn 1: a listing that ends "Which one would you like?".
F20 = (
    "There are 2 flights on Monday, November 23. The first departs at 09:30 and the last at "
    "18:15. The cheapest leaves at 09:30 and costs 910. Which{} would you like?"
)


def test_a_reply_that_only_leaves_a_fact_out_or_says_which_one_is_still_a_repeat() -> None:
    assert _again(F22_READ_BACK, F22_BOOKED)  # the same facts
    shorter = F22_BOOKED.replace(" وتوصل 23:15", "")  # the arrival left out, nothing new
    assert shorter != F22_BOOKED
    found = find_repeat(shorter, [F22_READ_BACK])
    assert found is not None and found.kind == "near"
    assert _again(F22_READ_BACK, shorter)
    which, which_one = F20.format(""), F20.format(" one")
    found = find_repeat(which_one, [which])
    assert found is not None and found.by == "first_clause"
    assert _again(which, which_one) and _again(which_one, which)
    assert not _again(which, F20.format(" one").replace("910", "980"))  # a new fare still goes


def _turn(*heard: str, written: tuple[str, ...] = (), language: Tag = "en") -> TurnRead:
    clauses = tuple(
        HeardClause(text=t, language=language, fate="played", played_fraction=1.0) for t in heard
    )
    return TurnRead(
        index=0,
        fate="answered",
        clauses=clauses,
        heard=clauses,
        tools=(),
        cards=0,
        written=written,
    )


def _scenario(*says: str, language: str = "en") -> Scenario:
    turns = [{"says": words} for words in says]
    made = {"id": "x03_lean_words", "split": "dev", "kind": "words", "turns": turns}
    return Scenario.model_validate(made | {"language": language, "notes": "Counted as written."})


# f29 p2, turn 1: 60 words heard, its long clause cut in two and its numbers said; 43 written.
F29_HEARD = (
    "Next week, Sunday 22 November through Saturday 28 November, we have flights to Paris.",
    "Departures are at one fifty-five at night and eight thirty-five in the morning,",
    "and the cheapest days are Tuesday twenty-four November at one thousand seven hundred and "
    "twenty and Monday twenty-three November at one thousand eight hundred and twenty.",
    "Which day would you like to choose?",
)
F29_WRITTEN = (
    F29_HEARD[0],
    "Departures are at 01:55 and 08:35, and the cheapest days are Tuesday 24 November at 1720 "
    "and Monday 23 November at 1820.",
    F29_HEARD[-1],
)
# f05 p3, turn 1, as written: 58 words, too long however counted.
F05_LONG = (
    "There are two flights on Thursday, first at 09:10 and last at 14:40, and the cheapest "
    "departs at 09:10 for 2190.",
    "There are two flights on Sunday, first at 16:00 and last at 21:45, and the cheapest "
    "departs at 16:00 for 2280, fares are one way per person.",
    "Which outbound and return flights would you like to choose?",
)
# f08 p1, turn 1, in Arabic, heard as written: 48 words.
F08_LONG = (
    "من الرياض إلى الدوحة في الأربعاء 18 نوفمبر. هناك 3 رحلات، أولها 08:00 وآخرها 19:45، "
    "وأرخصها 14:20 بسعر 480 ريال للراكب الواحد، رايح فقط. العودة في السبت 21 نوفمبر فيها 3 "
    "رحلات، أولها 10:40 وآخرها 22:30، وأرخصها 10:40 بسعر 530 ريال للراكب الواحد، هل تريد حجز "
    "هذه الرحلة؟"
)


def _words_checks(made: Scenario, read: TurnRead) -> list[str]:
    return [name for name in lean_turn_checks(made, 0, [read]) if name == "max_words"]


def test_max_words_counts_the_reply_as_written_and_a_long_one_still_fails() -> None:
    made = _scenario("Paris next week?")
    assert len(" ".join(F29_HEARD).split()) == 60 and made.turns[0].max_words == 45
    assert _words_checks(made, _turn(*F29_HEARD, written=F29_WRITTEN)) == []
    assert _words_checks(made, _turn(*F05_LONG, written=F05_LONG)) == ["max_words"]
    arabic = _scenario("الدوحة الأربعاء الجاي", language="ar-SA")
    long = _turn(F08_LONG, written=(F08_LONG,), language="ar-SA")
    assert _words_checks(arabic, long) == ["max_words"]


def test_a_lean_record_keeps_the_reply_as_written_and_a_scripted_one_does_not() -> None:
    made = _scenario("Paris next week?")
    read = LeanRead(turns=(_turn(*F29_HEARD, written=F29_WRITTEN),), violations=())
    (lean,) = record_of(made, 1, read, 1.0, agent="lean").turns
    (scripted,) = record_of(made, 1, read, 1.0).turns
    assert lean.written == F29_WRITTEN and scripted.written == ()

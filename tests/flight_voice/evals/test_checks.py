"""Each check of a scripted flight call's play (flight_voice/evals/checks.py) on a crafted turn:
the tools and the values they held as the airline reads them, the outcome and the read-back,
the words said and not said in either script, the language and the register, the words and
options counted, the long-call checks from the library's repeat measures (a near repeat caught,
an asked repeat and a read-back said again exempt, a cut repeat measured), the card and the
progress line; and the play's own: its end, its violations, the booking made and for whom, and the
reference said only when asked."""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest
from flight_voice.airline.bookings import Booking, Leg
from flight_voice.evals.call import PlayRead, TurnRead
from flight_voice.evals.checks import Failed, failures, options_said, turn_checks
from flight_voice.evals.scenarios import Scenario
from pydantic import JsonValue
from t2_agentic_voice.evals import HeardClause, TextToolCall

TOMORROW: JsonValue = {"kind": "relative", "when": "tomorrow"}


def clause(text: str, **fields: Any) -> HeardClause:
    return HeardClause(
        text=text,
        language=fields.pop("language", "en"),
        fate=fields.pop("fate", "played"),
        played_fraction=fields.pop("played_fraction", 1.0),
        **fields,
    )


def tool(name: str, **arguments: JsonValue) -> TextToolCall:
    return TextToolCall(call_id=f"c-{name}", tool=name, arguments=arguments, outcome="ok", ms=5.0)


def read(*clauses: HeardClause, index: int = 0, **fields: Any) -> TurnRead:
    return TurnRead(
        index=index,
        fate="answered",
        clauses=clauses,
        heard=tuple(c for c in clauses if c.fate != "unplayed"),
        tools=fields.pop("tools", ()),
        cards=fields.pop("cards", 0),
        **fields,
    )


def scenario(*turns: dict[str, Any], language: str = "en") -> Scenario:
    return Scenario.model_validate(
        {
            "id": "x01_crafted",
            "split": "dev",
            "language": language,
            "kind": "crafted",
            "notes": "A crafted call.",
            "turns": list(turns),
        }
    )


def failed(made: Scenario, *reads: TurnRead | None, at: int | None = None) -> list[str]:
    n = len(reads) - 1 if at is None else at
    return list(turn_checks(made, n, reads, None))


def test_the_tools_and_the_values_they_held_are_read_as_the_airline_reads_them() -> None:
    made = scenario(
        {
            "says": "Dubai tomorrow, back in three nights",
            "calls": ["search_flights"],
            "args": {"destination": "DXB", "depart": "2026-11-17", "return_date": "2026-11-20"},
        }
    )
    nights: JsonValue = {"kind": "nights", "nights": 3}
    search = tool("search_flights", destination="Dubai", depart=TOMORROW, return_date=nights)
    assert failed(made, read(clause("Here they are."), tools=(search,))) == []
    elsewhere = tool("search_flights", destination="Doha", depart=TOMORROW, return_date=nights)
    assert failed(made, read(clause("Here they are."), tools=(elsewhere,))) == ["args"]
    assert failed(made, read(clause("Here they are."))) == ["calls", "args"]


def test_a_pick_is_read_from_its_choice() -> None:
    made = scenario(
        {"says": "the earliest", "args": {"leg": "outbound", "pick": "earliest"}},
    )
    choose = tool("choose_flight", leg="outbound", choice={"pick": "earliest"})
    assert failed(made, read(clause("Done."), tools=(choose,))) == []
    latest = tool("choose_flight", leg="outbound", choice={"pick": "latest"})
    assert failed(made, read(clause("Done."), tools=(latest,))) == ["args"]


@pytest.mark.parametrize(
    ("outcome", "fields", "holds"),
    [
        ("asked_again", {"asked_again": True}, True),
        ("asked_again", {}, False),
        ("done", {"confirmed": True, "ended": "done"}, True),
        ("done", {"confirmed": True, "ended": "unknown"}, False),
        ("unknown", {"confirmed": True, "ended": "unknown"}, True),
        ("declined", {}, True),
        ("declined", {"confirmed": True}, False),
        ("none", {"read_back": True}, False),
        ("read_back", {"read_back": True}, True),
        ("read_back", {}, False),
    ],
)
def test_each_outcome_is_held_to_what_the_call_did(
    outcome: str, fields: dict[str, Any], holds: bool
) -> None:
    made = scenario({"says": "yes", "outcome": outcome})
    assert failed(made, read(clause("Okay."), **fields)) == ([] if holds else ["outcome"])


def test_a_read_back_missing_its_values_is_named_read_back() -> None:
    made = scenario(
        {
            "says": "the earliest",
            "outcome": "read_back",
            "read_back": {
                "outbound": "T2 201@2026-11-17",
                "one_way": True,
                "travelers": 1,
                "cabin": "economy",
            },
        }
    )
    assert failed(made, read(clause("Okay."))) == ["read_back"]


def test_words_said_and_not_said_compare_in_the_scorers_form() -> None:
    made = scenario(
        {"says": "أبي أروح لندن", "said_any": [["للشخص", "per person"]], "said_none": ["ما فيه"]},
        language="ar-SA",
    )
    marked = clause("السعر ٣٥٦٠ لِلشَّخص، أبي أعرف وش تبي", language="ar-SA")
    assert failed(made, read(marked)) == []
    assert failed(made, read(clause("ما فيه رحلات، تبي يوم ثاني؟", language="ar-SA"))) == [
        "said_any",
        "said_none",
    ]


def test_the_language_and_the_register_are_read_from_the_talkers_own_words() -> None:
    english = scenario({"says": "London"})
    assert failed(english, read(clause("وش تبي؟", language="ar-SA"))) == ["language"]
    # A read-back line, the runtime's, is never held to the talker's register or language.
    line = clause("رايح جاي للندن", language="ar-SA", template=True)
    assert failed(english, read(clause("Here it is."), line)) == []
    saudi = scenario({"says": "أبي أروح لندن"}, language="ar-SA")
    assert failed(saudi, read(clause("أبي أعرف وش اليوم اللي تبيه", language="ar-SA"))) == []
    msa = clause("هل تريد السفر في الصباح أم في المساء؟", language="ar-SA")
    assert failed(saudi, read(msa)) == ["register"]


def test_the_words_and_the_options_said_are_counted() -> None:
    made = scenario({"says": "London", "max_words": 5, "max_options": 2})
    assert failed(made, read(clause("One two three four five six."))) == ["max_words"]
    times = clause("At 7:15, 13:40 or 20:30.")
    assert options_said("At 7:15, 13:40 or 20:30, landing 9:12 (no flight leaves then).") == 3
    assert failed(made, read(times)) == ["max_options"]


def test_a_near_repeat_is_caught_and_an_asked_repeat_and_a_read_back_are_exempt() -> None:
    first = read(clause("The flights to London leave at nine and at two."), index=0)
    near = read(clause("The flights to London leave at nine, and one at night."), index=1)
    made = scenario({"says": "London"}, {"says": "and then?"})
    assert failed(made, first, near) == ["repeat"]
    asked = scenario({"says": "London"}, {"says": "say it again", "asks_repeat": True})
    assert failed(asked, first, near) == []
    line = clause("One way to London on Thursday.", template=True)
    again = read(clause("One way to London on Thursday.", template=True), line, index=1)
    assert failed(made, read(line, index=0), again) == []


def test_a_cut_repeat_is_measured_on_the_cut_replys_whole_text() -> None:
    whole = (
        clause("The flights to London on the third", fate="cut", played_fraction=0.3),
        clause("leave in the morning and at night.", fate="unplayed", played_fraction=0.0),
    )
    cut = read(*whole, index=0)
    made = scenario(
        {"says": "London"},
        {"stop": True, "at": "agent_speaking", "after_s": 1.0},
        {"says": "one more time?", "asks_repeat": True, "repeat_of_cut": True},
    )
    said = read(clause("The flights to London on the third leave at night."), index=2)
    assert failed(made, cut, None, said) == []
    short = read(clause("Sure, which day?"), index=2)
    assert failed(made, cut, None, short) == ["cut_repeat"]


def test_the_card_the_progress_line_and_the_agents_own_summary() -> None:
    made = scenario({"says": "London", "shows_card": True, "hears_progress": True})
    assert failed(made, read(clause("Here they are."))) == ["card", "progress"]
    shown = read(clause("One moment.", phrase=True), clause("Here they are."), cards=1)
    assert failed(made, shown) == []
    summary = scenario({"says": "the earliest", "outcome": "read_back"})
    own = read(clause("So that is flight 201 at 7:15."), read_back=True)
    assert failed(summary, own) == ["own_summary"]


def _booking(reference: str = "123456", traveler: str = "T-0001") -> Booking:
    return Booking(
        reference=reference,
        origin="RUH",
        destination="DXB",
        depart=date(2026, 11, 17),
        travelers=1,
        cabin="economy",
        total_sar=900,
        traveler_id=traveler,
        legs=(Leg(flight=201, day=date(2026, 11, 17)),),
        request_id="r1",
    )


BOOKED = scenario(
    {
        "says": "the earliest",
        "outcome": "read_back",
        "read_back": {
            "outbound": "T2 201@2026-11-17",
            "one_way": True,
            "travelers": 1,
            "cabin": "economy",
        },
    },
    {"says": "yes, book it", "when": "closing_question", "outcome": "done"},
    {"says": "what's my reference?", "asks_reference": True},
)


def _play(*said: str, **fields: Any) -> PlayRead:
    turns = (
        read(clause(said[0]), index=0, read_back=True),
        read(clause(said[1]), index=1, confirmed=True, ended="done"),
        read(clause(said[2]), index=2),
    )
    return PlayRead(turns=turns, violations=fields.pop("violations", ()), **fields)


def test_the_play_holds_its_booking_for_the_traveler_and_its_reference_when_asked() -> None:
    done = _play("Okay.", "Booked.", "It is 123456.", made=(_booking(),), writes=1)
    assert failures(BOOKED, done) == ()
    told = _play("Okay.", "Booked, reference 123456.", "It is 123456.", made=(_booking(),))
    assert failures(BOOKED, told) == (Failed("reference", 2),)
    other = _play("Okay.", "Booked.", "It is 123456.", made=(_booking(traveler="T-0002"),))
    assert [f.check for f in failures(BOOKED, other)] == ["others", "booked"]
    twice = (_booking(), _booking("654321"))
    assert [f.check for f in failures(BOOKED, _play("a", "b", "123456", made=twice))] == ["booked"]


def test_a_play_that_stopped_or_broke_a_rule_fails_whatever_its_turns_did() -> None:
    broke = _play("Okay.", "Booked.", "It is 123456.", made=(_booking(),), violations=("A",))
    assert failures(BOOKED, broke) == (Failed("violations"),)
    stuck = PlayRead(turns=(None, None, None), violations=(), failure="stuck")
    found = [f.check for f in failures(BOOKED, stuck)]
    assert found[:2] == ["failure", "booked"] and "said" in found

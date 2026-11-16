"""The booking's draft (flight_voice/booking/draft.py) as the library's action runner proposes it:
the talker sees no field of it, a value it sends under a field's name never survives `validate`,
which fills every field from the call's trip, and the read-back says the trip whole, its kind
first, in Saudi Arabic, MSA and English, every number in words."""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any

import pytest
from flight_voice.airline.schedule import departures
from flight_voice.booking.action import book_trip
from flight_voice.booking.draft import BOOK_TRIP, BookingDraft, NotFilledError
from flight_voice.trip import TripDraft
from t2_agentic_voice import CallContext
from t2_agentic_voice.actions.action_runner import ActionRunner
from t2_agentic_voice.actions.tools import ToolResult
from t2_agentic_voice.core.settings.tts import LanguageTag
from t2_agentic_voice.domain.action_lines import ReadBackPlan
from t2_agentic_voice.domain.ports.chat_model import ToolCallRequest
from t2_agentic_voice.stores import MemoryOutbox

from tests.flight_voice.booking.booking_support import CALLER, DEC_17, airline, london, planned


def _proposed(
    arguments: dict[str, Any] | None = None,
    tag: LanguageTag = "en",
    *,
    wording: LanguageTag | None = None,
    trip: TripDraft | None = None,
) -> ReadBackPlan | ToolResult:
    """The runner's proposal of `book_trip` called with `arguments`, for the demo traveler, in a
    call in `tag` read in `wording`, the call planning `trip` (London unless given)."""
    runner = ActionRunner([book_trip(airline(), planned(trip))], outbox=MemoryOutbox())
    sent = json.dumps(arguments or {})
    request = ToolCallRequest(id="t-1", name=BOOK_TRIP, arguments=sent)
    ctx = CallContext(caller=CALLER, call_id="call-1", language=tag)
    return asyncio.run(runner.propose(request, ctx, wording=wording))


def _plan(
    arguments: dict[str, Any] | None = None,
    tag: LanguageTag = "en",
    *,
    wording: LanguageTag | None = None,
    trip: TripDraft | None = None,
) -> ReadBackPlan:
    made = _proposed(arguments, tag, wording=wording, trip=trip)
    assert isinstance(made, ReadBackPlan), made
    return made


def test_the_talker_sees_no_field_of_the_booking() -> None:
    made = book_trip(airline(), planned())
    schema = made.tool_schema().parameters
    assert schema.get("properties") == {} and schema.get("additionalProperties") is False
    assert "required" not in schema
    assert len(BookingDraft.model_fields) > 20


def test_every_value_the_talker_sends_is_replaced_from_the_trip() -> None:
    """A guessed field never survives: the talker's flight, day, travelers, cabin, total and
    words are all replaced by the trip's own, priced now."""
    guessed = {
        "outbound_flight": 999,
        "outbound_date": "2026-11-20",
        "one_way": True,
        "travelers": 9,
        "cabin": "first",
        "total_sar": 1,
        "route_en": "Riyadh to the moon",
        "total_en": "one riyal",
    }
    sent = json.loads(_plan(guessed).draft_json)
    honest = json.loads(_plan().draft_json)
    assert sent == honest
    out = departures("RUH", "LHR", DEC_17)[0]
    assert (sent["outbound_flight"], sent["outbound_date"]) == (out.flight.number, "2026-12-17")
    assert (sent["one_way"], sent["travelers"], sent["cabin"]) == (False, 1, "economy")
    assert sent["total_sar"] > 1000 and sent["route_en"] == "Riyadh to London"


def test_a_field_the_draft_does_not_hold_is_refused_and_named() -> None:
    made = _proposed({"traveler_id": "T-0002"})
    assert isinstance(made, ToolResult) and not made.ok
    assert "traveler_id" in json.dumps(made.data) and "T-0002" not in json.dumps(made.data)


@pytest.mark.parametrize(
    ("read", "summary", "question"),
    [
        (
            ("ar-SA", None),
            "بحجز لك أنت على الدرجة السياحية، رايح جاي: من الرياض للندن، الخميس سبعطعش ديسمبر "
            "تطلع تسع وعشر دقايق الصبح، والرجعة الأحد عشرين ديسمبر تطلع من لندن أربع العصر. "
            "المجموع ستة آلاف وسبع مية وعشرة ريالات.",
            "تبيني أحجزها؟",
        ),
        (
            ("ar-SA", "ar"),
            "سأحجز لك وحدك في الدرجة السياحية، ذهاب وعودة: من الرياض إلى لندن، يوم الخميس السابع "
            "عشر من ديسمبر تقلع التاسعة وعشر دقائق صباحًا، والعودة يوم الأحد العشرين من ديسمبر "
            "تقلع من لندن الرابعة عصرًا. المجموع ستة آلاف وسبعمئة وعشرة ريالات.",
            "هل أحجزها لك؟",
        ),
        (
            ("en", None),
            "I'll book you in economy, round trip: Riyadh to London, Thursday the seventeenth of "
            "December at nine ten in the morning, back on Sunday the twentieth of December at "
            "four in the afternoon from London. The total is six thousand seven hundred and ten "
            "riyals.",
            "Shall I book it?",
        ),
    ],
)
def test_the_read_back_says_the_round_trip_whole(
    read: tuple[LanguageTag, LanguageTag | None], summary: str, question: str
) -> None:
    """A Saudi reply's, an MSA caller's (an `ar-SA` reply read in `ar`) and an English one's:
    the trip's kind, the route, each leg's day and time, the travelers, the cabin and the total
    priced now, every number in words."""
    tag, wording = read
    plan = _plan(tag=tag, wording=wording)
    assert (plan.summary.text, plan.question.text) == (summary, question)
    assert plan.summary.spoken == plan.summary.text
    assert not re.search(r"\d", plan.summary.text)


@pytest.mark.parametrize(
    ("tag", "kind"), [("ar-SA", "رايح بس"), ("ar", "ذهاب فقط"), ("en", "one way")]
)
def test_a_one_way_read_back_names_its_kind_and_no_return(tag: str, kind: str) -> None:
    trip = london(one_way=True, travelers=3, cabin="business")
    reply: LanguageTag = "en" if tag == "en" else "ar-SA"
    plan = _plan(tag=reply, wording="ar" if tag == "ar" else None, trip=trip)
    text = plan.summary.text
    assert kind in text
    for back in ("والرجعة", "والعودة", "back on", "رايح جاي", "ذهاب وعودة", "round trip"):
        assert back not in text
    party = {"ar-SA": "لثلاثة أشخاص", "ar": "لثلاثة أشخاص", "en": "three travelers"}[tag]
    cabin = {"ar-SA": "درجة رجال الأعمال", "ar": "درجة رجال الأعمال", "en": "business class"}
    assert party in text and cabin[tag] in text


def test_a_draft_no_trip_filled_gives_no_legs_to_write() -> None:
    with pytest.raises(NotFilledError):
        BookingDraft().legs()
    with pytest.raises(NotFilledError):
        BookingDraft(outbound_flight=401, outbound_date=DEC_17, total_sar=10).legs()
    one_way = BookingDraft(outbound_flight=401, outbound_date=DEC_17, total_sar=10, one_way=True)
    assert len(one_way.legs()) == 1

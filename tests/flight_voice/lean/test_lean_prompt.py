"""The lean agent's declaration and prompt (flight_voice/lean/agent.py, prompt.py,
instructions/): its four tools and no action, today's languages, names and time zone; the
calendar in each reply's language (today, the next 21 days, this week and next, this weekend and
next, the Saudi week Sunday to Saturday, none before today, and the booking window's last day);
its short instructions, filled, holding the owner's rulings in both files; the library's action
rules never in its prompt; and, by D-011, no example of theirs a string of a dev call's turn."""

from __future__ import annotations

import json
import re
import tomllib
from dataclasses import replace
from datetime import date, timedelta

import pytest
from flight_voice.agent import TIME_ZONE
from flight_voice.airline.schedule import window
from flight_voice.airline.system import Airline
from flight_voice.evals.scenarios import CALLS
from flight_voice.lean.agent import NAME, declare
from flight_voice.lean.prompt import calendar, instructions
from flight_voice.lean.results import fares_are
from flight_voice.persona import PROGRESS, TAGS, Names, Tag, breaking, held_words
from t2_agentic_voice import Action, Tool, render_prompt
from t2_agentic_voice.languages import speak_number

from tests.flight_voice.lean.lean_support import lean_deps
from tests.flight_voice.scenario_dates import TODAY

LAST = window(TODAY)[1]
OTHER = Names(persona_name_en="Fahad", persona_name_ar="فهد", airline_name_en="Najm Air")
LEAN_DIR = CALLS.parents[1] / "src" / "flight_voice" / "lean" / "instructions"
# The owner's rulings of 2026-11-17, and the prompt's rules, each by a phrase both files hold.
RULES = (
    "any yes is a yes",
    "say how many flights there are, the first and last departure times, and the cheapest",
    "each flight said once; name the others only when asked",
    # f-dev-lean-4: 54 of 98 listings said the cheapest's time twice, it being the first or last.
    "when the cheapest is the first or the last, give its fare with that time",
    # f-dev-lean-3: both days of a round trip listed in one reply, and one pick taken for both.
    "On a round trip, give the way out and ask which they want. Once it is chosen, "
    "choose_flights lists the way back",
    # Leg by leg is the default, never a rule: a caller who asks about the way back first hears it.
    "When the caller asks about the way back first, list it with choose_flights' list_leg.",
    "for the leg they picked, or both when they plainly pick both",
    "when two flights fit it alike, take one and say which",
    "Say once in the call what `fares_are` says.",
    "never say that anything is on a screen",
    "Work the caller's pick out yourself from the options you have",
    "Only when a pick is truly unclear, ask, with the fares",
    # f-dev-lean-3: a total the model added up itself, blocked by the output guard.
    "say it in one sentence: the route, each leg's day and time, the cabin, the travelers and "
    "the total choose_flights gives, never a sum of your own. Then ask whether to book it.",
    "Call book_trip only after the caller agrees",
    # f-dev-lean-3: a pick said after the summary answered in words, never chosen, then booked.
    "When they pick or change something, even after the summary, make it in that same reply "
    "with choose_flights or find_flights, then say what changed, with the new total once the "
    "trip is complete, and ask again.",
    "Once book_trip says the trip is booked, say so in a few words, without the trip again",
    # Each of book_trip's statuses by its name: "can't tell" is for `unknown` alone.
    "When book_trip answers not_confirmed, do what its say says; when it answers unknown, say "
    "you cannot tell whether it went through, and never book again in this call.",
    "Say only what a tool gave in this call",
    "Never use a day the caller did not say",
    "call find_flights with that span",
    "never ask for these, and say them in the summary",
    "the booking just made gives its own reference",
    # f-dev-lean-4, f10: «كمل معي عربي» answered in Arabic, the call never moved, so the short
    # yes after it was answered under the English tag.
    "When the caller asks to go on in Arabic or in English, call switch_language if you have "
    "it, even when you answer in that language already, then answer in it.",
    # f-dev-lean-4, f20: asked for the reference of the booking just made, the model said it
    # had none.
    "or the reference of an earlier booking, call traveler_profile",
)


def test_the_lean_agent_declares_its_four_tools_and_no_action() -> None:
    agent = declare(lean_deps(Airline(today=lambda: TODAY)))
    assert agent.name == NAME and agent.time_zone == TIME_ZONE
    assert [t.name for t in agent.tools] == [
        "find_flights",
        "choose_flights",
        "book_trip",
        "traveler_profile",
    ]
    assert not any(isinstance(t, Action) for t in agent.tools)
    assert [language.tag for language in agent.languages] == ["ar-SA", "en"]
    assert agent.ask_on_uncertain_overlaps and not agent.ask_on_unlisted_answers
    for tag in TAGS:
        prompt = render_prompt(agent, tag)
        assert "An action is a tool" not in prompt and "find_flights" in prompt
        assert "$" not in prompt


def test_no_lean_tool_is_shown_with_a_reference_or_a_one_of() -> None:
    # As the scripted tools are (test_tool_schemas.py): gpt-oss on Groq fails on a `$ref`.
    agent = declare(lean_deps(Airline(today=lambda: TODAY)))
    for each in agent.tools:
        assert isinstance(each, Tool)
        text = json.dumps(dict(each.tool_schema().parameters))
        for word in ('"$ref"', '"$defs"', '"oneOf"', '"discriminator"'):
            assert word not in text, (each.name, word)
    (find,) = (t for t in agent.tools if isinstance(t, Tool) and t.name == "find_flights")
    depart = json.loads(json.dumps(dict(find.tool_schema().parameters)))["properties"]["depart"]
    assert "anyOf" in depart and "first" in json.dumps(depart)


def test_the_calendar_holds_today_three_weeks_and_the_saudi_weeks() -> None:
    text = calendar(TODAY, "en", LAST)  # Monday 16 November 2026
    assert text.startswith("Today is Monday 16 November 2026 (2026-11-16).")
    days = re.findall(r"^- (\w+) \d+ \w+ \d{4} \((\d{4}-\d{2}-\d{2})\)", text, re.MULTILINE)
    assert [d for _, d in days] == [(TODAY + timedelta(n)).isoformat() for n in range(1, 22)]
    assert days[0][0] == "Tuesday" and "(2026-11-17), tomorrow" in text
    assert "- This week: Monday 16 November 2026 (2026-11-16) to Saturday 21 November 2026" in text
    assert "This weekend: Friday 20 November 2026 (2026-11-20) and Saturday 21" in text
    assert "Next week: Sunday 22 November 2026 (2026-11-22) to Saturday 28 November" in text
    assert "Next weekend: Friday 27 November 2026 (2026-11-27) and Saturday 28" in text
    assert "Sunday to Saturday" in text and "Friday and Saturday" in text
    # The window's last day, so a day past the 21 is searched (f-dev-lean-3 refused one).
    assert text.endswith(
        "- Bookings are open up to Tuesday 16 March 2027 (2027-03-16): any day up to it can be "
        "searched, listed above or not."
    )


def test_on_a_saturday_this_weekend_is_today_alone() -> None:
    saturday = date(2026, 11, 21)
    text = calendar(saturday, "en", window(saturday)[1])
    assert "- This weekend: Saturday 21 November 2026 (2026-11-21)." in text
    assert "- This week: Saturday 21 November 2026 (2026-11-21) to Saturday 21" in text


def test_the_arabic_calendar_is_written_in_arabic() -> None:
    text = calendar(TODAY, "ar-SA", LAST)
    assert text.startswith("اليوم الاثنين 16 نوفمبر 2026 (2026-11-16).")
    assert "الثلاثاء 17 نوفمبر 2026 (2026-11-17)، غدًا" in text
    assert "عطلة هذا الأسبوع: الجمعة 20 نوفمبر 2026 (2026-11-20) والسبت 21" in text
    assert "- الحجز مفتوح حتى الثلاثاء 16 مارس 2027 (2027-03-16):" in text


@pytest.mark.parametrize("tag", TAGS)
def test_the_instructions_are_short_filled_and_hold_the_rulings(tag: Tag) -> None:
    text = instructions(OTHER, TODAY, LAST)[tag]
    assert "$" not in text and "Fahad" in text and "Najm Air" in text and "Khalid" in text
    assert calendar(TODAY, tag, LAST) in text
    own = (LEAN_DIR / f"{tag}.md").read_text(encoding="utf-8").splitlines()
    assert 25 <= len(own) <= 35
    assert [rule for rule in RULES if rule not in text] == []
    assert "screen" in text and "markdown" in text


def test_the_saudi_file_keeps_the_register_lines() -> None:
    text = instructions(Names(), TODAY, LAST)["ar-SA"]
    for line in (
        '"now" is «الحين», never «الآن»',
        # f-dev-lean-3: MSA callers answered «ما فيه… تبي» on a turn with no tool.
        # The owner, 2026-11-18: the register held for the call, never changed in it.
        "Speak the register the last section of these instructions names, the same in every "
        "reply of the call",
        "In Modern Standard Arabic, keep every reply in MSA, a short one too",
        # The owner, 2026-11-18: the Najdi replies did not sound Najdi.
        "say «فيه» and «عندنا», never «يوجد» or «لدينا», «اللي», never «الذي» or «التي»",
        "Never repeat the caller's words back to them",
        "never with «ودك», «وين», «تبي», «اللي», «ما فيه», «أبشر» or «الحين»",
        "say a result's `route_msa`, `trip_msa` and `fares_are_msa` in place of the field beside "
        "each",
        # f-dev-lean-3: «ستطعش» (the 16th) said after a day's times, taken for a time.
        "A Saudi caller says 11 to 19 the Najdi way, ending in «طعش»; a bare number said to name "
        "or correct a day is that day of the month, not a time.",
        # f-dev-lean-4, f01 and f30: «حجزت لك» said of a trip only chosen, the run's three
        # violations; and «أبغى أحجز؟» for "shall I book it?" in 6 plays.
        "until then a flight is chosen («اخترت لك رحلة الصبح»، «رحلتك من الرياض لجدة…»), and a "
        "booking word («حجزت», «تم الحجز») comes once book_trip has booked.",
        "«تبيني أحجزها؟»",
        "«هل أحجزها لك؟»",
        # f-dev-lean-4, f16 and f32: the failure section's one example was Saudi.
        "to an MSA caller «لم أستطع التحقق الآن، هل أعيد المحاولة؟»",
    ):
        assert line in text


def test_the_english_file_keeps_its_digits_over_its_own_spoken_history() -> None:
    # f-dev-lean-4: 12 of 102 English replies wrote numbers in words, each after a reply whose
    # history held its numbers as they were said.
    text = instructions(Names(), TODAY, LAST)["en"]
    assert "in digits, as the tools give them, even where your earlier replies show them in" in text


def _bare(text: str) -> str:
    return " ".join(re.sub(r"[^\w\s]", " ", text.lower()).split())


def _strings(node: object) -> list[str]:
    if isinstance(node, str):
        return [node]
    if isinstance(node, dict):
        return [s for value in node.values() for s in _strings(value)]
    if isinstance(node, list):
        return [s for item in node for s in _strings(item)]
    return []


def test_no_lean_example_is_a_dev_calls_line() -> None:
    # D-011, the lean twin of test_agent.py's: only the dev calls (f*) are read.
    said = {
        _bare(s)
        for path in CALLS.glob("f*.toml")
        for turn in tomllib.loads(path.read_text(encoding="utf-8"))["turns"]
        for s in _strings(turn)
    }
    assert _bare("لا خلها ستطعش") in said  # the search finds a line once pasted (f27)
    texts = [
        text
        for network in ("mock", "real")
        for text in instructions(Names(), TODAY, LAST, network=network).values()
    ]
    quoted = [q for text in texts for q in re.findall(r'[«"]([^»"]+)[»"]', text)]
    assert len(quoted) >= 10
    assert [q for q in quoted if _bare(q) in said] == []


@pytest.mark.parametrize("tag", TAGS)
def test_the_mock_lines_change_only_on_another_search_and_a_price_as_given(tag: Tag) -> None:
    text = instructions(Names(), TODAY, LAST)[tag]
    for kept in ("Every flight starts or ends in Riyadh.", "Then ask whether to book it."):
        assert kept in text
    assert "- For another cabin, number of travelers, day or city, call find_flights again." in text
    assert "Say a price as the tool gives it; never divide or multiply one." in text
    assert "call choose_flights with it;" not in text and "Bookings are open up to" in calendar(
        TODAY, "en", LAST
    )


@pytest.mark.parametrize("tag", TAGS)
def test_the_real_lines_name_every_airline_and_book_nothing(tag: Tag) -> None:
    text = instructions(Names(), TODAY, LAST, network="real")[tag]
    assert "$" not in text and "the travel assistant of T2 Air" in text
    for gone in ("Every flight starts or ends in Riyadh.", "ask whether to book", "book_trip"):
        assert gone not in text, gone
    for held in (
        "and others, nonstop or with one stop",
        "the airline's own site books it",
        "never say a trip is booked",
        '"Saudia 1020"',
        "unknown_days",
        "checked_last",
        "the airlines do not show flights that far ahead yet",
        "Hotels, cars, visas, seats on the plane, meals, baggage, booking",
        "Say a price as the tool gives it; never divide or multiply one.",
    ):
        assert held in text, held
    opened = "Flights can be searched up to" if tag == "en" else "يمكن البحث عن الرحلات حتى"
    assert opened in text and "Bookings are open" not in text and "الحجز مفتوح" not in text
    if tag == "ar-SA":
        assert "«فيها ترانزيت في دبي ساعتين»" in text


def test_no_basis_of_a_price_holds_a_digit_word() -> None:
    numbers = {speak_number(n, language="en") for n in range(1, 10)}
    numbers |= {
        speak_number(n, language="ar-SA", register=r)
        for n in range(1, 10)
        for r in ("saudi", "msa")
    }
    for network in ("mock", "real"):
        for travelers in (1, 2):
            for round_trip in (True, False):
                for tag in ("en", "ar-SA", "ar"):
                    said = fares_are(
                        tag, round_trip=round_trip, travelers=travelers, network=network
                    )
                    for text in (t for t in said if t):
                        words = set(re.findall(r"\w+", text.lower()))
                        assert not words & numbers and not re.search(r"\d", text), text
                        assert travelers == 1 or "للشخص" not in text


def test_the_live_search_lines_pass_the_lines_rule() -> None:
    assert breaking(Names()) == ()
    for tag in TAGS:
        lines = PROGRESS[tag]["searching_live"]
        assert lines and all(
            held_words(line, "en" if tag == "en" else "ar") == () for line in lines
        )


def test_the_real_network_declares_its_own_terms_and_no_booking() -> None:
    deps = replace(
        lean_deps(),
        bookable=False,
        network="real",
        terms=("Riyadh", "Saudia"),
        pronounce={"SV": {"en": "ess vee", "ar": "إس في"}},
    )
    agent = declare(deps)
    assert [t.name for t in agent.tools] == ["find_flights", "choose_flights", "traveler_profile"]
    assert agent.vocabulary is not None and agent.vocabulary.terms == ("Riyadh", "Saudia", "T2 Air")
    assert dict(agent.pronounce)["SV"] == {"en": "ess vee", "ar": "إس في"}
    assert "T2" in dict(agent.pronounce)
    assert "the travel assistant of" in render_prompt(agent, "en")

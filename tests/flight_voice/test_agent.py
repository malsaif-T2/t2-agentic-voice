"""The flight agent's declaration (flight_voice/agent.py) and its persona (persona.py): it builds,
in Saudi Arabic and English, with the seven read tools and the booking, Riyadh's time zone, and
the chat model's judgement of uncertain overlaps and unlisted answers; its greetings, its
pronunciation of the airline's code, its vocabulary and its instructions built from the names,
a name of the test's own reaching every one of them; the instructions holding run F's rules of
2026-11-17 (from f-dev-4's and f-dev-5's diagnoses), their Arabic examples in the register run F
reads, no example of theirs or of the pick's schema any string of a dev call's turn, and the
result fields they name; and every line a call speaks as written held to the lines' rule, the
presets' yes words included."""

from __future__ import annotations

import json
import re
import tomllib
from datetime import timedelta
from typing import Final, Literal

import pytest
from flight_voice import persona
from flight_voice.agent import NAME, VERSION, declare
from flight_voice.airline.system import Airline
from flight_voice.evals.scenarios import CALLS
from flight_voice.evals.spoken import register_held
from flight_voice.persona import TAGS, Names, breaking, held_words, spoken_lines
from flight_voice.tools.profile import ProfileAnswer, TripSaid
from flight_voice.tools.results import Listing, NotServed, Option
from flight_voice.trip import TripBook
from t2_agentic_voice import Action, Tool
from t2_agentic_voice.domain.yes_words import PRESET_CONSENT
from t2_agentic_voice.languages import normalize_arabic, provider_text

from tests.flight_voice.scenario_dates import TODAY

OTHER = Names(
    persona_name_en="Fahad",
    persona_name_ar="فهد",
    airline_name_en="Najm Air",
    airline_name_ar="طيران نجم",
    airline_code="NJ",
    airline_code_said_en="en jay",
    airline_code_said_ar="إن جي",
)
TOOLS = (
    "search_flights",
    "choose_flight",
    "change_trip",
    "get_trip",
    "fare_calendar",
    "compare_cabins",
    "traveler_profile",
)


def test_the_declaration_builds_with_its_tools_and_its_booking() -> None:
    agent = declare(Airline(today=lambda: TODAY), TripBook())
    assert agent.name == NAME
    assert agent.version == VERSION
    assert [language.tag for language in agent.languages] == ["ar-SA", "en"]
    reads = [t.name for t in agent.tools if not isinstance(t, Action)]
    assert tuple(reads) == TOOLS
    assert [t.name for t in agent.tools if isinstance(t, Action)] == ["book_trip"]
    assert agent.time_zone == timedelta(hours=3)
    assert agent.ask_on_uncertain_overlaps
    assert agent.ask_on_unlisted_answers


def test_the_default_names_are_the_owners_picks() -> None:
    agent = declare(Airline(today=lambda: TODAY), TripBook())
    saudi, english = (language.greeting for language in agent.languages)
    assert "سعد" in saudi and "طيران تي تو" in saudi and "خالد" in saudi
    assert "Saad" in english and "T2 Air" in english and "Khalid" in english
    assert dict(agent.pronounce["T2"]) == {"ar": "تي تو", "en": "tee two"}
    assert "T2 Air" in agent.vocabulary.terms


def test_another_name_reaches_the_greetings_the_pronunciation_and_the_vocabulary() -> None:
    agent = declare(Airline(today=lambda: TODAY), TripBook(), OTHER)
    saudi, english = (language.greeting for language in agent.languages)
    assert "فهد" in saudi and "طيران نجم" in saudi
    assert "Fahad" in english and "Najm Air" in english
    assert "Saad" not in english and "سعد" not in saudi
    assert dict(agent.pronounce["NJ"]) == {"ar": "إن جي", "en": "en jay"}
    assert "T2" not in agent.pronounce
    assert "Najm Air" in agent.vocabulary.terms
    assert "T2 Air" not in agent.vocabulary.terms


def test_the_instructions_are_filled_with_the_names_in_each_language() -> None:
    filled = persona.instructions(OTHER)
    assert set(filled) == set(TAGS)
    for text in filled.values():
        assert "$" not in text
        assert "Fahad" in text and "Najm Air" in text and "Khalid" in text
        assert "book_trip" in text and "traveler_profile" in text
    assert "فهد" in filled["ar-SA"] and "طيران نجم" in filled["ar-SA"]


# Run F's rules of 2026-11-17, each by the scenarios whose diagnosis asked it: a phrase that
# carries it, in both files.
RULES: Final = {
    "date_whole_f07": 'its month\'s full name ("Friday, March 5"',
    "date_never_short_f07": "never shorten a month or a weekday",
    "defaults_never_asked_f06": "never ask for them and never say that you assumed them",
    "defaults_changed_when_said": "Change any of them when the caller says so.",
    "search_in_that_reply_f06_f09": (
        "Once the caller has said where they go and the day they leave, and for a round trip "
        "the day they come back, call search_flights in that same reply, with no question first"
    ),
    "no_day_confirmed_f05_f09_f23": "never ask them to confirm a day they said or anything you",
    "no_day_filled_in_c1": "never fill in a day they did not say",
    "the_pick_lists_the_return_c1": "call choose_flight with their pick (its result lists",
    "no_search_for_a_pick_or_cabin_c1": (
        "Once flights are listed, call change_trip when they change the cabin, the number of "
        "travelers or one way, and never search again for that or for a pick"
    ),
    "a_bare_correction_is_a_day_f27": "A number said alone as a correction after a listing",
    "a_pick_in_its_kind_f09_f10_f16_f25_f26_f28": (
        "Pass a pick in the kind the caller said it, to choose_flight and compare_cabins alike: "
        "a part of the day as its part, a comparison of when it leaves as the earliest or the "
        "latest, a place in the list only for a number or an order word they said or for the "
        "only flight listed, and a time only for a time they said."
    ),
    "a_pick_never_turned_f09_f26": (
        "Never turn a pick into the time or the number of the flight you think it is, even one "
        "a tool already named."
    ),
    "the_same_trip_f17": "keep its city, travelers and cabin and ask when they leave",
    "its_dates_passed_f17": "its dates have passed, so never offer them or search with them",
    "no_second_booking_f19": "cannot be booked again in this call, with no offer to try again",
    "the_reference_looked_up_f20": "get it from traveler_profile",
    "never_declined_unlooked_f20": "never say you do not have it before you call it",
}
# Each file's own examples: a return in days after leaving (nights), a departure in days, a
# bare day said as a correction, and a pick of each kind but a time (f-dev-5); in Arabic, the
# Saudi "now" and retry line (f12, f19), and the MSA forms for an MSA caller with the tools' MSA
# words, from the first reply (f28, f03).
_PICKS_EN: Final = '"the lowest fare", "option three", "the afternoon one", "the last flight out"'
EXAMPLES: Final = {
    "en": (
        '"back four days later" four nights after leaving',
        '"leave in four days" four days from today',
        '("no, the 19th")',
        f"({_PICKS_EN})",
    ),
    "ar-SA": (
        "«أرجع بعد أربع أيام» four nights after leaving",
        "«أسافر بعد أربع أيام» four days from today",
        "(«لا، تسعطعش»)",
        '"now" is «الحين», never «الآن»',
        "«ما قدرت أشيك الحين، تبي أجرب مرة ثانية؟»",
        "(«إلى أين تودّ السفر؟», «متى تودّ العودة؟», «الآن»), never with «ودك», «وين» or «الحين»",
        "say a tool's `*_said_msa` words in place of its `*_said` ones",
        "Your greeting is in Saudi; once the caller speaks MSA, every reply is in MSA, from your "
        "first one.",
        "when they leave («متى ودك تسافر؟», to an MSA caller «متى تودّ السفر؟»)",
        f"({_PICKS_EN}, «أرخص وحدة», «رقم ثلاثة», «اللي الظهر», «آخر وحدة تطلع», to an MSA caller "
        "«الرحلة الليلية»)",
    ),
}
SAUDI_EXAMPLES: Final = (
    "ما قدرت أشيك الحين، تبي أجرب مرة ثانية؟",
    "متى ودك تسافر؟",
    "اللي الظهر",
    "آخر وحدة تطلع",
)
MSA_EXAMPLES: Final = ("إلى أين تودّ السفر؟", "متى تودّ العودة؟", "متى تودّ السفر؟", "الرحلة الليلية")


@pytest.mark.parametrize("tag", TAGS)
@pytest.mark.parametrize("rule", list(RULES))
def test_the_instructions_hold_run_fs_rules(tag: persona.Tag, rule: str) -> None:
    assert RULES[rule] in persona.instructions(Names())[tag]


@pytest.mark.parametrize("tag", TAGS)
def test_the_instructions_hold_their_own_languages_examples(tag: persona.Tag) -> None:
    text = persona.instructions(Names())[tag]
    assert [e for e in EXAMPLES[tag] if e not in text] == []


def test_the_arabic_examples_are_in_the_register_run_f_reads() -> None:
    text = persona.instructions(Names())["ar-SA"]
    for line in SAUDI_EXAMPLES:
        assert f"«{line}»" in text and register_held(line, "saudi"), line
    for line in MSA_EXAMPLES:
        assert f"«{line}»" in text and register_held(line, "msa"), line


def _bare(text: str) -> str:
    return " ".join(re.sub(r"[^\w\s]", " ", text.lower()).split())


def _strings(node: object) -> list[str]:
    """Every string in a scenario's turn: its line, its checks' words and its arguments."""
    if isinstance(node, str):
        return [node]
    if isinstance(node, dict):
        return [s for value in node.values() for s in _strings(value)]
    if isinstance(node, list):
        return [s for item in node for s in _strings(item)]
    return []


def _pick_texts() -> list[str]:
    """The pick's descriptions as the talker is shown them in choose_flight's schema (the
    compare_cabins one is the same, tests/flight_voice/tools/test_cabins.py)."""
    agent = declare(Airline(today=lambda: TODAY), TripBook())
    (choose,) = (t for t in agent.tools if isinstance(t, Tool) and t.name == "choose_flight")
    shown = json.loads(json.dumps(dict(choose.tool_schema().parameters)))["properties"]["choice"]
    return [shown["description"], *(kind["description"] for kind in shown["anyOf"])]


def test_no_example_is_a_dev_calls_line() -> None:
    # D-011: an example is written for its pattern, never copied from a scripted call. Only the
    # dev calls (f*) are read; the held-out ones stay closed.
    said = {
        _bare(s)
        for path in CALLS.glob("f*.toml")
        for turn in tomllib.loads(path.read_text(encoding="utf-8"))["turns"]
        for s in _strings(turn)
    }
    assert _bare("لا خلها ستطعش") in said  # the search finds a line once pasted (f27)
    assert _bare("المسائية") in said  # and a check's word (f16's said_any)
    picks = _pick_texts()
    assert len(picks) == 7 and all('"' in text for text in picks[1:])
    texts = (*EXAMPLES["en"], *EXAMPLES["ar-SA"], *picks)
    quoted = [q for text in texts for q in re.findall(r'[«"]([^»"]+)[»"]', text)]
    assert [q for q in (*quoted, *SAUDI_EXAMPLES, *MSA_EXAMPLES) if _bare(q) in said] == []


def test_the_result_fields_the_instructions_name_are_the_tools() -> None:
    assert "booked" in ProfileAnswer.model_fields
    for model in (Option, Listing, NotServed, TripSaid):
        msa = [name for name in model.model_fields if name.endswith("_said_msa")]
        assert msa and all(name.removesuffix("_msa") in model.model_fields for name in msa)


def test_the_progress_lines_cover_each_key_the_tools_name() -> None:
    agent = declare(Airline(today=lambda: TODAY), TripBook())
    for language in agent.languages:
        assert set(language.progress) == {"searching", "fares"}


def _form(text: str) -> str:
    return f" {' '.join(normalize_arabic(provider_text(text)).lower().split())} "


@pytest.mark.parametrize("names", [Names(), OTHER], ids=["owners", "others"])
def test_no_line_holds_a_command_send_yes_or_claim_word(names: Names) -> None:
    for tag, said in spoken_lines(names).items():
        code: Literal["ar", "en"] = "en" if tag == "en" else "ar"
        yes = PRESET_CONSENT[code]
        for line in said:
            assert held_words(line, code) == ()
            form = _form(line.replace(",", " ").replace("،", " ").replace(".", " "))
            assert [w for w in (*yes.yes, *yes.send) if _form(w) in form] == []
    assert breaking(names) == ()


def test_the_rule_names_only_the_name_that_breaks_it() -> None:
    assert breaking(OTHER.model_copy(update={"airline_name_en": "Stop Air"})) == (
        "airline_name_en",
    )
    assert held_words("Hi, this is Wait Air.", "en") == ("wait",)
    assert held_words("Hi Khalid, booking confirmed.", "en") == ("booking confirmed",)

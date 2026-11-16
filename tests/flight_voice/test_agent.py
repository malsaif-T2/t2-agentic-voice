"""The flight agent's declaration (flight_voice/agent.py) and its persona (persona.py): it builds,
in Saudi Arabic and English, with the seven read tools and the booking, Riyadh's time zone, and
the chat model's judgement of uncertain overlaps and unlisted answers; its greetings, its
pronunciation of the airline's code, its vocabulary and its instructions built from the names,
a name of the test's own reaching every one of them; and every line a call speaks as written
held to the lines' rule, the presets' yes words included."""

from __future__ import annotations

from datetime import timedelta
from typing import Literal

import pytest
from flight_voice import persona
from flight_voice.agent import NAME, VERSION, declare
from flight_voice.airline.system import Airline
from flight_voice.persona import TAGS, Names, breaking, held_words, spoken_lines
from flight_voice.trip import TripBook
from t2_agentic_voice import Action
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

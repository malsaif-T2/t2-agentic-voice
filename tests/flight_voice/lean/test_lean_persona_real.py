"""The persona on the real network (plan 011, the owner's of 2026-11-18: "Saad, T2 flight
assistant"): the greeting names Saad the flight assistant of T2 in English and in Najdi Arabic,
the traveler named as today; the instructions' first line says so, and the Arabic names the
company «تي تو»; the mock keeps T2 Air's greeting and lines; and every greeting passes the lines'
rule."""

from __future__ import annotations

from dataclasses import replace

from flight_voice.lean.agent import declare
from flight_voice.lean.prompt import instructions
from flight_voice.persona import TAGS, Names, breaking, greeting, held_words

from tests.flight_voice.lean.lean_support import lean_deps
from tests.flight_voice.scenario_dates import TODAY

REAL_EN = "Hi Khalid, this is Saad, the T2 flight assistant. Where would you like to fly?"
REAL_AR = "هلا خالد، معك سعد، مساعد الرحلات في تي تو. وين ودّك تسافر؟"


def _greetings(network: str) -> dict[str, str]:
    deps = lean_deps()
    if network == "real":
        deps = replace(deps, bookable=False, network="real")
    return {lang.tag: lang.greeting for lang in declare(deps).languages}


def test_the_real_network_greets_as_t2s_flight_assistant() -> None:
    assert greeting("en", Names(), network="real") == REAL_EN
    assert greeting("ar-SA", Names(), network="real") == REAL_AR
    held = _greetings("real")
    assert held["en"] == REAL_EN and held["ar-SA"] == REAL_AR


def test_the_mock_keeps_t2_airs_greeting() -> None:
    held = _greetings("mock")
    assert held["en"] == greeting("en", Names()) and "T2 Air's voice assistant" in held["en"]
    assert "طيران تي تو" in held["ar-SA"]


def test_every_greeting_passes_the_lines_rule() -> None:
    for network in ("mock", "real"):
        for tag in TAGS:
            said = greeting(tag, Names(), network=network)
            assert held_words(said, "en" if tag == "en" else "ar") == (), said
    assert breaking(Names()) == ()


def test_the_real_instructions_open_on_t2s_flight_assistant() -> None:
    last = TODAY.replace(year=TODAY.year + 1)
    real = instructions(Names(), TODAY, last, network="real")
    assert real["en"].startswith(
        "You are Saad, the flight assistant of T2, the company, who finds flights of every airline."
    )
    assert real["ar-SA"].startswith("You are Saad (سعد), the flight assistant of T2 («تي تو»)")
    assert "name yourself سعد and the company تي تو" in real["ar-SA"]
    mock = instructions(Names(), TODAY, last)
    assert "name yourself سعد and the airline طيران تي تو" in mock["ar-SA"]
    assert "flight assistant of T2" not in mock["en"]

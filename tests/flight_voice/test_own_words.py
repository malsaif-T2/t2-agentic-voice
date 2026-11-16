"""The flight agent speaks in its own words, never the public demo's (the build spec's 6.1): its
greetings, progress lines, instructions, tool descriptions, `say` hints and failure messages,
and its page's texts, hold none of the demo's own strings, read case-blind."""

from __future__ import annotations

from typing import Final

from flight_voice import persona
from flight_voice.agent import declare
from flight_voice.airline.system import Airline
from flight_voice.persona import Names
from flight_voice.server import WEB
from flight_voice.tools import results
from flight_voice.trip import TripBook

from tests.flight_voice.scenario_dates import TODAY

# The public demo's own strings, which no text of ours holds.
DEMO: Final = (
    "where to,",
    "again?",
    "best fare",
    "reset demo",
    "my bookings",
    "show chat",
    "start a conversation",
    "explore flights",
    "select flight",
    "flexible dates",
)


def agent_texts() -> list[str]:
    """Every text of the agent the talker or the caller meets: the greetings and progress
    lines, the instructions, each tool's description, the results' hints and failures."""
    agent = declare(Airline(today=lambda: TODAY), TripBook())
    texts = [line for said in persona.spoken_lines(Names()).values() for line in said]
    texts += list(persona.instructions(Names()).values())
    texts += [tool.description for tool in agent.tools]
    texts += list(results.SAY.values())
    texts += [results.SEARCH_FAILED, results.PROFILE_FAILED]
    return texts


def held(texts: list[str]) -> list[tuple[str, str]]:
    """Each demo string a text holds, with the text's start."""
    return [(phrase, text[:40]) for text in texts for phrase in DEMO if phrase in text.lower()]


def test_the_agents_texts_hold_none_of_the_demos_strings() -> None:
    texts = agent_texts()
    assert len(texts) > 20
    assert held(texts) == []


def test_the_pages_texts_hold_none_of_the_demos_strings() -> None:
    texts = [(WEB / name).read_text(encoding="utf-8") for name in ("texts.js", "index.html")]
    assert held(texts) == []


def test_the_check_finds_a_demo_string() -> None:
    assert held(["Show Chat here"]) == [("show chat", "Show Chat here")]

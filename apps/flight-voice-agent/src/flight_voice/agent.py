"""The flight agent's declaration (D-101): what the app hands the library's runtime.

The talker speaks Saudi Arabic first, then English, answering a caller who speaks Modern
Standard Arabic in it; its instructions (instructions/, one file a language, filled with the
persona's names by persona.py) are written for the ear: short spoken replies, a day's flights
said briefly (one or two by departure time and fare, three or four by their count, first and
last times and the cheapest, the owner's ruling), dates passed as the caller said them (a span
of days searched at once) and resolved in code, numbers in digits, nothing ever said to be on a
screen, a booking only after the read-back and a spoken yes, which the talker never asks for
itself.
Its tools are the seven read tools over the mock airline and the call's trip (tools/,
`flight_tools`) and the one action, `book_trip` (booking/); its greetings and progress lines,
its pronunciation of the airline's code and its vocabulary are the persona's, built from the
settings' names, so nothing here holds a name.

- **The time zone** is Riyadh's fixed UTC+3 (D-106), so the prompt's "Today is" reads the day
  the airline counts in.
- **A chat model** decides a short overlap the rule would let go on (`ask_on_uncertain_overlaps`,
  D-069), and judges an answer to the read-back that the yes rule's lists leave unplaced, within
  its rails (`ask_on_unlisted_answers`, D-082), as Ole5's talker with its tickets does.
- **The version** is stamped on every trace: the date of the last change to the instructions,
  the tools' texts or the lines, and the change of that day.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Final

from t2_agentic_voice import Language, VoiceAgent

from flight_voice import persona
from flight_voice.airline.dates import RIYADH
from flight_voice.airline.system import Airline
from flight_voice.booking.action import book_trip
from flight_voice.persona import Names
from flight_voice.tools import flight_tools
from flight_voice.trip import TripBook

NAME: Final = "flight"
VERSION: Final = "2026-11-17.4"
# Riyadh's offset from UTC, all year (D-106).
TIME_ZONE: Final = RIYADH.utcoffset(None) or timedelta(hours=3)


def languages(names: Names) -> list[Language]:
    """Saudi Arabic, then English, each with its greeting and progress lines."""
    return [
        Language.saudi_arabic(
            greeting=persona.greeting("ar-SA", names), progress=persona.PROGRESS["ar-SA"]
        ),
        Language.english(greeting=persona.greeting("en", names), progress=persona.PROGRESS["en"]),
    ]


def declare(airline: Airline, trips: TripBook, names: Names | None = None) -> VoiceAgent:
    """The talker over `airline`, each call's trip kept in `trips`, named by `names` (the
    owner's picks unless given): the module's docstring."""
    named = Names() if names is None else names
    return VoiceAgent(
        name=NAME,
        version=VERSION,
        languages=languages(named),
        pronounce=persona.pronounce(named),
        instructions=persona.instructions(named),
        tools=[*flight_tools(airline, trips), book_trip(airline, trips)],
        vocabulary=persona.vocabulary(named),
        ask_on_uncertain_overlaps=True,
        ask_on_unlisted_answers=True,
        time_zone=TIME_ZONE,
    )

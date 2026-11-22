"""The lean agent's declaration (D-113): what the app hands the library's runtime when the
setting `FLIGHT_VOICE_AGENT` is `lean` (server.py), and what run F plays under `--agent lean`.

It speaks as today's agent does (the same languages, greetings, progress lines, pronunciation of
the airline's code and vocabulary, agent.py's and persona.py's; on the real network the greeting
is the real network's, Saad as T2's flight assistant), in Riyadh's time zone, with its
own short instructions and calendar (prompt.py) and its tools over its sources (deps.py):
`find_flights`, `choose_flights`, `book_trip` (only where the line books: the mock; on the real
network the links to book on the airline's site are on the cards the moment a flight is chosen,
D-126, D-130, with no tool, and `choose_flights` declares the booking's claims), and today's
`traveler_profile` (the mock's alone). On the real network the vocabulary's terms are the
network's own (they replace persona.py's, so the speech-to-text prompt keeps its stop words)
and its pronunciations are added to the airline code's. It declares no action, so the
library adds no action rules to its prompt and reads back nothing; `book_trip` books once the
booking check holds. A chat model still decides a short overlap the rule would let go on
(`ask_on_uncertain_overlaps`, D-069): the voice layer is the same as today's.

The booking check reads the call's events: the app registers `check.observed` for each kind of
`OBSERVED` (server.py), and run F's lean play reads the call's own (`read_from`).

**The calendar's day.** The instructions are the library's `Dated` kind (D-135): the library
asks for them on each request, and they are written for the airline's today, the day the tools
read (Riyadh's, or the day pinned), once a day for both languages and kept (`dated`), so a
request pays a lookup, not a build, and the prompt's text is the same all day. A server left
running past midnight prompts with the new day's calendar (the owner's calls of 2026-11-22 ran
on 19 November's, on a server started on the 19th). Each call logs an error
(`calendar_watch`: `lean_calendar_stale`) when the airline's today is not Riyadh's, pinned to
another day: the library's "Today is …" reads the clock, so the prompt holds two todays.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import date
from functools import lru_cache
from typing import Final

from t2_agentic_voice import Tool, Vocabulary, VoiceAgent, get_logger
from t2_agentic_voice.events import Event

from flight_voice import persona
from flight_voice.agent import TIME_ZONE, languages
from flight_voice.airline.system import live_today
from flight_voice.lean import prompt
from flight_voice.lean.book import book_trip
from flight_voice.lean.booking_check import OBSERVED
from flight_voice.lean.choose import choose_flights
from flight_voice.lean.deps import LeanDeps
from flight_voice.lean.find import find_flights
from flight_voice.persona import TAGS, Names
from flight_voice.said import Tag
from flight_voice.tools.profile import traveler_profile

NAME: Final = "flight-lean"
VERSION: Final = "lean-2026-11-22.1"

__all__ = ["NAME", "OBSERVED", "VERSION", "calendar_watch", "dated", "declare", "lean_tools"]

log = get_logger(__name__)


def calendar_watch(
    day: Callable[[], date], now: Callable[[], date] = live_today
) -> Callable[[Event], Awaitable[None]]:
    """An observer of each `CallStarted`: an error logged when the calendar's day, as `day`
    reads it, is not Riyadh's today as `now` reads it (the module's docstring)."""

    async def watch(event: Event) -> None:
        written, today = day(), now()
        if today != written:
            log.error("lean_calendar_stale", calendar=written.isoformat(), riyadh=today.isoformat())

    return watch


def lean_tools(deps: LeanDeps) -> tuple[Tool, ...]:
    """The tools over `deps`: `book_trip` only where the line books, `traveler_profile` only on
    the mock."""
    booking = (book_trip(deps),) if deps.bookable else ()
    # The real network has no profile: anyone at the company calls (the owner, 2026-11-18).
    profile = (traveler_profile(deps.airline),) if deps.network == "mock" else ()
    return (find_flights(deps), choose_flights(deps), *booking, *profile)


def dated(deps: LeanDeps, names: Names) -> Callable[[date, Tag], str]:
    """The lean instructions as the library asks for them on each request (the module's
    docstring): written for the airline's today, once a day, and kept."""

    @lru_cache(maxsize=2)  # today's and, past midnight, yesterday's for a call still on it
    def written(day: date) -> dict[Tag, str]:
        last = deps.data.last_day(day)
        return prompt.instructions(names, day, last, network=deps.network)

    def instructions(_today: date, tag: Tag) -> str:
        return written(deps.today())[tag]

    return instructions


def declare(deps: LeanDeps, names: Names | None = None) -> VoiceAgent:
    """The lean talker over `deps`, named by `names` (the owner's picks unless given): the
    module's docstring."""
    named = Names() if names is None else names
    instructions = dated(deps, named)
    today = deps.today()
    for tag in TAGS:  # written now: a file or calendar fault stops the start, as before
        instructions(today, tag)
    pronounce = persona.pronounce(named) | {k: dict(v) for k, v in deps.pronounce.items()}
    terms = persona.TERMS if deps.terms is None else deps.terms
    return VoiceAgent(
        name=NAME,
        version=VERSION,
        languages=languages(named, deps.network),
        pronounce=pronounce,
        instructions=instructions,
        tools=lean_tools(deps),
        vocabulary=Vocabulary(terms=(*terms, named.airline_name_en)),
        ask_on_uncertain_overlaps=True,
        time_zone=TIME_ZONE,
    )

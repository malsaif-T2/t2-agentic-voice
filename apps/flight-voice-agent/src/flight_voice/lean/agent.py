"""The lean agent's declaration (D-113): what the app hands the library's runtime when the
setting `FLIGHT_VOICE_AGENT` is `lean` (server.py), and what run F plays under `--agent lean`.

It speaks as today's agent does (the same languages, greetings, progress lines, pronunciation of
the airline's code and vocabulary, agent.py's and persona.py's; on the real network the greeting
is the real network's, Saad as T2's flight assistant), in Riyadh's time zone, with its
own short instructions and calendar (prompt.py) and its tools over its sources (deps.py):
`find_flights`, `choose_flights`, `book_trip` (only where the line books: the mock), on the
real network `booking_link` in its place (the link to book the trip on the airline's site,
D-126), and today's `traveler_profile`. On the real network the vocabulary's terms are the
network's own (they replace persona.py's, so the speech-to-text prompt keeps its stop words)
and its pronunciations are added to the airline code's. It declares no action, so the
library adds no action rules to its prompt and reads back nothing; `book_trip` books once the
booking check holds. A chat model still decides a short overlap the rule would let go on
(`ask_on_uncertain_overlaps`, D-069): the voice layer is the same as today's.

The booking check reads the call's events: the app registers `check.observed` for each kind of
`OBSERVED` (server.py), and run F's lean play reads the call's own (`read_from`).

**The calendar's day.** The calendar is written once, as the agent is declared, while the
library writes "Today is …" from the clock on every turn; so a server keeps the calendar's day as
its airline's today (server.py), and each call it takes logs an error (`calendar_watch`:
`lean_calendar_stale`) when that day is not Riyadh's today, left running past midnight or pinned
to another day: two todays in the prompt, until it is restarted.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import date
from typing import Final

from t2_agentic_voice import Tool, Vocabulary, VoiceAgent, get_logger
from t2_agentic_voice.events import Event

from flight_voice import persona
from flight_voice.agent import TIME_ZONE, languages
from flight_voice.airline.system import live_today
from flight_voice.lean import prompt
from flight_voice.lean.book import book_trip
from flight_voice.lean.booking_check import OBSERVED
from flight_voice.lean.booking_link import booking_link
from flight_voice.lean.choose import choose_flights
from flight_voice.lean.deps import LeanDeps
from flight_voice.lean.find import find_flights
from flight_voice.persona import Names
from flight_voice.tools.profile import traveler_profile

NAME: Final = "flight-lean"
VERSION: Final = "lean-2026-11-18.5"

__all__ = ["NAME", "OBSERVED", "VERSION", "calendar_watch", "declare", "lean_tools"]

log = get_logger(__name__)


def calendar_watch(
    day: date, now: Callable[[], date] = live_today
) -> Callable[[Event], Awaitable[None]]:
    """An observer of each `CallStarted`: an error logged when the calendar's `day` is not
    Riyadh's today as `now` reads it (the module's docstring)."""

    async def watch(event: Event) -> None:
        today = now()
        if today != day:
            log.error("lean_calendar_stale", calendar=day.isoformat(), riyadh=today.isoformat())

    return watch


def lean_tools(deps: LeanDeps) -> tuple[Tool, ...]:
    """The tools over `deps`: `book_trip` only where the line books, `booking_link` only on the
    real network, `traveler_profile` only on the mock."""
    booking = (book_trip(deps),) if deps.bookable else ()
    linking = (booking_link(deps),) if deps.network == "real" else ()
    # The real network has no profile: anyone at the company calls (the owner, 2026-11-18).
    profile = (traveler_profile(deps.airline),) if deps.network == "mock" else ()
    return (find_flights(deps), choose_flights(deps), *booking, *linking, *profile)


def declare(deps: LeanDeps, names: Names | None = None) -> VoiceAgent:
    """The lean talker over `deps`, named by `names` (the owner's picks unless given): the
    module's docstring."""
    named = Names() if names is None else names
    today = deps.today()
    pronounce = persona.pronounce(named) | {k: dict(v) for k, v in deps.pronounce.items()}
    terms = persona.TERMS if deps.terms is None else deps.terms
    return VoiceAgent(
        name=NAME,
        version=VERSION,
        languages=languages(named, deps.network),
        pronounce=pronounce,
        instructions=prompt.instructions(
            named, today, deps.data.last_day(today), network=deps.network
        ),
        tools=lean_tools(deps),
        vocabulary=Vocabulary(terms=(*terms, named.airline_name_en)),
        ask_on_uncertain_overlaps=True,
        time_zone=TIME_ZONE,
    )

"""The lean agent's instructions, filled with the persona's names and the calendar the model
reads every date from: on the mock, lean/instructions/<tag>.md (about 30 lines each) with the
mock's lines (network_text.py), as run F has read them; on the real network, of every airline,
which books nothing, lean/instructions/real_<tag>.md, short guidance on manner and goals and the
tools' facts, never a reply's template (plan 011's round 2: the owner's "too structured and
following a script"), with no blocks.

**The calendar** (`calendar`), written in code in the reply's language: today with its weekday,
then the next `AHEAD` days, each with its weekday (tomorrow named), then the days "this week",
"this weekend", "next week" and "next weekend" cover, the Saudi week running Sunday to Saturday
and the weekend Friday and Saturday, none of them before today; and the last day the source
sells (`last_day`: the mock's booking window, or how far ahead the airlines show), so a day
past the listed ones is searched, never taken for one that cannot be booked (f-dev-lean-3
refused a day past them as not among its days). Each date is written whole and as `YYYY-MM-DD`,
the form the tools take.

The instructions are built once, when the agent is declared, from the airline's today: a server
serves the calendar of the day it started, its airline kept on that day (restarted each day, its
`FLIGHT_VOICE_TODAY` pinned only to today; lean/agent.py's `calendar_watch`), and run F declares
the agent for each play, on the scenario's today.
"""

from __future__ import annotations

from datetime import date, timedelta
from importlib.resources import files
from string import Template
from typing import Final

from flight_voice.airline.airports import Register
from flight_voice.airline.dates import week_index
from flight_voice.airline.profile import TRAVELER, Traveler
from flight_voice.lean.network_text import blocks
from flight_voice.lean.results import Network
from flight_voice.persona import TAGS, Names, filled
from flight_voice.said import Tag, words

AHEAD: Final = 21
_FRIDAY: Final = 5  # in the Saudi week, Sunday 0
_SATURDAY: Final = 6
_TEXTS: Final[dict[str, dict[str, str]]] = {
    "en": {
        "today": "Today is {day}.",
        "ahead": f"The next {AHEAD} days:",
        "tomorrow": ", tomorrow",
        "week": "The Saudi week runs Sunday to Saturday, and the weekend is Friday and Saturday:",
        "this_week": "This week: {first} to {last}.",
        "this_weekend": "This weekend: {days}.",
        "next_week": "Next week: {first} to {last}.",
        "next_weekend": "Next weekend: {days}.",
        "open": "Bookings are open up to {last}: any day up to it can be searched, listed above "
        "or not.",
        "open_real": "Flights can be searched up to {last}: any day up to it can be searched, "
        "listed above or not.",
        "and": " and ",
    },
    "ar": {
        "today": "اليوم {day}.",
        "ahead": f"الأيام الـ{AHEAD} القادمة:",
        "tomorrow": "، غدًا",
        "week": "الأسبوع في السعودية من الأحد إلى السبت، والعطلة الجمعة والسبت:",
        "this_week": "هذا الأسبوع: من {first} إلى {last}.",
        "this_weekend": "عطلة هذا الأسبوع: {days}.",
        "next_week": "الأسبوع القادم: من {first} إلى {last}.",
        "next_weekend": "عطلة الأسبوع القادم: {days}.",
        "open": "الحجز مفتوح حتى {last}: يمكن البحث في أي يوم حتى ذلك اليوم، مذكورًا أعلاه أو لا.",
        "open_real": "يمكن البحث عن الرحلات حتى {last}: أي يوم حتى ذلك اليوم، مذكورًا أعلاه أو لا.",
        "and": " و",
    },
}


def written(day: date, tag: Tag) -> str:
    """A day written whole in the reply's language, then as the tools take it: "Thursday 19
    November 2026 (2026-11-19)", «الخميس 19 نوفمبر 2026 (2026-11-19)»."""
    register: Register = "en" if tag == "en" else "msa"
    named = f"{words.weekday(day, register)} {day.day} {words.month(day.month, register)}"
    return f"{named} {day.year} ({day.isoformat()})"


def _days(first: date, last: date, today: date, tag: Tag) -> str:
    """The days from `first` to `last` that are not before today, joined."""
    kept = [first + timedelta(days=n) for n in range((last - first).days + 1)]
    texts = _TEXTS["en" if tag == "en" else "ar"]
    return texts["and"].join(written(d, tag) for d in kept if d >= today)


def calendar(today: date, tag: Tag, last: date, network: Network = "mock") -> str:
    """The calendar the model reads every date from (the module's docstring)."""
    texts = _TEXTS["en" if tag == "en" else "ar"]
    lines = [texts["today"].format(day=written(today, tag)), texts["ahead"]]
    for n in range(1, AHEAD + 1):
        day = today + timedelta(days=n)
        lines.append(f"- {written(day, tag)}{texts['tomorrow'] if n == 1 else ''}")
    sunday = today - timedelta(days=week_index(today))
    lines.append(texts["week"])
    for which, start in (("this", sunday), ("next", sunday + timedelta(days=7))):
        saturday = start + timedelta(days=_SATURDAY)
        first = max(start, today)
        week = texts[f"{which}_week"].format(first=written(first, tag), last=written(saturday, tag))
        friday = start + timedelta(days=_FRIDAY)
        weekend = texts[f"{which}_weekend"].format(days=_days(friday, saturday, today, tag))
        lines += [f"- {week}", f"- {weekend}"]
    opened = texts["open" if network == "mock" else "open_real"]
    lines.append(f"- {opened.format(last=written(last, tag))}")
    return "\n".join(lines)


def instructions(
    names: Names,
    today: date,
    last: date,
    *,
    network: Network = "mock",
    traveler: Traveler = TRAVELER,
) -> dict[Tag, str]:
    """The lean agent's instructions for each language, filled with the names, on the mock the
    traveler and the mock's lines, and the calendar of `today` to `last` in that language (the
    module's docstring)."""
    folder = files("flight_voice") / "lean" / "instructions"
    found: dict[Tag, str] = {}
    for tag in TAGS:
        values = filled(names, traveler)
        if network == "mock":
            text = (folder / f"{tag}.md").read_text(encoding="utf-8")
            values |= blocks(tag, values)
        else:
            text = (folder / f"real_{tag}.md").read_text(encoding="utf-8")
        values["calendar"] = calendar(today, tag, last, network)
        found[tag] = Template(text).substitute(values)
    return found

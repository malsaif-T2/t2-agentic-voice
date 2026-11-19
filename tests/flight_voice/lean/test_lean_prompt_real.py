"""The real network's lean instructions (lean/instructions/real_<tag>.md, plan 011's round 2; the
owner: "The agent feels too structured and following a script ... it should be more natural"):
files of their own, well under round 1's render, guidance on manner and goals with no reply
template and no list of particular words; the tools' facts held (the calendar and its weekday
arguments, one way and round trip, a way back added to a chosen one-way trip, a span's cheapest
and flights_per_day, the airline filter, picks from the options, the link ready by itself once a
flight is chosen, failures never no flights, never a fact no tool gave); the Saudi file's Najdi
held for the call with the tools' spelling of names; no demo string; the declared agent's prompt
from them; and the mock's render unchanged byte for byte, so run F reads what it always read."""

from __future__ import annotations

import hashlib
import re
from dataclasses import replace
from importlib.resources import files

import pytest
from flight_voice.airline.schedule import window
from flight_voice.lean.agent import declare
from flight_voice.lean.prompt import calendar, instructions
from flight_voice.persona import TAGS, Names, Tag
from t2_agentic_voice import render_prompt

from tests.flight_voice.lean.lean_support import lean_deps
from tests.flight_voice.scenario_dates import TODAY
from tests.flight_voice.test_own_words import held

LAST = window(TODAY)[1]
FAR = TODAY.replace(year=TODAY.year + 1)
LEAN_DIR = files("flight_voice") / "lean" / "instructions"
# Round 1's real render, the calendar left out, was 5370 characters in English and 6871 in the
# Saudi file: the new ones stay under 70% of that.
LONGEST: dict[Tag, int] = {"en": 3760, "ar-SA": 4810}
# The tools' facts the model needs, each by a phrase both files hold.
FACTS = (
    "pass it too (depart_weekday, return_weekday)",
    "Never use a day the caller did not say.",
    "a trip said to be one way has none",
    "To add a way back to a chosen one-way trip, search the way back: it is read as the trip's "
    "return.",
    "one search gives each day's cheapest price",
    "For the priciest, a time of day, an airline or nonstop flights over those days, search the "
    "span with flights_per_day.",
    "call find_flights again with airline, never answer from the options",
    "Work the caller's pick out yourself from the options (the priciest, the earliest, an "
    "airline's, a time)",
    "choose_flights then lists the way back",
    "the link to book it is ready for the caller by itself",
    "say the link to book it is ready",
    "Sum the whole trip up only when it helps: once it is complete, briefly",
    "Say a connection briefly",
    "Say only what a tool gave in this call",
    "never divide or multiply one",
    "never that there are no flights",
    "When find_flights answers date_problem, say why from its note",
    "call switch_language if you have it",
    # Voice first: the caller hears, and books from the link alone.
    "never speak of a screen, a button, a tap or a click, never read a link or an address aloud",
    "never say a trip is booked",
)
# How each reply sounds: the manner, never a reply's shape.
MANNER = (
    "Vary your wording; do not open every reply the same way or end each with the same question.",
    "Answer what the caller asked with what matters for it, not the trip's every detail.",
    "at most one question",
    "Say what `fares_are` says once, when prices first come up, not with every price.",
)
# Round 1's templates and word lists, which the owner heard as a script: none is left.
TEMPLATES = (
    "say how many flights there are, the first and last departure times",
    "say it in one sentence: the route",
    "Want the link to book it?",
    "booking_link",
    "For example:",
    "«تبي رابط الحجز؟»",
    "«أبشر»",
    "«وش»",
    "«الحين»",
)


def _real(tag: Tag) -> str:
    return instructions(Names(), TODAY, FAR, network="real")[tag]


@pytest.mark.parametrize("tag", TAGS)
def test_the_real_instructions_are_their_own_short_files(tag: Tag) -> None:
    text = _real(tag)
    assert "$" not in text and calendar(TODAY, tag, FAR, "real") in text
    body = text.replace(calendar(TODAY, tag, FAR, "real"), "")
    assert len(body) <= LONGEST[tag], len(body)
    assert len((LEAN_DIR / f"real_{tag}.md").read_text(encoding="utf-8").splitlines()) <= 30
    for mock in ("Every flight starts or ends in Riyadh.", "Khalid", "خالد", "book_trip"):
        assert mock not in text, mock


@pytest.mark.parametrize("tag", TAGS)
def test_the_real_instructions_hold_the_tools_facts_and_the_manner(tag: Tag) -> None:
    text = _real(tag)
    assert [fact for fact in (*FACTS, *MANNER) if fact not in text] == []


@pytest.mark.parametrize("tag", TAGS)
def test_the_real_instructions_hold_no_template_and_no_word_list(tag: Tag) -> None:
    text = _real(tag)
    assert [phrase for phrase in TEMPLATES if phrase in text] == []
    # The company's Arabic name and one quoted form at most: guidance, never a list of cases.
    quoted = re.findall(r'[«"]([^»"]+)[»"]', text)
    assert len([q for q in quoted if q != "تي تو"]) <= 1, quoted


def test_the_saudi_file_holds_najdi_for_the_call_and_the_tools_spelling() -> None:
    text = _real("ar-SA")
    for line in (
        "Speak the register the last section of these instructions names, the same in every "
        "reply of the call.",
        "talk as a friendly, quick travel agent from Riyadh does on the phone: Najdi, in the "
        "everyday words and natural phrasing a Najdi speaker uses",
        "never English carried word for word into Arabic or spelled in Arabic letters",
        "Write every city, airline and place name exactly as the tool results write it, letter "
        "for letter",
        "say a result's `route_msa`, `trip_msa` and `fares_are_msa` in place of the field",
        "In Arabic, name yourself سعد and the company تي تو.",
    ):
        assert line in text, line
    assert "plain, warm English" in _real("en")


def test_the_real_instructions_hold_none_of_the_demos_strings() -> None:
    assert held([_real(tag) for tag in TAGS]) == []


def test_the_real_agents_prompt_is_read_from_the_real_files() -> None:
    agent = declare(replace(lean_deps(), bookable=False, network="real"))
    for tag in TAGS:
        prompt = render_prompt(agent, tag)
        assert "the link to book it is ready for the caller by itself" in prompt
        assert "$" not in prompt and "Then ask whether to book it." not in prompt


# The mock's render of 2026-11-19, before round 2: run F's instructions, kept byte for byte. A
# deliberate change of the mock's files or network_text.py updates these, with a run F note.
MOCK_SHA256: dict[Tag, str] = {
    "ar-SA": "f22649ed6922797acae225c60517f6073f9fd1ca9f411f6fbcab302eebc48163",
    "en": "b6c1e2abe5134b6d38b5e86372dd95aa799308186f238cd2a35a641d384cc987",
}


@pytest.mark.parametrize("tag", TAGS)
def test_the_mock_render_is_unchanged(tag: Tag) -> None:
    text = instructions(Names(), TODAY, LAST)[tag]
    assert hashlib.sha256(text.encode("utf-8")).hexdigest() == MOCK_SHA256[tag]

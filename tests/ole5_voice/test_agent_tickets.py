"""Ole5's talker and its tickets (ole5_voice/agent.py; plan 007): the served talker acting on one
ticket system through all four of its tools, and it alone asking a chat model of an answer
the yes rule's lists leave unplaced (D-082); its instructions telling it to ask only what is
wrong and how urgent, to make a handoff ticket when the caller asks for a person, and to say no
ticket and no number but from a tool's result or the system's words, all in one spoken reply;
the line saying it cannot open a ticket gone; and the talker given no ticket system told it has
none, versioned apart.

The adversarial cases of invariant 2 (docs/SECURITY.md) on the instructions: they hold no
ID-shaped number and no claim phrase of any action, nor of Ole5's for a ticket's number, nor do
the tools' descriptions, so the talker is taught no number and no claim to copy. The talker
with tickets runs under settings whose guard reads a number said as the caller's ticket number
(«رقم تذكرتك», "your ticket number is") as a claim of any action (the owner's ruling of
2026-11-10; `with_ticket_claims`)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from ole5_voice.agent import (
    ECHO_AGENT,
    NO_TICKETS,
    NO_TICKETS_VERSION,
    VERSION,
    Tag,
    instructions,
    talker_agent,
    without_tickets,
)
from ole5_voice.tickets.lines import NUMBER_CLAIMS
from ole5_voice.tickets.mock import MockTicketSystem
from ole5_voice.tickets.tools import ticket_tools, with_ticket_claims
from t2_agentic_voice import Action, GuardSettings, Tool, VoiceSettings, render_prompt
from t2_agentic_voice.evals import FakeKnowledgeBase
from t2_agentic_voice.languages import normalize_arabic, normalize_digits, provider_text

TICKET_TOOLS = ["create_ticket", "add_ticket_note", "hand_off", "ticket_status"]


def _form(text: str) -> str:
    return f" {normalize_arabic(provider_text(text))} "


def test_the_served_talker_acts_on_one_ticket_system(tmp_path: Path) -> None:
    system = MockTicketSystem(tmp_path)
    talker = talker_agent(FakeKnowledgeBase(), tickets=system)
    names = [tool.name for tool in talker.tools]
    assert names == ["search_knowledge", *TICKET_TOOLS]
    assert talker.version == VERSION
    [status] = [tool for tool in talker.tools if isinstance(tool, Tool) and tool.reports_on]
    assert status.name == "ticket_status"
    assert set(status.reports_on) == {"create_ticket", "hand_off"}
    actions = [tool for tool in talker.tools if isinstance(tool, Action)]
    assert [each.name for each in actions] == TICKET_TOOLS[:3]
    assert all(each.description.isascii() for each in talker.tools)  # the design's 6.4
    assert not tmp_path.joinpath("tickets.json").exists()  # built with no IO


def test_only_the_talker_with_tickets_asks_a_model_of_an_unlisted_answer(tmp_path: Path) -> None:
    """D-082: the served talker has a chat model judge an answer to a read-back that the yes
    rule's lists leave unplaced; the talker with no ticket system (runs K, S and T) and with no
    search (run T's pass Tn) has no action, so no read-back, and does not ask, its declaration
    as it was; nor does the echo."""
    served = talker_agent(FakeKnowledgeBase(), tickets=MockTicketSystem(tmp_path))
    assert served.ask_on_unlisted_answers and served.ask_on_uncertain_overlaps
    for unasking in (talker_agent(FakeKnowledgeBase()), talker_agent(None), ECHO_AGENT):
        assert not unasking.ask_on_unlisted_answers
        assert not [tool for tool in unasking.tools if isinstance(tool, Action)]


def test_the_talker_with_no_search_is_given_no_ticket_system(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="no tool"):
        talker_agent(None, tickets=MockTicketSystem(tmp_path))


@pytest.mark.parametrize("tag", ["ar-SA", "en"])
def test_the_tickets_section_says_what_plan_007_asks(tag: Tag) -> None:
    """Q5: only what is wrong and how urgent, in one question at most; the summary and the
    type the model's, the priority Medium unless the caller says how urgent. D-009 and
    D-018: a person asked for is a handoff ticket, no transfer and no call back promised.
    Invariant 2: no ticket and no number but from a tool's result or the system's words;
    nothing said after an action's call. Q4 and Q6: the caller's own tickets, by their last
    four digits, a number they say said back first, the digits said before what happened to the
    ticket (TD-144's ruling). D-075: all in one reply, no screen."""
    text = " ".join(instructions()[tag].split())
    for needed in (
        "learn only what is wrong and how urgent it is, asking in one short question for "
        "whichever the caller has not said",
        "never ask for anything else",
        "Write the summary yourself",
        "pick the type",
        "When the caller asks for a person, a staff member or a human",
        "call hand_off",
        "There is no live transfer",
        "Never say that a person is joining the call or will call the caller back.",
        "say nothing more in that reply",
        "never say a ticket number, unless a tool's result or the system's words in this call",
        "A number from the knowledge base is never a ticket number.",
        "do not try to make it again in this call",
        "It sees only the tickets made for this caller through this voice line",
        "Say only the last four digits of a ticket's number.",
        "first say its last four digits back, then that ticket's status, in the same reply",
        # A status backs a claim only when it names a ticket's digits, or its reply already did
        # (the owner's ruling of 2026-11-10 on TD-144, "Number or same reply"); an Arabic comma
        # ends a clause, so the digits come before what happened.
        "When you tell a ticket's status, say its last four digits first, before what happened "
        "to it.",
        "say all of them in one reply",
        "Never say that anything is on a screen or shown to the caller.",
        "you never ask for a password, a code, an email address or an employee number",
    ):
        assert needed in text, needed
    # The line that said it cannot open a ticket is gone (plan 007, "The Ole5 app").
    for removed in ("You cannot open, change or follow up a ticket", "cannot transfer the call"):
        assert removed not in text
    assert "show_draft" not in text and " card" not in text


def test_the_saudi_instructions_give_a_request_for_a_person_in_saudi_words() -> None:
    text = instructions()["ar-SA"]
    assert "«أبي أكلم أحد من الدعم»" in text and "«موظف»" in text


@pytest.mark.parametrize("tag", ["ar-SA", "en"])
def test_the_instructions_hold_no_number_and_no_claim_phrase(tag: Tag, tmp_path: Path) -> None:
    """Invariant 2: a number the talker could copy as a ticket's (an ID-shaped run of three
    digits or more, in any digits), or a phrase the guard reads as a claim, is in neither the
    instructions, served or with no tickets, nor any tool's description."""
    tools = ticket_tools(MockTicketSystem(tmp_path))
    phrases = [
        phrase
        for tool in tools
        if isinstance(tool, Action)
        for phrase in (*tool.claims.for_language("en"), *tool.claims.for_language(tag))
    ]
    phrases += [phrase for listed in NUMBER_CLAIMS.values() for phrase in listed]
    assert len(phrases) > 40
    texts = [
        instructions()[tag],
        instructions(tickets=False)[tag],
        *(tool.description for tool in tools),
    ]
    for text in texts:
        assert re.search("[0-9]{3,}", normalize_digits(text)) is None
        form = _form(text)
        assert [phrase for phrase in phrases if _form(phrase) in form] == []


def test_the_talker_with_tickets_reads_a_number_said_as_the_callers_as_a_claim() -> None:
    """Ole5's phrases for a ticket's number are added to the guard's phrases that claim any
    action, after those the settings hold (`T2V_GUARD__CLAIMS`), each once; every other setting
    stays as it was, the prefix too."""
    alone = with_ticket_claims(VoiceSettings(env="test"))
    assert dict(alone.guard.claims) == {"ar": ("رقم تذكرتك",), "en": ("your ticket number is",)}
    # khallaSt lak: I finished it for you; a team's own phrases, set in the environment.
    own = GuardSettings.model_validate({"claims": {"ar": ["خلصت لك"], "en": ["all sorted"]}})
    held = VoiceSettings(env="test", guard=own)
    added = with_ticket_claims(held)
    assert dict(added.guard.claims) == {
        "ar": ("خلصت لك", "رقم تذكرتك"),
        "en": ("all sorted", "your ticket number is"),
    }
    assert with_ticket_claims(added).guard.claims == added.guard.claims
    assert added.model_dump(exclude={"guard"}) == held.model_dump(exclude={"guard"})
    assert added.guard.model_dump(exclude={"claims"}) == held.guard.model_dump(exclude={"claims"})
    assert added.prefix == held.prefix


@pytest.mark.parametrize("tag", ["ar-SA", "en"])
def test_the_talker_with_no_ticket_system_is_told_it_has_none(tag: Tag) -> None:
    """Runs K, S and T give the talker no ticket system: in place of the tickets' section it is
    told it can neither open a ticket nor pass the call on, so it names no tool none offers,
    and it is versioned apart."""
    talker = talker_agent(FakeKnowledgeBase())
    assert talker.version == NO_TICKETS_VERSION
    assert [tool.name for tool in talker.tools] == ["search_knowledge"]
    prompt = render_prompt(talker, tag)
    assert NO_TICKETS in prompt and "Tickets and support staff:" not in prompt
    for name in TICKET_TOOLS:
        assert name not in prompt
    assert instructions(tickets=False)[tag] == without_tickets(instructions()[tag])
    with pytest.raises(ValueError, match="0 sections"):
        without_tickets(NO_TICKETS)

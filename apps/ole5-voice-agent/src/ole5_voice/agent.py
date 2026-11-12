"""Ole5's agents (the design's 4.3; plan 006, "The Ole5 app"): the declaration the app hands
the library's runtime.

- **The talker** (`talker_agent`): Saudi Arabic first, then English; Ole5's instructions for
  each (instructions/, one file a language), written for the ear: short spoken answers in the
  Saudi register, in Modern Standard Arabic for a caller who speaks it and in English for
  English; every step of a procedure said in one reply, repeated whole or in part when asked,
  and no screen named (D-075); numbers as digits; a plain "I cannot" for what no tool
  provides; a search whenever the question is about Ole5; and its tickets (plan 007): only
  what is wrong asked for one, its priority set by the talker from the caller's words and
  never asked or said (the owner's ruling of 2026-11-11), a person asked for made a handoff
  ticket, no ticket and no number said but from a tool's result or the system's own words, a
  status of the caller's own tickets alone. Its tools search Ole5's knowledge base
  (`search_tool`, the library's `knowledge_tool`), reading the top `SEARCH_LIMIT` passages
  whole, with a progress line in each language (`PROGRESS`) for a search that runs long, and
  act on a ticket system (tickets/tools.py's `ticket_tools`: `create_ticket`,
  `add_ticket_note`, `hand_off` and `ticket_status`); its
  vocabulary holds Ole5's product terms for the Whisper prompt every call sends (run W kept
  its arm W1, Q23); its `version` is stamped on its traces; a chat model decides a short
  overlap of two or more words the rule would let go on (`ask_on_uncertain_overlaps`, D-069;
  the owner's ruling on run U, Q28); and, with its tickets, a chat model judges an answer to a
  ticket's read-back that the yes rule's lists leave unplaced, within the rule's rails
  (`ask_on_unlisted_answers`, D-082; the owner's rulings of 2026-11-10). With no ticket system
  (runs K, S and T, which give none), the same talker told in place of the tickets' section
  that it can neither open a ticket nor pass the call on (`NO_TICKETS`), since a model told of
  a tool none offers writes a call to one (the live probe of 2026-11-07: Groq refused it,
  `tool_use_failed`); having no action, it reads nothing back, and it does not ask, so its
  declaration and those runs are as they were; with no
  knowledge base either (run T's pass Tn), with no tool at all, told in place of the search
  section that it has none (`NO_SEARCH`), for the same reason. Each is versioned apart.
- **The echo** (`ECHO_AGENT`): the same languages and name with no instructions, which says
  back what it heard, as the app ran before it had a knowledge base; the app runs it when the
  knowledge base's access is not set (server.py).

No fixed line a call of the talker speaks as written (a greeting, a progress line) holds a word
of the presets' stop, wait, repeat or listening lists, nor a yes or send word, so its echo
cannot be heard as the caller's (plan 006, "What voice-first means here", item 6); a test reads
them; the echo's Saudi greeting holds a'eed (I say back), a word of the repeat list, as it did
before. Ole5's name is said "oo lee faayf" in Arabic and "Oh-lee five" in English (the
prototype's D26 and D37, Ole5-chatbot/VOICE_LOG.md, lines 35 and 45). The Arabic texts are
written with `\\u` escapes, as the library's are, each with its sound and meaning in a comment.
"""

from __future__ import annotations

from collections.abc import Sequence
from importlib.resources import files
from typing import Final, Literal

from t2_agentic_voice import DeclaredTool, Language, Tool, Vocabulary, VoiceAgent, knowledge_tool
from t2_agentic_voice.ports import KnowledgeBase

from ole5_voice.tickets.system import TicketSystem
from ole5_voice.tickets.tools import ticket_tools

NAME: Final = "ole5"
# Stamped on every trace of the talker, with the agent's fingerprint: the date it was last
# changed, and the change of that day; the talker with no search, or no tickets, is versioned
# apart (`version`), so a run's record tells each apart: no tickets, as runs K, S and T build
# it with a search; and no tool at all, as run T's pass Tn builds it.
VERSION: Final = "2026-11-12.1"
NO_TICKETS_VERSION: Final = f"{VERSION}+no-tickets"
NO_SEARCH_VERSION: Final = f"{VERSION}+no-search+no-tickets"
# oo lee faayf, as two plain words: the owner's pick of ten samples of the voice, 2026-11-09.
_NAME_SAID: Final = {
    "ar": "\u0623\u0648 \u0644\u064a \u0641\u0627\u064a\u0641",
    "en": "Oh-lee five",
}
# The map finds a form as written, and the knowledge base writes OLE5, which the model copies.
PRONOUNCE: Final = dict.fromkeys(("Ole5", "OLE5", "ole5"), _NAME_SAID)

# The key the search tool names its progress line by, and the line in each language.
PROGRESS_KEY: Final = "searching"
PROGRESS: Final = {
    # adawwir lak fi ad-daleel: I am looking for you in the guide.
    "ar-SA": (
        "\u0623\u062f\u0648\u0651\u0631 \u0644\u0643 "
        "\u0641\u064a \u0627\u0644\u062f\u0644\u064a\u0644."
    ),
    "en": "Let me check the guide.",
}
# The passages a search reads, the knowledge tool's `limit` (its k), each whole (the tool's
# `passage_chars`): one constant, so the agent every run builds and the server serves read the
# same k: 7, as run K0 (`poe knowledge-depth`, Q20) kept on dev on 2026-11-07.
SEARCH_LIMIT: Final = 7
# What tells the talker when to search, in English (the design's 6.4).
SEARCH_DESCRIPTION: Final = (
    "Search Ole5's knowledge base: its user guide, its permissions and business rules, and its "
    "fixes for common problems. Call it once for any question about using Ole5 (how to do "
    "something, a screen, a button, an error message, a setting, a permission or a rule), with "
    "the caller's question in a few words, in the caller's language. Do not call it for a "
    "greeting, thanks, small talk or a question about who you are."
)
# Ole5's product terms as a transcript should write them: the golden set's (evals/terms.toml)
# first, then the products and sign-in methods the knowledge base names.
VOCABULARY: Final = Vocabulary(
    terms=(
        "Ole5",
        "Outlook",
        "PDF",
        "Word",
        "Excel",
        "PowerPoint",
        "OTP",
        "QR",
        "Chrome",
        "Edge",
        "Active Directory",
        "LDAP",
        "ADFS",
        "MFA",
    )
)
# A language's tag, as the library's declaration takes it (its `LanguageTag`), and the tags the
# instructions are given for, each by its file under instructions/.
Tag = Literal["ar-SA", "ar", "en"]
TAGS: Final[tuple[Tag, ...]] = ("ar-SA", "en")
# The heading of each language's section on when and how to search, and what the talker with no
# search is told in its place, in English as the rest of the instructions.
SEARCH_HEADING: Final = "Searching:"
NO_SEARCH: Final = (
    "No knowledge base in this call:\n"
    "- In this call there is no knowledge base and no tool. Answer from the conversation, in "
    "one to three short sentences.\n"
    "- For a question about Ole5 that would need the guide, say plainly, in one sentence, that "
    "you cannot look that up right now."
)
# The heading of each language's section on tickets and handoffs, and what the talker with no
# ticket system is told in its place.
TICKETS_HEADING: Final = "Tickets and support staff:"
NO_TICKETS: Final = (
    "No tickets in this call:\n"
    "- In this call you cannot open, change or follow up a ticket, and you cannot pass the call "
    "to a person or have someone call the caller back. When the caller asks, say so plainly, in "
    "one sentence, and offer to go on helping with their question. Never say that a ticket "
    "exists or that someone will contact them."
)


def instructions(*, search: bool = True, tickets: bool = True) -> dict[Tag, str]:
    """Ole5's instructions for each language, by tag, read from instructions/<tag>.md; with
    `search` False, each one's search section replaced by `NO_SEARCH`; with `tickets` False,
    its tickets' section by `NO_TICKETS`."""
    folder = files("ole5_voice") / "instructions"
    found = {tag: (folder / f"{tag}.md").read_text(encoding="utf-8") for tag in TAGS}
    if not search:
        found = {tag: without_search(text) for tag, text in found.items()}
    if not tickets:
        found = {tag: without_tickets(text) for tag, text in found.items()}
    return found


def without_search(text: str) -> str:
    """`text` with its one section headed `SEARCH_HEADING` replaced by `NO_SEARCH`
    (`replaced`)."""
    return replaced(text, SEARCH_HEADING, NO_SEARCH)


def without_tickets(text: str) -> str:
    """`text` with its one section headed `TICKETS_HEADING` replaced by `NO_TICKETS`
    (`replaced`)."""
    return replaced(text, TICKETS_HEADING, NO_TICKETS)


def replaced(text: str, heading: str, section: str) -> str:
    """`text` with its one section headed `heading` (the sections are split by a blank line)
    replaced by `section`, every other section as it was. ValueError for a text with no such
    section, or more than one."""
    sections = text.split("\n\n")
    found = [n for n, each in enumerate(sections) if each.startswith(heading)]
    if len(found) != 1:
        raise ValueError(f"the instructions hold {len(found)} sections headed {heading}")
    sections[found[0]] = section
    return "\n\n".join(sections)


def version(*, search: bool = True, tickets: bool = True) -> str:
    """The version stamped on the talker's traces: `VERSION`, marked `+no-search` and
    `+no-tickets` for each part it lacks."""
    return VERSION + ("" if search else "+no-search") + ("" if tickets else "+no-tickets")


def _languages(*, talker: bool) -> list[Language]:
    """Saudi Arabic, then English: the talker's with its greetings and progress lines, the
    echo's with its own greetings."""
    if talker:
        # hala, ma'ak musaa'id Ole5 as-sawti. wesh agdar asa'dak feeh?: hello, this is Ole5's
        # voice assistant. What can I help you with?
        saudi = (
            "\u0647\u0644\u0627\u060c \u0645\u0639\u0643 \u0645\u0633\u0627\u0639\u062f Ole5 "
            "\u0627\u0644\u0635\u0648\u062a\u064a. \u0648\u0634 \u0623\u0642\u062f\u0631 "
            "\u0623\u0633\u0627\u0639\u062f\u0643 \u0641\u064a\u0647\u061f"
        )
        english = "Hi, this is the Ole5 voice assistant. How can I help?"
        progress = {tag: {PROGRESS_KEY: line} for tag, line in PROGRESS.items()}
    else:
        # hala, ma'ak musaa'id Ole5 as-sawti; takallam wa a'eed 'aleek illi asma'ah: hello, this
        # is Ole5's voice assistant; speak, and I say back to you what I hear.
        saudi = (
            "\u0647\u0644\u0627\u060c \u0645\u0639\u0643 \u0645\u0633\u0627\u0639\u062f Ole5 "
            "\u0627\u0644\u0635\u0648\u062a\u064a. \u062a\u0643\u0644\u0651\u0645 "
            "\u0648\u0623\u0639\u064a\u062f \u0639\u0644\u064a\u0643 \u0627\u0644\u0644\u064a "
            "\u0623\u0633\u0645\u0639\u0647."
        )
        english = "Hi, this is the Ole5 voice assistant. Speak, and I will say back what I hear."
        progress = {}
    return [
        Language.saudi_arabic(greeting=saudi, progress=progress.get("ar-SA")),
        Language.english(greeting=english, progress=progress.get("en")),
    ]


ECHO_AGENT: Final = VoiceAgent(name=NAME, languages=_languages(talker=False), pronounce=PRONOUNCE)


def search_tool(kb: KnowledgeBase) -> Tool:
    """The talker's search of `kb`: the library's knowledge tool, told when to search
    (`SEARCH_DESCRIPTION`), reading the top `SEARCH_LIMIT` passages, with Ole5's progress
    line."""
    return knowledge_tool(
        kb, description=SEARCH_DESCRIPTION, progress=PROGRESS_KEY, limit=SEARCH_LIMIT
    )


def declare(
    tools: Sequence[DeclaredTool] = (), *, search: bool = True, tickets: bool = True
) -> VoiceAgent:
    """The talker's declaration (the module's docstring) with `tools`; with `search` False,
    told it has no search (`instructions(search=False)`), with `tickets` False, that it has no
    tickets, each versioned apart (`version`), and asking a chat model of an unlisted answer to
    a read-back only with its tickets."""
    return VoiceAgent(
        name=NAME,
        version=version(search=search, tickets=tickets),
        languages=_languages(talker=True),
        pronounce=PRONOUNCE,
        instructions=instructions(search=search, tickets=tickets),
        tools=tools,
        vocabulary=VOCABULARY,
        ask_on_uncertain_overlaps=True,
        ask_on_unlisted_answers=tickets,
    )


def talker_agent(kb: KnowledgeBase | None, *, tickets: TicketSystem | None = None) -> VoiceAgent:
    """Ole5's talker, searching `kb` and acting on `tickets` (`ticket_tools`), as the server
    serves it, under the settings tickets/tools.py's `with_ticket_claims` gives, whose guard
    reads a number said as the caller's ticket number as a claim; with `tickets` None, told it
    has no tickets (runs K, S and T, which give it none); with `kb` None, the same talker with
    no tool at all (a run that times the replies with no search, as run T's pass Tn does), so
    given no ticket system: ValueError otherwise."""
    if kb is None:
        if tickets is not None:
            raise ValueError("the talker with no search has no tool; give it no ticket system")
        return declare(search=False, tickets=False)
    tools = [search_tool(kb), *(() if tickets is None else ticket_tools(tickets))]
    return declare(tools, tickets=tickets is not None)

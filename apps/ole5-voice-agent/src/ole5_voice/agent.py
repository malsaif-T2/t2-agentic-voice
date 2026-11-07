"""Ole5's agents (the design's 4.3; plan 006, "The Ole5 app"): the declaration the app hands
the library's runtime.

- **The talker** (`talker_agent`): Saudi Arabic first, then English; Ole5's instructions for
  each (instructions/, one file a language), written for the ear: short spoken answers in the
  Saudi register, in Modern Standard Arabic for a caller who speaks it and in English for
  English; the first steps in a few words, and the screen named only when the search's card
  shows them; numbers as digits; a plain "I cannot" for what no tool
  provides; no ticket and no person promised, since the agent can do neither; and a search
  whenever the question is about Ole5. Its one tool searches Ole5's knowledge base
  (`search_tool`, the library's `knowledge_tool`), reading the top `SEARCH_LIMIT` passages
  whole, with a progress line in each language (`PROGRESS`) for a search that runs long; its
  vocabulary holds Ole5's product terms for the Whisper prompt, used only if run W keeps its
  arm W1; its `version` is stamped on its traces. With no knowledge base (run T's pass Tn),
  the same talker with no tool, told in place of the instructions' search section that it has
  no search (`NO_SEARCH`), since a model told to search with no tool offered writes a call to
  one (the live probe of 2026-11-07: Groq refused it, `tool_use_failed`).
- **The echo** (`ECHO_AGENT`): the same languages and name with no instructions, which says
  back what it heard, as the app ran before it had a knowledge base; the app runs it when the
  knowledge base's access is not set (server.py).

No fixed line a call of the talker speaks as written (a greeting, a progress line) holds a word
of the presets' stop, wait, repeat or listening lists, nor a yes or send word, so its echo
cannot be heard as the caller's (plan 006, "What voice-first means here", item 6); a test reads
them; the echo's Saudi greeting holds a'eed (I say back), a word of the repeat list, as it did
before. Ole5's name is said "oo-lee faayf" in Arabic and "Oh-lee five" in English (the
prototype's D26 and D37, Ole5-chatbot/VOICE_LOG.md, lines 35 and 45). The Arabic texts are
written with `\\u` escapes, as the library's are, each with its sound and meaning in a comment.
"""

from __future__ import annotations

from collections.abc import Sequence
from importlib.resources import files
from typing import Final, Literal

from t2_agentic_voice import DeclaredTool, Language, Tool, Vocabulary, VoiceAgent, knowledge_tool
from t2_agentic_voice.ports import KnowledgeBase

NAME: Final = "ole5"
# Stamped on every trace of the talker, with the agent's fingerprint: the date it was last
# changed, and the change of that day; the talker with no search (run T's pass Tn) is versioned
# apart, so a run's record tells the two apart.
VERSION: Final = "2026-11-07.3"
NO_SEARCH_VERSION: Final = f"{VERSION}+no-search"
# oo-lee faayf
PRONOUNCE: Final = {
    "Ole5": {
        "ar": "\u0623\u064f\u0648\u0644\u0650\u064a \u0641\u0627\u064a\u0641",
        "en": "Oh-lee five",
    }
}

# The key the search tool names its progress line by, and the line in each language.
PROGRESS_KEY: Final = "searching"
PROGRESS: Final = {
    # adawwir lak al-jawab fi daleel Ole5: I am looking up the answer for you in Ole5's guide.
    "ar-SA": (
        "\u0623\u062f\u0648\u0651\u0631 \u0644\u0643 \u0627\u0644\u062c\u0648\u0627\u0628 "
        "\u0641\u064a \u062f\u0644\u064a\u0644 Ole5."
    ),
    "en": "I'm checking the Ole5 guide for that.",
}
# The passages a search reads, the knowledge tool's `limit` (its k), each whole (the tool's
# `passage_chars`): one constant, so the agent every run builds and the server serves read the
# same k; 5 until run K0 (`poe knowledge-depth`, Q20) keeps another.
SEARCH_LIMIT: Final = 5
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
# tool is told in its place, in English as the rest of the instructions.
SEARCH_HEADING: Final = "Searching:"
NO_SEARCH: Final = (
    "No knowledge base in this call:\n"
    "- In this call there is no knowledge base and no tool. Answer from the conversation, in "
    "one to three short sentences.\n"
    "- For a question about Ole5 that would need the guide, say plainly, in one sentence, that "
    "you cannot look that up right now."
)


def instructions(*, search: bool = True) -> dict[Tag, str]:
    """Ole5's instructions for each language, by tag, read from instructions/<tag>.md; with
    `search` False, each one's search section replaced by `NO_SEARCH`."""
    folder = files("ole5_voice") / "instructions"
    found = {tag: (folder / f"{tag}.md").read_text(encoding="utf-8") for tag in TAGS}
    return found if search else {tag: without_search(text) for tag, text in found.items()}


def without_search(text: str) -> str:
    """`text` with its one section headed `SEARCH_HEADING` (the sections are split by a blank
    line) replaced by `NO_SEARCH`, every other section as it was. ValueError for a text with no
    such section, or more than one."""
    sections = text.split("\n\n")
    found = [n for n, section in enumerate(sections) if section.startswith(SEARCH_HEADING)]
    if len(found) != 1:
        raise ValueError(f"the instructions hold {len(found)} sections headed {SEARCH_HEADING}")
    sections[found[0]] = NO_SEARCH
    return "\n\n".join(sections)


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


def declare(tools: Sequence[DeclaredTool] = (), *, search: bool = True) -> VoiceAgent:
    """The talker's declaration (the module's docstring) with `tools`; with `search` False,
    told it has no search (`instructions(search=False)`) and versioned apart."""
    return VoiceAgent(
        name=NAME,
        version=VERSION if search else NO_SEARCH_VERSION,
        languages=_languages(talker=True),
        pronounce=PRONOUNCE,
        instructions=instructions(search=search),
        tools=tools,
        vocabulary=VOCABULARY,
    )


def talker_agent(kb: KnowledgeBase | None) -> VoiceAgent:
    """Ole5's talker, searching `kb`; with None, the same talker with no tool, told it has no
    search (a run that times the replies with no search, as run T's pass Tn does)."""
    if kb is None:
        return declare(search=False)
    return declare([search_tool(kb)])

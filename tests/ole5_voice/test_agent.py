"""Ole5's agents (ole5_voice/agent.py): the echo as the app ran before; the talker's
declaration, which loads with instructions for every language it speaks, each holding what the
ear needs; its search, the library's knowledge tool with Ole5's description and progress line;
its vocabulary and version; no fixed line of it holding a word the caller commands with; and
its prompt rendered in each language once the library composes it, naming the screen only when
the search shows a card."""

from __future__ import annotations

import asyncio
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

import pytest
from ole5_voice import agent
from ole5_voice.agent import (
    ECHO_AGENT,
    PROGRESS,
    PROGRESS_KEY,
    SEARCH_DESCRIPTION,
    SEARCH_LIMIT,
    VERSION,
    VOCABULARY,
    Tag,
    declare,
    instructions,
    search_tool,
    talker_agent,
)
from ole5_voice.evals.items import EVALS, TERMS_FILE
from t2_agentic_voice import CallContext, Caller, Tool, VoiceAgent, render_prompt
from t2_agentic_voice.evals import FakeKnowledgeBase
from t2_agentic_voice.languages import normalize_arabic, provider_text
from t2_agentic_voice.ports import KnowledgeBase, Passage


@dataclass(frozen=True)
class _Tool:
    """The smallest shape a declared tool has (the library's `DeclaredTool`)."""

    name: str = "search_knowledge"
    description: str = "Search the made-up base."
    progress: str | None = PROGRESS_KEY


def test_the_echo_speaks_saudi_arabic_first_says_its_name_and_has_no_instructions() -> None:
    assert ECHO_AGENT.name == "ole5"
    assert [language.tag for language in ECHO_AGENT.languages] == ["ar-SA", "en"]
    assert dict(ECHO_AGENT.pronounce["Ole5"]) == {"ar": "أُولِي فايف", "en": "Oh-lee five"}
    assert all("Ole5" in language.greeting for language in ECHO_AGENT.languages)
    assert not ECHO_AGENT.instructed and ECHO_AGENT.tools == ()
    assert all(not language.progress for language in ECHO_AGENT.languages)


def test_the_talkers_declaration_loads_with_instructions_for_every_language() -> None:
    tool = _Tool()
    talker = declare([tool])
    assert talker.instructed and talker.tools == (tool,)
    assert isinstance(talker.instructions, Mapping)
    tags = [language.tag for language in talker.languages]
    assert tags == ["ar-SA", "en"]  # Saudi Arabic first, as the echo
    assert set(talker.instructions) == set(tags)
    assert all(text.strip() for text in talker.instructions.values())
    assert (talker.name, dict(talker.pronounce)) == (ECHO_AGENT.name, dict(ECHO_AGENT.pronounce))
    for language in talker.languages:
        assert dict(language.progress) == {PROGRESS_KEY: PROGRESS[language.tag]}
        assert "Ole5" in language.greeting
    assert talker.version == VERSION
    assert talker.vocabulary == VOCABULARY


def test_the_vocabulary_holds_the_golden_sets_product_terms_first() -> None:
    with (EVALS / TERMS_FILE).open("rb") as file:
        golden = [term for term in tomllib.load(file)["terms"] if term != "English"]
    assert list(VOCABULARY.terms[: len(golden)]) == golden  # English is a language, not Ole5's
    assert len(set(VOCABULARY.terms)) == len(VOCABULARY.terms)


@pytest.mark.parametrize("tag", ["ar-SA", "en"])
def test_each_languages_instructions_hold_what_the_ear_needs(tag: Tag) -> None:
    """The plan's "The Ole5 app": short spoken answers, in the Saudi register or MSA or
    English as the caller speaks; the steps on the screen, when a card shows them (below);
    numbers as digits; a plain "I cannot"; no ticket or person promised; a search when the
    question is about Ole5."""
    text = " ".join(instructions()[tag].split())
    for needed in (
        "Saudi spoken register",
        "Modern Standard Arabic",
        "English",
        "one to three short sentences",
        "the full steps are on the screen",
        "Write numbers as digits.",
        "search Ole5's knowledge base first",
        "answer only from what it returns",
        "you do not have that information",
        "you cannot look it up right now",
        "You cannot open, change or follow up a ticket",
        "you cannot transfer the call to a person",
        "Never say that a ticket was opened",
    ):
        assert needed in text, needed


# The yes and send words, the prototype's (its `voice/rules.py`, YES and SUBMIT, read only:
# D-010), which the library's presets do not list yet (the yes rule's): a fixed line holds
# none, so its echo is never heard as a yes.
YES_AND_SEND = {
    "ar": (
        "نعم",
        "ايه",
        "اي",
        "ايوه",
        "ايوا",
        "اكيد",
        "موافق",
        "ارسل",
        "ارسلها",
        "ارسله",
        "ارسلي",
        "ارسلوها",
        "قدم",
        "قدمها",
        "قدمه",
        "افتحها",
        "افتح التذكره",
        "سجلها",
        "اعتمدها",
    ),
    "en": (
        "naam",
        "aywa",
        "yes",
        "yeah",
        "yep",
        "sure",
        "of course",
        "submit",
        "send",
        "confirm",
        "create",
        "go ahead",
    ),
}


def _held(line: str, code: Literal["ar", "en"], talker: VoiceAgent) -> list[str]:
    """The words of the agent's stop, wait, repeat and listening lists, and the yes and send
    words, that `line` holds as whole words, compared in the interruption rule's form."""
    words = talker.phrases.words(code)
    listed = [*words.stop, *words.wait, *words.repeat, *words.backchannel, *YES_AND_SEND[code]]
    form = f" {normalize_arabic(provider_text(line))} "
    return [word for word in listed if f" {normalize_arabic(provider_text(word))} " in form]


def test_no_fixed_line_of_the_talker_holds_a_word_the_caller_commands_with() -> None:
    """The talker's greetings and progress lines (plan 006, "What voice-first means here",
    item 6): their echo cannot be heard as a stop, a wait, a repeat request, a listening sound,
    a yes or a send."""
    talker = declare([_Tool()])
    lines = [
        (language, text)
        for language in talker.languages
        for text in (language.greeting, *language.progress.values())
    ]
    assert len(lines) == 4
    for language, text in lines:
        assert _held(text, language.primary, talker) == [], text
    # The check finds such words where a line holds them, in any case and with any marks.
    found = _held("One moment, I'll REPEAT it. Okay?", "en", talker)
    assert found == ["one moment", "repeat", "repeat it", "okay"]
    assert _held("لحظة، أرسلها الحين", "ar", talker) == ["لحظه", "ارسلها"]


def test_the_search_is_the_librarys_knowledge_tool_with_ole5s_lines(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    made: list[tuple[KnowledgeBase, dict[str, Any]]] = []
    tool = _Tool()

    def knowledge_tool(kb: KnowledgeBase, **given: Any) -> _Tool:
        made.append((kb, given))
        return tool

    monkeypatch.setattr(agent, "knowledge_tool", knowledge_tool)
    kb = FakeKnowledgeBase()
    built: object = search_tool(kb)  # the fake's, whatever its type
    assert built is tool
    [(searched, given)] = made
    assert searched is kb
    assert given == {
        "description": SEARCH_DESCRIPTION,
        "progress": PROGRESS_KEY,
        "limit": SEARCH_LIMIT,
    }
    talker = talker_agent(kb)
    assert talker.instructed and talker.tools == (tool,)
    bare = talker_agent(None)  # the knowledge tool left out, as run T's pass Tn needs
    assert bare.instructed and bare.tools == ()


def test_the_talkers_search_reads_one_named_k_of_passages() -> None:
    """The k every run's agent and the served agent read: 5 until run K0 keeps another (Q20)."""
    assert SEARCH_LIMIT == 5
    found = [
        Passage(id=f"made-up-{n}", title=f"Made-up {n}", text="Made up.", score=0.5)
        for n in range(1, 9)
    ]
    kb = FakeKnowledgeBase(found)
    [search] = talker_agent(kb).tools
    assert isinstance(search, Tool)
    context = CallContext(caller=Caller(subject="made-up"), call_id="call-1", language="ar-SA")
    result = asyncio.run(search.function(context, query="made up"))
    assert [each.limit for each in kb.searches] == [SEARCH_LIMIT]
    assert isinstance(result.data, dict) and isinstance(result.data["passages"], list)
    assert len(result.data["passages"]) == SEARCH_LIMIT


def test_the_search_description_is_in_english_and_says_when_to_search() -> None:
    assert SEARCH_DESCRIPTION.isascii()
    assert "any question about using Ole5" in SEARCH_DESCRIPTION
    assert "Do not call it for a greeting" in SEARCH_DESCRIPTION


def test_the_search_tool_loads_into_the_declaration() -> None:
    """With the library's knowledge tool built, Ole5's search is a `Tool` the declaration
    takes, with Ole5's progress line."""
    try:
        tool = search_tool(FakeKnowledgeBase())
    except NotImplementedError:
        pytest.skip("the library's knowledge tool is not built yet")
    assert isinstance(tool, Tool)
    assert (tool.description, tool.progress) == (SEARCH_DESCRIPTION, PROGRESS_KEY)
    assert declare([tool]).tools == (tool,)


@pytest.mark.parametrize("tag", ["ar-SA", "en"])
def test_the_prompt_renders_with_ole5s_instructions(tag: Tag) -> None:
    talker = declare()
    try:
        prompt = render_prompt(talker, tag)
    except NotImplementedError:
        pytest.skip("the library does not compose the talker's prompt yet")
    assert " ".join(instructions()[tag].split()) in " ".join(prompt.split())
    with pytest.raises(ValueError):
        render_prompt(talker, "ar")  # a language the talker does not speak


@pytest.mark.parametrize("tag", ["ar-SA", "en"])
def test_the_prompt_names_the_screen_only_when_the_search_shows_a_card(tag: Tag) -> None:
    """The live smoke of 2026-11-07: asked how to recover a password, the talker said the full
    steps were on the screen when its search showed no card. In the prompt of each language, the
    library's rule and Ole5's line say it only on the condition of the search result's
    `shown_on_screen`, which says "nothing" when no card is shown. A test cannot show that a
    real model obeys: the registered runs and the live calls can."""
    prompt = render_prompt(declare(), tag)
    lines = [line for line in prompt.splitlines() if "on the screen" in line]
    assert len(lines) == 2, lines  # the library's rule, then Ole5's
    for line in lines:
        assert "on the screen only when" in line, line
        assert "shown_on_screen holds them; otherwise never mention the screen." in line, line
    no_steps = Passage(id="made-up-1", title="Made-up", text="Made up.", score=0.5)
    [search] = talker_agent(FakeKnowledgeBase([no_steps])).tools
    assert isinstance(search, Tool)
    context = CallContext(caller=Caller(subject="made-up"), call_id="call-1", language=tag)
    result = asyncio.run(search.function(context, query="made up"))
    assert result.card is None
    assert isinstance(result.data, dict) and result.data["shown_on_screen"] == "nothing"

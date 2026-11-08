"""The register of each Arabic variant of the knowledge set (plan 006, item 8, after run K's first
dev round) and the register its reply is held to. The library reads it from the caller's words
(the `languages` facade's `register_of`): every MSA variant reads as MSA, and its prompt asks
Ole5's talker for MSA; a Saudi or mixed variant reads as Saudi when its words hold a dialect form,
its prompt asking for the Saudi register, and as MSA when they hold none. Run K holds each reply
by the owner's Q24 (2026-11-08, "Either register right"; `talker_data.registers_held`): a reply
to an MSA variant must be MSA; to a Saudi or mixed one whose words hold a dialect form, Saudi; to
a Saudi or mixed one whose words hold none, either register is right, but never no Arabic."""

from __future__ import annotations

import asyncio
from collections.abc import Iterable
from datetime import date

import pytest
from ole5_voice.agent import talker_agent
from ole5_voice.evals.items import EVALS
from ole5_voice.evals.knowledge_set import (
    KNOWLEDGE_DIR,
    KnowledgeItem,
    SpokenLanguage,
    load_knowledge_items,
)
from ole5_voice.evals.talker_data import (
    REGISTERS,
    TAGS,
    Clause,
    HeardTurn,
    in_language,
    registers_held,
)
from t2_agentic_voice.agent.prompt import LANGUAGE_SECTIONS, MSA_SECTION, compose_prompt
from t2_agentic_voice.evals import ScriptedLLM, TextCall
from t2_agentic_voice.languages import register_of
from t2_agentic_voice.ports import ChatRequest
from t2_agentic_voice.testing.knowledge_fake import FakeKnowledgeBase

ITEMS = load_knowledge_items(EVALS / KNOWLEDGE_DIR)
DAY = date(2026, 11, 7)
# A reply in Arabic, as the judge's register is asked of it; the script check passes it.
ARABIC = HeardTurn(
    fate="answered",
    clauses=(Clause(text="افتح الرسالة.", language="ar-SA", fate="played", played_fraction=1),),
)


def _variants(
    *languages: SpokenLanguage,
) -> Iterable[tuple[KnowledgeItem, int, SpokenLanguage, str]]:
    for item in ITEMS:
        for position, variant in enumerate(item.variants, start=1):
            if variant.language in languages:
                yield item, position, variant.language, variant.text


def test_every_msa_variant_reads_as_msa_is_asked_for_msa_and_held_to_it() -> None:
    talker = talker_agent(FakeKnowledgeBase())
    read = list(_variants("msa"))
    assert len(read) > 30  # the set's MSA variants, every one
    for item, position, language, text in read:
        register = register_of(text)
        assert register == "msa", (item.id, position)
        prompt = compose_prompt(talker, language="ar-SA", today=DAY, register=register)
        assert prompt.endswith(f"\n\n{MSA_SECTION}"), (item.id, position)
        assert registers_held(TAGS[language], text) == {"msa"}, (item.id, position)


def test_a_saudi_or_mixed_variant_is_held_to_saudi_with_a_dialect_form_and_to_either_without() -> (
    None
):
    """The rule over every Saudi and mixed variant, both kinds of words among them: the
    registers a reply is right in, and run K's language score of an Arabic reply in each."""
    talker = talker_agent(FakeKnowledgeBase())
    read = list(_variants("saudi", "mixed"))
    assert len(read) > 100
    kinds: set[str] = set()
    for item, position, language, text in read:
        where = (item.id, position)
        register = register_of(text)
        kinds.add(register)
        held = registers_held(TAGS[language], text)
        assert held == ({"saudi"} if register == "saudi" else {"saudi", "msa"}), where
        right = {
            each for each in REGISTERS if in_language(ARABIC, TAGS[language], each, words=text)
        }
        assert right == held and "none" not in right, where
        section = LANGUAGE_SECTIONS["ar-SA"] if register == "saudi" else MSA_SECTION
        prompt = compose_prompt(talker, language="ar-SA", today=DAY, register=register)
        assert prompt.endswith(f"\n\n{section}"), where
    assert kinds == {"saudi", "msa"}  # the set holds both kinds of words


@pytest.mark.parametrize(("item", "position"), [("q02_new_internal", 3), ("q02_new_internal", 2)])
def test_ole5s_talker_is_asked_in_the_register_of_the_callers_words(
    item: str, position: int
) -> None:
    """Through the served talker's own path, an `ar-SA` call: its first request's system
    message ends with the section the caller's words call for."""
    [found] = [each for each in ITEMS if each.id == item]
    asked = found.variants[position - 1]
    llm = ScriptedLLM([ScriptedLLM.reply("حسنا.")])

    async def scene() -> None:
        served = talker_agent(FakeKnowledgeBase())
        async with TextCall(served, llm=llm, language="ar-SA") as call:
            await call.user(asked.text)
            await call.advance(5.0)

    asyncio.run(scene())
    request: ChatRequest = llm.requests[0]
    wanted = MSA_SECTION if asked.language == "msa" else LANGUAGE_SECTIONS["ar-SA"]
    assert asked.language in {"msa", "saudi"}
    assert request.messages[0].content.endswith(f"\n\n{wanted}")

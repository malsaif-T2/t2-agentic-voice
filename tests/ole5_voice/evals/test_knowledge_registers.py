"""The register the library reads from each Arabic variant of the knowledge set (agent/language.py's
`register_of`; plan 006, item 8, after run K's first dev round): every MSA variant reads as MSA, and
its prompt asks Ole5's talker for MSA; every Saudi variant, and every Arabic one with English
product terms (`mixed`, which run K holds to the Saudi register too), reads as Saudi, its prompt
asking for the Saudi register, but for the variants named in `NEUTRAL`, whose words hold none of
the rule's dialect forms. The rule reads a turn of Arabic with no dialect form as MSA, so the
talker is asked for MSA there, and a run that holds such a variant to the Saudi register by its
label counts an MSA reply wrong; each is named with why, for the lead to rule on."""

from __future__ import annotations

import asyncio
from collections.abc import Iterable
from datetime import date

import pytest
from ole5_voice.agent import talker_agent
from ole5_voice.evals.items import EVALS
from ole5_voice.evals.knowledge_set import KNOWLEDGE_DIR, KnowledgeItem, load_knowledge_items
from t2_agentic_voice.agent.language import register_of
from t2_agentic_voice.agent.prompt import LANGUAGE_SECTIONS, MSA_SECTION, compose_prompt
from t2_agentic_voice.evals import ScriptedLLM, TextCall
from t2_agentic_voice.ports import ChatRequest
from t2_agentic_voice.testing.knowledge_fake import FakeKnowledgeBase

ITEMS = load_knowledge_items(EVALS / KNOWLEDGE_DIR)
DAY = date(2026, 11, 7)
_NONE = "no dialect form: MSA as written"
# The Saudi and mixed variants the rule reads as MSA, by item and variant (from 1), and why.
NEUTRAL: dict[tuple[str, int], str] = {
    ("n04_screen_freezes", 1): "lamma (when) before a verb, which the list does not hold",
    ("n13_attach_pdf", 2): _NONE,
    ("n17_save_word", 1): _NONE,
    ("n20_error_suddenly", 1): "ma 'aad (no longer): a perfect with no ending, no verb's shape",
    ("n23_signature_msa", 2): _NONE,
    ("q03_register_incoming", 1): "jana (came to us), which the list does not hold",
    ("q07_delivery_statement", 1): _NONE,
    ("q12_storage", 2): "imtalat, MSA's imtala'at (filled) written without its hamza",
    ("q16_two_factor", 3): _NONE,
    ("q19_new_role", 1): _NONE,
    ("q26_support_hours", 1): _NONE,
    ("q27_translate", 2): _NONE,
    ("q29_greeting", 1): _NONE,
    ("q32_weather", 1): _NONE,
    ("q34_open_ticket", 3): _NONE,
    ("q35_employee_left", 1): "aqfil (I close), which MSA says too",
    ("q39_fingerprint_login", 3): _NONE,
    ("q42_password_expiry", 3): _NONE,
}


def _variants(*languages: str) -> Iterable[tuple[KnowledgeItem, int, str]]:
    for item in ITEMS:
        for position, variant in enumerate(item.variants, start=1):
            if variant.language in languages:
                yield item, position, variant.text


def test_every_msa_variant_reads_as_msa_and_is_asked_for_msa() -> None:
    talker = talker_agent(FakeKnowledgeBase())
    read = list(_variants("msa"))
    assert len(read) > 30  # the set's MSA variants, every one
    for item, position, text in read:
        register = register_of(text)
        assert register == "msa", (item.id, position)
        prompt = compose_prompt(talker, language="ar-SA", today=DAY, register=register)
        assert prompt.endswith(f"\n\n{MSA_SECTION}"), (item.id, position)


def test_every_saudi_variant_reads_as_saudi_but_the_neutral_ones() -> None:
    talker = talker_agent(FakeKnowledgeBase())
    read = list(_variants("saudi", "mixed"))
    assert len(read) > 100
    misread = set()
    for item, position, text in read:
        register = register_of(text)
        prompt = compose_prompt(talker, language="ar-SA", today=DAY, register=register)
        if register == "msa":
            misread.add((item.id, position))
            assert prompt.endswith(f"\n\n{MSA_SECTION}")
        else:
            assert prompt.endswith(f"\n\n{LANGUAGE_SECTIONS['ar-SA']}"), (item.id, position)
    assert misread == set(NEUTRAL)  # a change of the rule or of the set shows here


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

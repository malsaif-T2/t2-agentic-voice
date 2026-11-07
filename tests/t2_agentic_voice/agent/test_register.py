"""The register of the caller's Arabic (agent/language.py's `register_of`, agent/prompt.py; plan
006, item 8: an Arabic reply is in the Saudi register unless the caller speaks MSA). Run K's first
dev round had 8 of 10 MSA callers answered in Saudi Arabic while the model alone was told to tell
the two apart; the library now reads it from the caller's words, by a small explicit list of Saudi
and Gulf dialect forms: a turn of Arabic with none is MSA, and an `ar-SA` reply's language section
and its line after a tool result say so. An agent's Arabic tag that is not Saudi (`ar`) keeps its
section. Every sentence is written for the test."""

from __future__ import annotations

from datetime import date

import pytest
from t2_agentic_voice.actions.knowledge import NAME, knowledge_tool
from t2_agentic_voice.agent.language import (
    DIALECT_OPENERS,
    DIALECT_WORDS,
    NOT_NEGATED,
    register_of,
)
from t2_agentic_voice.agent.prompt import (
    LANGUAGE_SECTIONS,
    MSA_REPLY_LINE,
    MSA_SECTION,
    REPLY_LINES,
    compose_prompt,
    language_section,
    reply_line,
)
from t2_agentic_voice.core.conversation import TalkerTurn
from t2_agentic_voice.core.settings.tts import LanguageTag
from t2_agentic_voice.domain.declaration import Language
from t2_agentic_voice.domain.ports.knowledge import Passage
from t2_agentic_voice.domain.words import rule_form
from t2_agentic_voice.testing.knowledge_fake import FakeKnowledgeBase

from tests.t2_agentic_voice.agent.chat_support import (
    ENGLISH,
    MSA,
    SAUDI,
    FakeChat,
    agent,
    call,
    calls,
    reply,
    said,
    talker,
)

DAY = date(2026, 11, 7)
# One sentence for each form the brief named, and each the library adds, holding that form and
# otherwise only words MSA says too.
SAUDI_SENTENCES = [
    "أبشر، سأساعدك في ذلك",
    "تقدر تساعدني في الطباعة؟",
    "كيف أقدر أطبع الملف",
    "أبي أطبع الملف",
    "أبغى أطبع الملف",
    "الملف اللي أرسلته لا يظهر",
    "وش سبب الخطأ",
    "ايش سبب الخطأ",
    "ليش يظهر الخطأ",
    "الحين يظهر الخطأ",
    "لازم أغير كلمة المرور؟",
    "أريد الخطوة الأولى بس",
    "الزر مو موجود",
    "راح أرسل الملف غدا",
    "جرب إعادة التشغيل",
    "هل تشوف الزر",
    "الزر لا يبان",
    "معليش، أعد السؤال",
    "أريد رمزا جديدا عشان الدخول",
    "يظهر كذا في الشاشة",
    "زين، شكرا لك",
    "النظام بطيء مرة",
    "وين أجد الأرشيف",
    "مين أرسل الرسالة",
    "شلون أغير كلمة المرور",
    "كيف أسوي أرشفة للرسائل",
    "ينفع أرسل الرسالة الآن؟",
    "الطابعة خربان",
]
NEGATED = [
    "الزر ما يظهر في الشاشة",  # ma before an imperfect: teh
    "الرسالة ما تصل إلى البريد",
    "ما أعرف كيف أرسلها",  # alef, four letters
    "ما نقدر نفتح النظام",
    "ما وصلتني الرسالة",  # a perfect's ending: teh, noon, yeh
    "ما فتحت الرسالة بعد",  # teh
    "وما يفتح البرنامج",  # wa before ma
]
MSA_SENTENCES = [
    "لم تظهر الرسالة في صندوق الوارد",
    "كيف أضيف توقيعا إلى رسائلي؟",
    "ما سبب ظهور هذا الخطأ؟",  # ma, what, before a noun
    "ما هي خطوات إنشاء حساب جديد؟",
    "ما الذي يجب فعله الآن؟",
    "ما يجب علي فعله؟",  # NOT_NEGATED: MSA's verbs after ma
    "ما أفضل طريقة لحفظ الملف؟",  # and its nouns of a verb's shape
    "ما تاريخ آخر تحديث؟",
    "ما اسم الزر؟",  # alef, three letters
    "ما نوع الملف المطلوب؟",  # noon, three letters
    "ما خطوات الأرشفة؟",  # a plural's ending, not a perfect's
    "أريد معرفة ما إذا كان الحساب مفعلا",
    "هل يوجد فيه زر للطباعة؟",  # fih, not the turn's first word
    "شكرا جزيلا على المساعدة",
]


@pytest.mark.parametrize("words", [*SAUDI_SENTENCES, *NEGATED])
def test_arabic_with_a_dialect_form_is_saudi(words: str) -> None:
    assert register_of(words) == "saudi"


@pytest.mark.parametrize("words", MSA_SENTENCES)
def test_arabic_with_no_dialect_form_is_msa(words: str) -> None:
    assert register_of(words) == "msa"


def test_each_form_counts_alone_and_with_wa_before_it() -> None:
    for form in DIALECT_WORDS:
        assert register_of(f"هل {form} الآن") == "saudi", form
        assert register_of(f"هل و{form} الآن") == "saudi", form
    assert register_of("فيه زر للطباعة؟") == "saudi"  # fih opening the turn: is there


def test_the_forms_are_written_in_the_rules_form() -> None:
    """As the library's other Arabic tables: teh marbuta written heh, alef maksura yeh, every
    alef bare, so a caller's word in any spelling is compared in one."""
    listed = [*DIALECT_WORDS, *DIALECT_OPENERS, *NOT_NEGATED]
    assert all(rule_form(word) == word and " " not in word for word in listed)
    assert register_of("أبْغَى") == register_of("ابغي") == "saudi"  # harakat, alef maksura
    assert register_of("مرّة") == "saudi"  # shadda, teh marbuta


@pytest.mark.parametrize("words", ["OK", "VPN Outlook", "", "123"])
def test_a_turn_with_no_arabic_word_keeps_the_saudi_default(words: str) -> None:
    assert register_of(words) == "saudi"


def test_an_ar_sa_reply_to_an_msa_caller_asks_for_msa_and_any_other_is_as_it_was() -> None:
    assert language_section("ar-SA", "msa") == MSA_SECTION
    assert MSA_SECTION.startswith("Reply in Modern Standard Arabic")
    assert "Saudi" in MSA_SECTION and "dialect" in MSA_SECTION  # none of its words
    assert language_section("ar-SA", "saudi") == LANGUAGE_SECTIONS["ar-SA"]  # as it was
    for register in ("saudi", "msa"):
        assert language_section("ar", register) == LANGUAGE_SECTIONS["ar"]  # not Saudi's
        assert language_section("en", register) == LANGUAGE_SECTIONS["en"]
    assert reply_line("ar-SA", "msa") == MSA_REPLY_LINE
    assert MSA_REPLY_LINE.startswith("Reply in Modern Standard Arabic")
    assert reply_line("ar-SA", "saudi") == REPLY_LINES["ar-SA"]
    assert [reply_line("ar", "msa"), reply_line("en", "msa")] == [
        REPLY_LINES["ar"],
        REPLY_LINES["en"],
    ]


def test_the_prompt_ends_with_the_registers_section() -> None:
    msa = compose_prompt(agent(), language="ar-SA", today=DAY, register="msa")
    assert msa.endswith(f"\n\n{MSA_SECTION}")
    saudi = compose_prompt(agent(), language="ar-SA", today=DAY)  # the default, Saudi's
    assert saudi.endswith(f"\n\n{LANGUAGE_SECTIONS['ar-SA']}")
    assert compose_prompt(agent(), language="ar", today=DAY, register="msa").endswith(
        f"\n\n{LANGUAGE_SECTIONS['ar']}"
    )


PASSAGE = Passage(id="made-up-ar-002", title="الطباعة", text="افتح الرسالة ثم اطبعها.", score=0.7)


def _requests(words: str, call_language: LanguageTag, *languages: Language) -> FakeChat:
    search = knowledge_tool(FakeKnowledgeBase([PASSAGE]), description="Search the help.")
    model = FakeChat(calls(call(NAME, query="print")), said("Sure."))
    declared = agent(search, languages=languages or (SAUDI, MSA, ENGLISH))
    chat = talker(model, search, language=call_language, declared=declared)
    reply(chat, TalkerTurn(turn_id=1, words=words, language="ar"))
    return model


def test_an_msa_turn_of_a_saudi_call_is_asked_for_msa_before_and_after_its_search() -> None:
    model = _requests("كيف أطبع الرسالة من النظام؟", "ar-SA")
    first, second = model.requests
    assert first.messages[0].content.endswith(f"\n\n{MSA_SECTION}")
    assert "in the Saudi dialect" not in first.messages[0].content
    assert second.messages[-1].content == MSA_REPLY_LINE


def test_a_saudi_turn_of_the_same_call_is_asked_for_the_saudi_register() -> None:
    model = _requests("أبي أطبع الرسالة من النظام", "ar-SA")
    first, second = model.requests
    assert first.messages[0].content.endswith(f"\n\n{LANGUAGE_SECTIONS['ar-SA']}")
    assert second.messages[-1].content == REPLY_LINES["ar-SA"]


def test_an_agents_arabic_that_is_not_saudi_keeps_its_section() -> None:
    model = _requests("كيف أطبع الرسالة من النظام؟", "ar", MSA, ENGLISH)
    first, second = model.requests
    assert first.messages[0].content.endswith(f"\n\n{LANGUAGE_SECTIONS['ar']}")
    assert second.messages[-1].content == REPLY_LINES["ar"]

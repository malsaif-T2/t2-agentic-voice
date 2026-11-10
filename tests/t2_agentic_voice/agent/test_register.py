"""The register of the caller's Arabic (agent/language.py's `register_of`, agent/prompt.py; plan
006, item 8: an Arabic reply is in the Saudi register unless the caller speaks MSA). Run K's first
dev round had 8 of 10 MSA callers answered in Saudi Arabic while the model alone was told to tell
the two apart; the library now reads it from the caller's words, by a small explicit list of Saudi
and Gulf dialect forms: a turn of Arabic with none is MSA, and an `ar-SA` reply's language section
and its line after a tool result say so. A reply follows the call's register: Saudi once any heard
turn of the caller's held a form (a review finding), MSA while none has. An agent's Arabic tag
that is not Saudi (`ar`) keeps its section; an `ar-SA` reply to an MSA caller reads an action's
MSA texts (`wording`). Every sentence is written for the test."""

from __future__ import annotations

from datetime import date

import pytest
from t2_agentic_voice.actions.knowledge import NAME, knowledge_tool
from t2_agentic_voice.agent.language import (
    DIALECT_OPENERS,
    DIALECT_WORDS,
    NOT_NEGATED,
    register_of,
    wording,
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
from t2_agentic_voice.core.conversation import Conversation, PastTurn, TalkerTurn, TurnFate
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


# The register over the call (a review finding): a short plain turn after a Saudi one («تمام»،
# «كمل»، «ممكن تعيد؟») flipped the reply to MSA, and a repeat came back reworded in MSA.
def _call(*turns: str, dropped: frozenset[int] = frozenset()) -> list[tuple[str, str]]:
    """Each turn of one ar-SA call answered with a search, in order: the system prompt's last
    line and the line after its result, as the talker sent them; the turns of `dropped` (from
    0) heard as the agent's own voice."""
    search = knowledge_tool(FakeKnowledgeBase([PASSAGE]), description="Search the help.")
    entries = [step for _ in turns for step in (calls(call(NAME, query="print")), said("Sure."))]
    model = FakeChat(*entries)
    chat = talker(model, search, language="ar-SA", declared=agent(search))
    past: list[PastTurn] = []
    for n, words in enumerate(turns):
        heard = Conversation(turns=tuple(past))
        reply(chat, TalkerTurn(turn_id=n + 1, words=words, language="ar", conversation=heard))
        fate: TurnFate = "dropped" if n in dropped else "answered"
        past.append(PastTurn(turn_id=n + 1, words=words, fate=fate))
    systems = [r.messages[0].content.rsplit("\n\n", 1)[1] for r in model.requests[::2]]
    lines = [r.messages[-1].content for r in model.requests[1::2]]
    return list(zip(systems, lines, strict=True))


SAUDI_ASKED = (LANGUAGE_SECTIONS["ar-SA"], REPLY_LINES["ar-SA"])
MSA_ASKED = (MSA_SECTION, MSA_REPLY_LINE)


def test_plain_turns_after_a_saudi_turn_keep_the_saudi_register() -> None:
    assert _call("أبي أطبع الرسالة", "تمام شكرا", "ممكن تعيد؟", "كمل") == [SAUDI_ASKED] * 4


def test_a_call_of_msa_turns_only_keeps_msa() -> None:
    assert _call("كيف أطبع الرسالة؟", "شكرا جزيلا", "هل يمكنني إعادتها؟") == [MSA_ASKED] * 3


def test_a_plain_first_turn_is_msa_then_saudi_from_the_first_dialect_turn_on() -> None:
    found = _call("كيف أطبع الرسالة؟", "ممكن تعيد؟", "وين الزر؟", "تمام", "How long does it take?")
    assert found[:2] == [MSA_ASKED] * 2
    assert found[2:4] == [SAUDI_ASKED] * 2
    assert found[4] == (LANGUAGE_SECTIONS["en"], REPLY_LINES["en"])  # English, the call's Saudi


def test_a_turn_heard_as_the_agents_own_voice_says_nothing_of_the_callers_register() -> None:
    """A dialect word the drop rule judged the agent's echo is not the caller's."""
    assert _call("الحين يظهر الخطأ", "كيف أطبع الرسالة؟", dropped=frozenset({0}))[1] == MSA_ASKED


def test_an_actions_lines_are_read_in_msa_for_an_saudi_reply_to_an_msa_caller() -> None:
    """The register picks an action's texts, never the reply's tag: an `ar-SA` reply to an MSA
    caller reads `ar`, the MSA texts, still spoken in `ar-SA`; any other reads its own tag."""
    assert wording("ar-SA", "msa") == "ar" and wording("ar-SA", "saudi") == "ar-SA"
    assert wording("ar", "saudi") == "ar" and wording("ar", "msa") == "ar"
    assert wording("en", "msa") == "en" and wording("en", "saudi") == "en"

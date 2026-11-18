"""The register of the caller's Arabic read Saudi first (agent/language.py's `call_register` under
`words.saudi_first`), and a team's own Saudi forms (`words.dialect`): with the setting on, a turn
with no Saudi form is MSA only when it plainly speaks MSA (`MSA_WORDS`); a turn with neither
keeps the call Saudi, or MSA once an MSA turn was heard, until a Saudi form is; with it off (the
default), every reading is as it was. With `words.fixed_register` set, every call is held in that
one, whatever the caller says. The talker asks for the register so read. Every sentence is
written for the test."""

from __future__ import annotations

import pytest
from t2_agentic_voice.agent.language import MSA_WORDS, call_register, register_of
from t2_agentic_voice.agent.prompt import HELD_SAUDI_SECTION, LANGUAGE_SECTIONS, MSA_SECTION
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.conversation import Conversation, PastTurn, TalkerTurn
from t2_agentic_voice.core.settings.words import WordSettings

from tests.t2_agentic_voice.agent.chat_support import FakeChat, reply, said, talker

FIRST = WordSettings(saudi_first=True)
# Turns that hold neither a Saudi form of the library's list nor a form only MSA says.
NEUTRAL = ["السلام عليكم", "نعم لو سمحت", "إلى جدة", "شكرا جزيلا", "الرحلة الثانية"]
# Turns that plainly speak MSA, one for each of the forms the brief named.
PLAIN_MSA = [
    "أريد تذكرة إلى الدمام",
    "أودّ السفر يوم الأحد",
    "هل توجد مقاعد؟",
    "ماذا عن الرحلة المسائية؟",
    "لماذا السعر مرتفع؟",
    "أحتاج الحجز الآن",
    "سوف أسافر مع عائلتي",
]
# Turns that plainly speak MSA by a form a caller says beside those: a wish, tomorrow, next,
# "I have", all right, which.
MORE_MSA = [
    "أرغب في السفر إلى جدة",
    "أحتاج رحلة إلى أبها غدًا",
    "أبحث عن رحلة الأسبوع القادم",
    "صباح الخير، لدي سؤال عن الرحلات",
    "حسنًا، الرحلة الصباحية من فضلك",
    "الرحلة التي تصل مساء",
]
TEAM_FORMS = ("كذاك", "يا هلا بك")
WALADI = "ولدي"  # my son: a word of its own, not wa and ladayya (I have)


@pytest.mark.parametrize("words", NEUTRAL)
def test_a_neutral_turn_reads_saudi_first_and_msa_as_before(words: str) -> None:
    assert register_of(words, saudi_first=True) == "saudi"
    assert call_register([words], FIRST) == "saudi"
    assert register_of(words) == call_register([words]) == "msa"  # the setting off: as before
    assert call_register([words], WordSettings()) == "msa"


@pytest.mark.parametrize("words", [*PLAIN_MSA, *MORE_MSA])
def test_a_turn_that_plainly_speaks_msa_reads_msa_either_way(words: str) -> None:
    assert register_of(words, saudi_first=True) == register_of(words) == "msa"
    assert call_register([words], FIRST) == "msa"


def test_each_form_only_msa_says_reads_msa_with_or_without_wa() -> None:
    for form in MSA_WORDS:
        assert register_of(f"نعم {form} ذلك", saudi_first=True) == "msa", form
        joined = "msa" if f"و{form}" != WALADI else "saudi"
        assert register_of(f"نعم و{form} ذلك", saudi_first=True) == joined, form
    assert register_of(f"{WALADI} مسافر معي", saudi_first=True) == "saudi"


def test_a_saudi_form_beside_an_msa_one_reads_saudi() -> None:
    assert register_of("هل فيه رحلة الحين؟", saudi_first=True) == "saudi"  # al-heen


def test_an_msa_turn_holds_the_call_in_msa_until_a_saudi_form_is_heard() -> None:
    assert call_register(["السلام عليكم", "أريد السفر إلى جدة"], FIRST) == "msa"
    assert call_register(["أريد السفر إلى جدة", "نعم", "الرحلة الأولى"], FIRST) == "msa"
    assert call_register(["أريد السفر إلى جدة", "وين أرخص يوم؟", "نعم"], FIRST) == "saudi"
    assert call_register(["أبي أسافر", "هل توجد رحلة؟"], FIRST) == "saudi"  # as before
    assert call_register(["OK", "Yes"], FIRST) == call_register([], FIRST) == "saudi"


def test_a_register_set_holds_every_call_in_it_whatever_is_said() -> None:
    # The owner, 2026-11-18: "make a switch for Nadji and Arabic, don't make them change during
    # the call".
    saudi, msa = (
        WordSettings(fixed_register="saudi"),
        WordSettings(fixed_register="msa", saudi_first=True),
    )
    for turns in (["أريد السفر إلى جدة", "هل توجد رحلة؟"], ["أبي أسافر", "وين أرخص يوم؟"], []):
        assert call_register(turns, saudi) == "saudi", turns
        assert call_register(turns, msa) == "msa", turns
    assert WordSettings().fixed_register is None  # read from the caller's words by default


def test_a_teams_saudi_forms_read_saudi_with_the_setting_off_too() -> None:
    added = WordSettings(dialect=TEAM_FORMS)
    assert call_register(["كذاك أحسن"], added) == "saudi"
    assert call_register(["وكذاك أحسن"], added) == "saudi"  # with wa
    assert call_register(["أهلا يا هلا بك"], added) == "saudi"  # a phrase, its words in a row
    assert call_register(["هلا بك يا صديقي"], added) == "msa"  # its words, not in a row
    assert register_of("كذاك أحسن", dialect=TEAM_FORMS) == "saudi"
    assert call_register(["كذاك أحسن"]) == "msa"  # none added: as before


def _system_prompts(settings: VoiceSettings, *turns: str) -> list[str]:
    """The system prompt's last section of each turn of one ar-SA call, in order."""
    model = FakeChat(*(said("تمام.") for _ in turns))
    chat = talker(model, language="ar-SA", settings=settings)
    past: list[PastTurn] = []
    for n, words in enumerate(turns):
        heard = Conversation(turns=tuple(past))
        reply(chat, TalkerTurn(turn_id=n + 1, words=words, language="ar", conversation=heard))
        past.append(PastTurn(turn_id=n + 1, words=words, fate="answered"))
    return [request.messages[0].content.rsplit("\n\n", 1)[1] for request in model.requests]


def test_the_talker_asks_for_the_register_read_saudi_first() -> None:
    first = VoiceSettings(env="test", words=FIRST)
    turns = ("السلام عليكم", "أريد السفر إلى جدة", "نعم")
    saudi, msa = LANGUAGE_SECTIONS["ar-SA"], MSA_SECTION
    assert _system_prompts(first, *turns) == [saudi, msa, msa]
    assert _system_prompts(VoiceSettings(env="test"), *turns) == [msa, msa, msa]  # as before


def test_the_talker_asks_for_the_register_held_in_every_reply() -> None:
    """A register held for the call (D-125): the same section on every turn, whatever is said;
    the Saudi one never invites MSA."""
    turns = ("السلام عليكم", "أريد السفر إلى جدة", "هل توجد رحلة؟")
    saudi, msa = WordSettings(fixed_register="saudi"), WordSettings(fixed_register="msa")
    for words, section in ((saudi, HELD_SAUDI_SECTION), (msa, MSA_SECTION)):
        settings = VoiceSettings(env="test", words=words)
        assert _system_prompts(settings, *turns) == [section] * len(turns), section
    assert "unless" not in HELD_SAUDI_SECTION

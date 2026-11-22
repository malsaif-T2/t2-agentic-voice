"""The language each clause of a reply is said in (agent/clause_voice.py, agent/clause_gate.py;
`tts.voice_by_script`). The owner's calls of 2026-11-22: in an Arabic call held in its language,
English small talk was answered in Arabic under the English tag, and the English voice read it.
With the setting on, a clause of an English reply with more words in Arabic letters than in
Latin ones carries the agent's Arabic tag and the call's register, one with no letter keeps the
tag before it, English clauses stay English, and an Arabic reply never moves, whatever Latin name
it holds; a blocked clause carries its own tag too, and a `switch_language` move starts the voice
again from the moved tag. Off, every clause carries the reply's tag, as before. Every line is
written for the test."""

from __future__ import annotations

import pytest
from t2_agentic_voice.actions.language_tool import NAME, language_tool
from t2_agentic_voice.agent.clause_voice import arabic_tag
from t2_agentic_voice.agent.talker import ClauseBlocked, SpokenClause, TalkerEvent
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.conversation import Conversation, PastTurn, TalkerTurn
from t2_agentic_voice.core.settings.tts import LanguageTag, TtsSettings
from t2_agentic_voice.domain.text.arabic_numbers import Register

from tests.t2_agentic_voice.agent.chat_support import (
    ENGLISH,
    SAUDI,
    FakeChat,
    agent,
    call,
    calls,
    reply,
    said,
    talker,
)

ON = VoiceSettings(env="test", tts=TtsSettings(voice_by_script=True))
TWO = (SAUDI, ENGLISH)
ASKED = "How's it going with you?"  # heard as the call's Arabic, as under `session`
FINE = "الحمد لله، كل شيء تمام."  # al-hamdu lillah, kull shay tamam: thank God, all is well
BYE = "مع السلامة."  # ma'a as-salama, goodbye
SAUDI_ASKED = "ابي اغير موعد رحلتي"  # abi aghayyir maw'id rihlati: I want to change my flight
MSA_ASKED = "أريد تغيير موعد رحلتي"  # ureed taghyeer maw'id rihlati: the same, in MSA


def _clauses(events: list[TalkerEvent]) -> list[tuple[str, LanguageTag, Register | None]]:
    spoken = [e for e in events if isinstance(e, SpokenClause)]
    return [(e.text, e.language, e.caller_register) for e in spoken]


def _english_turn(*before: str) -> TalkerTurn:
    """The caller's English small talk in an ar-SA call, heard in Arabic, after `before`."""
    past = tuple(PastTurn(turn_id=n, words=w, fate="answered") for n, w in enumerate(before))
    conversation = Conversation(turns=past)
    return TalkerTurn(turn_id=len(before), words=ASKED, language="ar", conversation=conversation)


def _reply(
    *pieces: str, settings: VoiceSettings = ON, turn: TalkerTurn | None = None
) -> list[TalkerEvent]:
    chat = talker(
        FakeChat(said(*pieces)), language="ar-SA", settings=settings, declared=agent(languages=TWO)
    )
    return reply(chat, turn or _english_turn())


@pytest.mark.parametrize(("before", "register"), [(SAUDI_ASKED, "saudi"), (MSA_ASKED, "msa")])
def test_an_arabic_clause_of_an_english_reply_is_said_in_arabic_in_the_calls_register(
    before: str, register: Register
) -> None:
    events = _reply(f"{FINE} ", "14:00. ", "How can I help?", turn=_english_turn(before))
    assert _clauses(events) == [
        (FINE, "ar-SA", register),
        ("14:00.", "ar-SA", register),  # no letter: the voice before it
        ("How can I help?", "en", None),
    ]


def test_an_english_reply_stays_english_its_first_clause_with_no_letter_too() -> None:
    events = _reply("14:00. ", "The flight leaves then, from gate B. ", f"Bye, {BYE}")
    assert _clauses(events) == [
        ("14:00.", "en", None),
        ("The flight leaves then, from gate B.", "en", None),
        (f"Bye, {BYE}", "ar-SA", "saudi"),  # two Arabic words to one Latin
    ]


def test_an_arabic_reply_keeps_its_voice_through_latin_names() -> None:
    """One way: «flynas XY 299» and "Saudia Business Class" inside Arabic never move it."""
    turn = TalkerTurn(turn_id=0, words="ابي احجز flynas XY 299", language="ar")
    pieces = ("رحلتك على flynas XY 299، الساعة 14:00، ", "Saudia Business Class. ", BYE)
    clauses = _clauses(_reply(*pieces, turn=turn))
    assert [text for text, _, _ in clauses] == [
        "رحلتك على flynas XY 299،",
        "الساعة 14:00،",
        "Saudia Business Class.",
        BYE,
    ]
    assert {(tag, register) for _, tag, register in clauses} == {("ar-SA", "saudi")}


def test_a_blocked_arabic_clause_of_an_english_reply_carries_the_arabic_tag() -> None:
    """Its notice is then said in Arabic (voice/session/talker_play.py)."""
    events = _reply("Sure. ", "رقم حجزك 48213. ")
    found = [
        (type(e).__name__, e.language)
        for e in events
        if isinstance(e, SpokenClause | ClauseBlocked)
    ]
    assert found == [("SpokenClause", "en"), ("ClauseBlocked", "ar-SA")]


def test_the_voice_starts_again_from_the_tag_the_switch_moved_the_reply_to() -> None:
    model = FakeChat(
        calls(call(NAME, language="en"), before="أكيد. "),
        said("14:00. ", f"{BYE} ", "Sure."),
    )
    chat = talker(
        model, language_tool(TWO), language="ar-SA", settings=ON, declared=agent(languages=TWO)
    )
    turn = TalkerTurn(turn_id=1, words="ممكن نكمل بلغة ثانية؟", language="ar-SA")
    assert [(text, tag) for text, tag, _ in _clauses(reply(chat, turn))] == [
        ("أكيد.", "ar-SA"),
        ("14:00.", "en"),  # the moved reply's, not the Arabic clause's before the move
        (BYE, "ar-SA"),
        ("Sure.", "en"),
    ]


def test_off_or_with_no_arabic_tag_every_clause_carries_the_replys_tag() -> None:
    off = _reply(f"{FINE} ", "14:00.", settings=VoiceSettings(env="test"))
    assert _clauses(off) == [(FINE, "en", None), ("14:00.", "en", None)]
    assert arabic_tag(True, call="en", spoken=["en"]) is None
    assert arabic_tag(False, call="ar-SA", spoken=["ar-SA", "en"]) is None
    assert arabic_tag(True, call="en", spoken=["en", "ar-SA"]) == "ar-SA"
    assert arabic_tag(True, call="ar", spoken=["ar-SA", "ar", "en"]) == "ar"  # the call's own
    english = agent(languages=(ENGLISH,))
    pieces = ("Sure. ", f"{FINE} ", "14:00.")
    each = []
    for settings in (ON, VoiceSettings(env="test")):
        chat = talker(FakeChat(said(*pieces)), language="en", settings=settings, declared=english)
        each.append(reply(chat, TalkerTurn(turn_id=0, words=ASKED, language="en")))
    assert each[0] == each[1]

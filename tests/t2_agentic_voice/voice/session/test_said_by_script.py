"""An Arabic clause of an English reply, in the session (agent/clause_voice.py,
`tts.voice_by_script`; voice/session/talker_play.py, open_reply.py, report.py). In an Arabic call
held in its language, the caller asks in English, so the reply is tagged English, and the model
writes Arabic, as gpt-oss did in the owner's calls of 2026-11-22. On, the clause is said in the
Arabic voice, counted under the Arabic model, its time said in Saudi words; off, the English
voice reads it, as before. The call's report records, by turn, the language speech-to-text was
told, the reply's, and the languages its clauses were said in, and reads back the same from its
JSON. The library's `ChatTalker` on a fake chat model, in a session on the fake session I/O;
every line is written for the test."""

from __future__ import annotations

import asyncio
import dataclasses
from datetime import time

import pytest
from t2_agentic_voice.actions.runner import ToolRunner
from t2_agentic_voice.agent.talker import ChatTalker, TalkerCall
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.events import CallReport
from t2_agentic_voice.core.settings.tts import LanguageTag, TtsSettings
from t2_agentic_voice.domain.text.spoken_forms import speak_time
from t2_agentic_voice.voice.session.call import CallSession
from t2_agentic_voice.voice.session.report import numbers

from tests.t2_agentic_voice.agent.chat_support import ENGLISH, SAUDI, FakeChat, agent, said
from tests.t2_agentic_voice.session_fakes import FakeSessionIO
from tests.t2_agentic_voice.voice.session.session_support import greeted, play, report, speaks
from tests.t2_agentic_voice.voice.session.talker_support import talked

AGENT = agent(languages=(SAUDI, ENGLISH))
ASKED = "How's it going with you?"
# al-hamdu lillah, kull shay tamam, wa rihlatak as-sa'a 14:00: thank God, all is well, and your
# flight is at 14:00
FINE = "الحمد لله، كل شيء تمام، ورحلتك الساعة 14:00."


def _call(settings: VoiceSettings, model: FakeChat, *, on: bool = True) -> FakeSessionIO:
    """An ar-SA call of `AGENT` whose talker is the library's own, on `model`, spoken by Groq's
    Orpheus (its models differ by language) with numbers in the caller's register, and the
    setting `on` or off."""
    tts = TtsSettings(provider="groq", spoken_numbers="by_register", voice_by_script=on)
    settings = settings.model_copy(update={"tts": tts})
    io = FakeSessionIO(settings, agent=AGENT, language="ar-SA")
    talker = ChatTalker(
        AGENT,
        model=model,
        runner=ToolRunner([]),
        settings=settings,
        call=TalkerCall(call_id=io.setup.call_id, caller=io.setup.caller, language="ar-SA"),
        clock=io.clock,
    )
    io.setup = dataclasses.replace(io.setup, talker=talker)
    io.attach(CallSession(io.setup, io.commands))
    return io


async def _turns(io: FakeSessionIO, *heard: str) -> None:
    """The greeting, then each of `heard` said, heard in the call's Arabic, and its reply
    played whole; then the call ends."""
    await greeted(io)
    for turn_id, words in enumerate(heard):
        await talked(io, turn_id, words, language="ar")
        await play(io, turn_id + 1)
        await io.clock.advance(1.0)
    await io.ending()
    await io.close()


@pytest.mark.parametrize(("on", "voice"), [(True, "ar-SA"), (False, "en")])
def test_an_arabic_clause_of_an_english_reply_is_said_in_the_arabic_voice(
    settings: VoiceSettings, on: bool, voice: LanguageTag
) -> None:
    io = _call(settings, FakeChat(said(FINE)), on=on)
    asyncio.run(_turns(io, ASKED))
    [speak] = speaks(io, 1)
    assert speak.language == voice
    if on:
        assert "14:00" not in speak.text
        assert speak_time(time(14, 0), language="ar-SA", register="saudi") in speak.text
    languages = io.setup.settings.tts.languages
    models = {u.model: u for u in report(io).usage}
    spoken, other = languages[voice].model, languages["en" if on else "ar-SA"].model
    assert (models[spoken].requests, models[spoken].characters) == (1, len(speak.text))
    assert (models[other].requests if other in models else 0) == 0
    [record] = report(io).turns
    assert (record.language, record.reply_language) == ("ar-SA", "en")
    assert record.spoken_languages == (voice,)


def test_the_report_records_each_turns_reply_and_spoken_languages(
    settings: VoiceSettings,
) -> None:
    """A switch turn answered in Arabic, a same-language turn, and an English reply that ends in
    Arabic: by turn, speech-to-text's language, the reply's, and its clauses' each once in
    order; the report's JSON reads back the same, and its numbers hold them too."""
    model = FakeChat(
        said(FINE),
        said("أبشر، وين ودك تسافر؟"),  # abshir, wain wddak tsafir: sure, where to?
        said("Sure, I can help with that. ", "مع السلامة."),  # ma'a as-salama, goodbye
    )
    io = _call(settings, model)
    asyncio.run(_turns(io, ASKED, "ابي احجز رحلة لجدة", "Can you help me with my booking?"))
    found = report(io)
    assert [(t.language, t.reply_language, t.spoken_languages) for t in found.turns] == [
        ("ar-SA", "en", ("ar-SA",)),
        ("ar-SA", "ar-SA", ("ar-SA",)),
        ("ar-SA", "en", ("en", "ar-SA")),
    ]
    assert CallReport.model_validate_json(found.model_dump_json()) == found
    kept = numbers(found)["turns"]  # what the report's file holds
    assert isinstance(kept, list)
    last = kept[2]
    assert isinstance(last, dict)
    assert (last["reply_language"], last["spoken_languages"]) == ("en", ["en", "ar-SA"])

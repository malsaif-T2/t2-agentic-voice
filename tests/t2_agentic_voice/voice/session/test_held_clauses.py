"""A clause the clause cache held, in the session (voice/session/playback.py, speaker.py, echo.py;
plan 007): a cache hit in the call's usage and in its reply's numbers, sending no characters, yet
never a fixed phrase, so a reply said again says it through text-to-speech, never looking it up
in the phrase cache; and a reply said again says each clause as it was first sent, in its own
language (the text the speaking rules made, an English clause of an Arabic call in the English
voice), so it makes the same key. The fake talker is the tests' own (talker_support.py)."""

from __future__ import annotations

import asyncio

from t2_agentic_voice.agent.talker import ModelReplied, ModelRequested, ReplyDone, SpokenClause
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.conversation import TalkerTurn
from t2_agentic_voice.domain.ports.chat_model import Usage

from tests.t2_agentic_voice.voice.session.session_support import (
    captions,
    greeted,
    play,
    report,
    speaks,
)
from tests.t2_agentic_voice.voice.session.talker_support import (
    MODEL,
    Step,
    answer,
    talked,
    talker_call,
)

ARABIC = "عندك طلب واحد مفتوح."
ENGLISH = "Your ticket 4521 is open."


def test_a_held_clause_is_a_cache_hit_with_no_characters(settings: VoiceSettings) -> None:
    """The first clause held, the second requested: the reply's numbers count one request, its
    characters, and one hit; the call's usage the greeting's hit and the held clause's."""
    io, session, _ = talker_call(
        settings, lambda turn: answer("Your ticket is open.", "We will call you back.")
    )

    async def drive() -> None:
        await greeted(io)
        await talked(io, 0, "where is my ticket")
        first, second = speaks(io, 1)
        await io.clause_queued(1, first.clause, held=True)
        await io.clause_played(1, first.clause, audio_s=0.4)
        await io.synthesizing(1, second.clause)
        await io.clause_queued(1, second.clause)
        await io.clause_played(1, second.clause, audio_s=0.4)
        await io.ending()
        await io.close()

    asyncio.run(drive())
    first, second = speaks(io, 1)
    reply = session._playback.reply(1)
    assert reply is not None
    held, asked = reply.clauses
    assert (held.held, held.cached, asked.held, asked.cached) == (True, False, False, False)
    assert (held.sent, asked.sent) == (first.text, second.text)
    numbers = reply.numbers()
    assert (numbers.requests, numbers.cache_hits, numbers.characters) == (1, 1, len(second.text))
    english = settings.tts.languages["en"].model
    models = {u.model: u for u in report(io).usage}
    assert (models[english].requests, models[english].characters) == (1, len(second.text))
    assert models[english].cache_hits == 2  # the greeting's, then the held clause's
    shown = [c.text for c in captions(io) if c.reply_id == 1]
    assert shown == ["Your ticket is open.", "We will call you back."]


def _two_languages(turn: TalkerTurn) -> list[Step]:
    return [
        ModelRequested(model=MODEL),
        ModelReplied(
            model=MODEL, usage=Usage(input_tokens=90, output_tokens=20), first_token_s=0.3
        ),
        SpokenClause(text=ARABIC, language="ar-SA"),
        SpokenClause(text=ENGLISH, language="en"),
        ReplyDone(),
    ]


def test_a_reply_said_again_says_each_clause_as_sent_in_its_own_language(
    settings: VoiceSettings,
) -> None:
    """An Arabic call's reply of an Arabic clause and an English one with a ticket number,
    the English one held: said again, each clause is the request it first was (its digits said
    as the speaking rules said them, never raw), in its own language's voice, counted under its
    model; the held one is said through text-to-speech, never asked of the phrase cache."""
    io, session, _ = talker_call(settings, _two_languages, language="ar-SA")

    async def drive() -> None:
        await greeted(io)
        await talked(io, 0, "وش حالة طلبي", language="ar")
        arabic, english = speaks(io, 1)
        await io.synthesizing(1, arabic.clause)
        await io.clause_queued(1, arabic.clause)
        await io.clause_played(1, arabic.clause, audio_s=0.4)
        await io.clause_queued(1, english.clause, held=True)
        await io.clause_played(1, english.clause, audio_s=0.4)
        await io.clock.advance(1.0)
        await session._speaker.repeat(io.clock.now(), turn_id=0)
        await play(io, 2)
        await io.ending()
        await io.close()

    asyncio.run(drive())
    first, again = speaks(io, 1), speaks(io, 2)
    assert [(s.text, s.language, s.audio) for s in again] == [
        (s.text, s.language, None) for s in first
    ]
    english = first[1].text
    assert "4521" not in english and "four" in english  # the speaking rules', not the caption's
    assert [c.text for c in captions(io) if c.reply_id == 2] == [ARABIC, ENGLISH]
    assert (ENGLISH, "ar-SA") not in io.phrases.asked and (english, "en") not in io.phrases.asked
    models = {u.model: u for u in report(io).usage}
    arabic_model, english_model = (settings.tts.languages[t].model for t in ("ar-SA", "en"))
    assert (models[arabic_model].requests, models[english_model].requests) == (2, 1)
    assert models[english_model].cache_hits == 1  # the held clause, in its own language

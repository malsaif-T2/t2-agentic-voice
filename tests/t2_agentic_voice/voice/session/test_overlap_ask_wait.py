"""A chat model's wait over an uncertain overlap (voice/session/overlap_ask.py; D-069, plan 006,
Q28), on the real rule and a fake chat model: the reply plays on ducked while it waits and no
step is starved; the turn's own transcript waits for the word, or decides when no whole overlap
went; and a stop, another overlap's stop or the call's end during the wait is safe, with exactly
one `unduck` per decided overlap; a reply that plays out does not cancel the request."""

from __future__ import annotations

import asyncio

from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.events import Interrupted
from t2_agentic_voice.testing.llm_fakes import Pause
from t2_agentic_voice.voice.protocol import Unduck
from t2_agentic_voice.voice.session.commands import StopSpeaking

from tests.t2_agentic_voice.voice.session.overlap_ask_support import (
    GO_ON,
    STOP,
    STOP_WORD,
    TWO_WORDS,
    asking_call,
    over_the_reply,
)
from tests.t2_agentic_voice.voice.session.overlap_support import overlap_part
from tests.t2_agentic_voice.voice.session.session_support import emitted, greeted, report, sent
from tests.t2_agentic_voice.voice.session.talker_support import MODEL, settle, talked


def test_the_reply_plays_on_ducked_while_it_waits_and_no_step_is_starved(
    settings: VoiceSettings,
) -> None:
    io, _session, _talker, _llm = asking_call(settings, (Pause(0.5), *GO_ON))

    async def drive() -> None:
        await over_the_reply(io, TWO_WORDS)
        await asyncio.wait_for(io.clause_played(1, 0), 1.0)  # no lock held for the wait
        await asyncio.wait_for(io.clause_queued(1, 1), 1.0)
        assert not io.commands.of(StopSpeaking)
        assert not sent(io, Unduck)
        await asyncio.wait_for(io.synthesizing(1, 1), 1.0)
        await io.clock.advance(0.6)
        await settle()
        assert len(sent(io, Unduck)) == 1
        await io.ending()
        await io.close()

    asyncio.run(drive())


def test_the_turns_own_transcript_waits_for_the_model_and_is_then_taken(
    settings: VoiceSettings,
) -> None:
    io, _session, talker, _llm = asking_call(settings, (Pause(0.5), *STOP))

    async def drive() -> None:
        await over_the_reply(io, TWO_WORDS)
        await io.turn_closed(1)
        await io.transcribed(1, TWO_WORDS, language="en")
        await settle()
        assert [t.turn_id for t in talker.turns] == [0]  # held, undecided
        await io.clock.advance(0.6)
        await settle()
        assert [t.turn_id for t in talker.turns] == [0, 1]
        await io.ending()
        await io.close()

    asyncio.run(drive())
    (stopped,) = emitted(io, Interrupted)
    assert (stopped.kind, stopped.reason) == ("new_words", "model")


def test_the_turns_own_transcript_decides_when_no_whole_overlap_went(
    settings: VoiceSettings,
) -> None:
    """The overlap's `HearOverlap` reached the bridge after the turn closed: its own transcript
    decides, and the part reusing it changes nothing."""
    io, _session, talker, llm = asking_call(settings, (Pause(0.2), *STOP))

    async def drive() -> None:
        await greeted(io)
        await talked(io, 0, "How do I reset my password?")
        await io.synthesizing(1, 0)
        await io.clause_queued(1, 0)
        await io.clock.advance(0.2)
        await io.turn_opened(1)
        await io.turn_closed(1)
        await io.transcribing(1, audio_s=0.6)
        await io.transcribed(1, TWO_WORDS, language="en")
        await settle()
        assert len(llm.requests) == 1
        await io.transcribed(1, TWO_WORDS, language="en", part="overlap")
        await settle()
        assert len(llm.requests) == 1
        await io.clock.advance(0.3)
        await settle()
        await io.ending()
        await io.close()

    asyncio.run(drive())
    (stopped,) = emitted(io, Interrupted)
    assert stopped.reason == "model"
    assert [t.turn_id for t in talker.turns] == [0, 1]


def test_a_stop_during_the_wait_cancels_the_request_and_leaves_the_rules_verdict(
    settings: VoiceSettings,
) -> None:
    io, _session, talker, _llm = asking_call(settings, (Pause(5.0), *STOP))

    async def drive() -> None:
        await over_the_reply(io, TWO_WORDS)
        await io.client({"v": 1, "type": "stop"})
        await settle()
        assert len(sent(io, Unduck)) == 1  # the rule's verdict, its one unduck
        await io.turn_closed(1)
        await io.transcribed(1, TWO_WORDS, language="en")
        await settle()
        await io.clock.advance(6.0)
        await settle()
        await io.ending()
        await io.close()

    asyncio.run(drive())
    reasons = [(e.kind, e.reason) for e in emitted(io, Interrupted)]
    assert ("new_words", "model") not in reasons
    assert ("false", "short_output") in reasons
    assert [t.turn_id for t in talker.turns] == [0]
    assert len(sent(io, Unduck)) == 1


def test_another_overlaps_stop_during_the_wait_gives_each_duck_one_unduck(
    settings: VoiceSettings,
) -> None:
    io, _session, _talker, _llm = asking_call(settings, (Pause(5.0), *STOP))

    async def drive() -> None:
        await over_the_reply(io, TWO_WORDS)
        await io.turn_opened(2)
        await overlap_part(io, 2, STOP_WORD)
        await settle()
        assert io.commands.of(StopSpeaking) == [StopSpeaking(reply_id=1)]
        await io.clock.advance(6.0)
        await settle()
        await io.ending()
        await io.close()

    asyncio.run(drive())
    assert len(sent(io, Unduck)) == 2
    kinds = sorted((e.kind, e.reason) for e in emitted(io, Interrupted))
    assert kinds == [("false", "short_output"), ("stop", "stop_word")]


def test_the_calls_end_during_the_wait_is_safe(settings: VoiceSettings) -> None:
    io, session, _talker, _llm = asking_call(settings, (Pause(5.0), *STOP))

    async def drive() -> None:
        await over_the_reply(io, TWO_WORDS)
        await io.ending()
        await settle()
        await io.close()

    asyncio.run(drive())
    assert not sent(io, Unduck)  # the end restores the volume, as for any undecided overlap
    assert not emitted(io, Interrupted)
    assert not session._interrupter.asks._asks
    chat = {u.model: u for u in report(io).usage}[MODEL]
    assert chat.requests == 2  # the talker's and the one the end cancelled, which went


def test_a_reply_that_plays_out_during_the_wait_does_not_cancel_the_request(
    settings: VoiceSettings,
) -> None:
    io, session, talker, _llm = asking_call(settings, (Pause(0.5), *STOP))

    async def drive() -> None:
        await over_the_reply(io, TWO_WORDS)
        await io.clause_played(1, 0)
        await io.clause_queued(1, 1)
        await io.clause_played(1, 1)
        await settle()
        reply = session._playback.reply(1)
        assert reply is not None and reply.ended_at is not None
        await io.turn_closed(1)
        await io.transcribed(1, TWO_WORDS, language="en")
        await settle()
        await io.clock.advance(0.6)
        await settle()
        await io.ending()
        await io.close()

    asyncio.run(drive())
    (stopped,) = emitted(io, Interrupted)
    assert (stopped.kind, stopped.reason) == ("new_words", "model")
    assert [t.turn_id for t in talker.turns] == [0, 1]
    assert not io.commands.of(StopSpeaking)  # nothing left to stop
    assert len(sent(io, Unduck)) == 1

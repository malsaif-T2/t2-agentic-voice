"""The replies as they play (voice/session/playback.py) and the heard words (heard.py), beside the
session's own tests: a clause event that names no clause the session asked for, or one of a
reply already ended, changes nothing; a reply's share played and its first audio; a hangup while
the `ended` notice plays; a transcript of marks alone said back as nothing; and a limit's timer
that wakes after its deadline moved."""

from __future__ import annotations

import asyncio

from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.events import AgentSpeechEnded
from t2_agentic_voice.core.settings.limits import LimitSettings
from t2_agentic_voice.domain.ports.speech_to_text import Transcript
from t2_agentic_voice.voice.protocol import Ended, Notice
from t2_agentic_voice.voice.session.commands import HangUp, Speak
from t2_agentic_voice.voice.session.echo import Line
from t2_agentic_voice.voice.session.heard import heard_words
from t2_agentic_voice.voice.session.playback import Playback
from t2_agentic_voice.voice.session.session_events import (
    ClauseFailed,
    ClausePlayed,
    ClauseQueued,
    Synthesizing,
    Transcribed,
)

from tests.t2_agentic_voice.voice.session.session_support import (
    call,
    captions,
    emitted,
    greeted,
    report,
    sent,
    speaks,
    turn,
)


def _line(reply_id: int, clause: int, text: str) -> Line:
    speak = Speak(reply_id=reply_id, clause=clause, turn_id=0, text=text, language="en")
    return Line(speak=speak, caption=text)


def _speaking(playback: Playback) -> bool:
    return playback.speaking


def test_an_event_of_no_clause_asked_for_changes_nothing() -> None:
    playback = Playback()
    reply = playback.ask("echo", [_line(0, 0, "one two"), _line(0, 1, "three")], turn_id=0)
    assert playback.requested(Synthesizing(reply_id=5, clause=0, at=1.0)) is None
    assert playback.requested(Synthesizing(reply_id=0, clause=7, at=1.0)) is None
    assert playback.queued(ClauseQueued(reply_id=0, clause=9, at=1.0, requested_at=None)) is None
    played = ClausePlayed(reply_id=3, clause=0, at=2.0, audio_s=1.0, chunks=1)
    assert playback.done(played) is None
    assert playback.requested(Synthesizing(reply_id=0, clause=0, at=1.0)) is not None
    playback.queued(ClauseQueued(reply_id=0, clause=0, at=1.5, requested_at=1.0))
    playback.done(ClausePlayed(reply_id=0, clause=0, at=2.0, audio_s=1.0, chunks=3))
    assert reply.first_audio_s == 0.5 and [reply.ended_at] == [None] and _speaking(playback)
    playback.done(ClauseFailed(reply_id=0, clause=1, at=2.5, failure="timeout", retryable=True))
    assert reply.ended_at == 2.5 and reply.failed and not _speaking(playback)
    assert reply.clauses[0].played_at == 2.0 and reply.clauses[1].played_at is None
    failed = ClauseFailed(reply_id=0, clause=1, at=3.0, failure="timeout", retryable=True)
    assert playback.done(failed) is None  # its reply has ended
    assert playback.over(2.7) is reply and playback.over(2.9) is None
    assert playback.over(0.5) is None


def test_the_clause_playing_and_the_texts_played_since_a_time() -> None:
    """The clause playing is the first not done of the oldest reply playing, once its first
    audio was queued; the texts played since a time are those clauses', then the one playing."""
    playback = Playback()
    first = playback.ask("echo", [_line(0, 0, "one two"), _line(0, 1, "three")], turn_id=0)
    second = playback.ask("echo", [_line(1, 0, "four")], turn_id=1)
    assert playback.playing() is None and playback.heard_since(0.0) == ()
    playback.queued(ClauseQueued(reply_id=0, clause=0, at=1.0, requested_at=None))
    assert playback.playing() == (first, 0)
    playback.done(ClausePlayed(reply_id=0, clause=0, at=2.0, audio_s=1.0, chunks=1))
    assert playback.playing() is None  # its next clause has no audio yet
    playback.queued(ClauseQueued(reply_id=0, clause=1, at=2.1, requested_at=None))
    playback.queued(ClauseQueued(reply_id=1, clause=0, at=2.2, requested_at=None))
    assert playback.playing() == (first, 1)
    assert playback.heard_since(1.5) == ("one two", "three")
    assert playback.heard_since(2.5) == ("three",)
    playback.done(ClausePlayed(reply_id=0, clause=1, at=3.0, audio_s=1.0, chunks=1))
    assert playback.playing() == (second, 0)
    dropped = playback.drop(3.5, tail=False)
    assert dropped == [second] and second.cut and second.tail_s == 0.0 and not first.cut
    assert playback.over(3.6) is None and playback.over(3.5) is second  # no tail after it


def test_the_session_reads_no_event_of_a_clause_it_did_not_ask_for(
    settings: VoiceSettings,
) -> None:
    io, session = call(settings)

    async def drive() -> None:
        await greeted(io)
        at = io.clock.now()
        await session.handle(ClauseQueued(reply_id=7, clause=0, at=at, requested_at=None))
        await session.handle(ClausePlayed(reply_id=7, clause=0, at=at, audio_s=1.0, chunks=1))
        await session.handle(Synthesizing(reply_id=7, clause=0, at=at))

    asyncio.run(drive())
    assert [c.reply_id for c in captions(io)] == [0]
    assert len(emitted(io, AgentSpeechEnded)) == 1


def test_heard_words_are_the_transcripts_text_without_its_spaces() -> None:
    transcript = Transcript(text="  hello there ", language="en")
    event = Transcribed(turn_id=2, at=5.0, audio_s=1.0, sent_at=4.0, transcript=transcript)
    heard = heard_words(event)
    assert heard is not None and (heard.turn_id, heard.text, heard.language, heard.at) == (
        2,
        "hello there",
        "en",
        5.0,
    )
    none = Transcribed(turn_id=2, at=5.0, audio_s=0.0, sent_at=None, transcript=None)
    assert heard_words(none) is None


def test_a_transcript_of_marks_alone_is_said_back_as_nothing(settings: VoiceSettings) -> None:
    """Direction marks and joiners, which a provider is never sent, say nothing: the splitter
    keeps no clause of them, so there is no reply."""
    io, _ = call(settings)

    async def drive() -> None:
        await greeted(io)
        await turn(io, 0, "‏‍")
        await io.ending()
        await io.close()

    asyncio.run(drive())
    assert speaks(io, 1) == [] and report(io).turns[0].said == ""


def test_a_hangup_while_the_ended_notice_plays_ends_the_call_once(
    settings: VoiceSettings,
) -> None:
    limits = LimitSettings(max_call_s=10.0, idle_s=60.0)
    io, _ = call(settings.model_copy(update={"limits": limits}))

    async def drive() -> None:
        await greeted(io)
        await io.clock.advance(limits.max_call_s)
        await io.clause_queued(1, 0)
        await io.client({"v": 1, "type": "hangup"})
        await io.close()

    asyncio.run(drive())
    assert [n.kind for n in sent(io, Notice)] == ["ended"]
    assert sent(io, Ended) == [Ended(reason="hangup")]
    assert io.commands.of(HangUp) == [HangUp(reason="hangup")]
    assert emitted(io, AgentSpeechEnded)[-1].played_fraction == 0.0


def test_a_limit_whose_deadline_moved_waits_on(settings: VoiceSettings) -> None:
    """The idle timer can find, once it holds the session, that the caller was heard since it
    woke: it does nothing then."""
    io, session = call(settings)

    async def drive() -> None:
        await greeted(io)
        await session._limit("idle")  # well before its deadline
        await session._limit("max_call")

    asyncio.run(drive())
    assert not sent(io, Notice)

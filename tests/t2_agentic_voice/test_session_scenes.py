"""The scenes the session builds on (voice/session/io.py), each played through the fake session
I/O (tests/t2_agentic_voice/session_fakes.py) by a scripted session that gives the commands
`CallSession` will (Track D's tests drive the real one): the greeting, with a turn that opens
while it plays; a stop that drops a reply queued behind another; the call's end, whatever ends
it, with a turn's transcript still to come; and every request that went counted. Every fixed
phrase plays from the cache, and no heard words reach it. Only the first scene greets: the
others leave the greeting out, so their first reply is 1."""

from __future__ import annotations

import asyncio
from collections.abc import Iterable

import pytest
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.events import EndReason, ModelUsage
from t2_agentic_voice.domain.fixed_phrases import fixed_phrases
from t2_agentic_voice.voice.protocol import Caption, Ended, Hangup, Notice, Stop
from t2_agentic_voice.voice.session.commands import Command, HangUp, Send, Speak, StopSpeaking
from t2_agentic_voice.voice.session.session_events import (
    ClauseFailed,
    ClausePlayed,
    ClauseQueued,
    Connected,
    Ending,
    FromClient,
    SessionEvent,
    Synthesizing,
    Transcribed,
    Transcribing,
    TurnClosed,
    TurnOpened,
)

from tests.t2_agentic_voice.session_fakes import FakeSession, FakeSessionIO

HEARD = "words of the test"  # what the caller said, in every scene
LEAKED = "the agent's own greeting, leaked"  # what the caller's microphone caught of it


def played_from_the_cache(io: FakeSessionIO, heard: Iterable[str] = (HEARD, LEAKED)) -> None:
    """Every `Speak` whose text is one of the agent's fixed phrases carries its cached audio,
    and the phrase audio was asked for fixed phrases alone, never for `heard`."""
    fixed = {phrase.text for phrase in fixed_phrases(io.setup.agent)}
    assert all(speak.audio is not None for speak in io.commands.of(Speak) if speak.text in fixed)
    asked = {text for text, _ in io.phrases.asked}
    assert asked <= fixed and not asked & set(heard)


def cached(io: FakeSessionIO, reply_id: int, text: str, *, turn_id: int | None = None) -> Speak:
    """A fixed phrase of the call's language as one clause of `reply_id`, from the cache."""
    tag = io.setup.language.tag
    audio = io.phrases.audio(text, language=tag)
    return Speak(reply_id=reply_id, clause=0, turn_id=turn_id, text=text, language=tag, audio=audio)


def echo(io: FakeSessionIO, reply_id: int, turn_id: int, heard: str) -> list[Command]:
    """A turn's echo as `reply_id`: the cached frame, then the heard words (one request)."""
    frame = cached(io, reply_id, io.setup.language.echo_frame, turn_id=turn_id)
    tag = io.setup.language.tag
    words = Speak(reply_id=reply_id, clause=1, turn_id=turn_id, text=heard, language=tag)
    return [frame, words]


def unfinished(session: FakeSession) -> set[int]:
    """The turns closed whose transcript never came, which the report keeps as unfinished."""
    closed = {e.turn_id for e in session.events if isinstance(e, TurnClosed)}
    return closed - {e.turn_id for e in session.events if isinstance(e, Transcribed)}


def test_the_greeting_and_a_turn_that_opens_while_it_plays_never_share_a_key(
    settings: VoiceSettings,
) -> None:
    """The greeting is reply 0, naming no turn. The caller's turn 0 opens while it plays, so
    the drop rule leaves it unanswered (the session's part, Track D's test); turn 1 opens after
    the greeting, and its echo is reply 1, naming turn 1. A scripted session plays the
    greeting's commands here, as `CallSession` will: every key of a reply's clause, and every
    caption's, is its own, and the call's end leaves the echo's queued clause with no event."""
    io = FakeSessionIO(settings)
    language = io.setup.language
    greeting = cached(io, 0, language.greeting)
    frame, heard = echo(io, 1, 1, HEARD)
    assert isinstance(frame, Speak)

    def caption(speak: Speak) -> Send:
        return Send(
            message=Caption(
                speaker="agent",
                text=speak.text,
                final=True,
                turn_id=speak.turn_id,
                reply_id=speak.reply_id,
                clause=speak.clause,
            )
        )

    def replies(event: SessionEvent) -> list[Command]:
        if isinstance(event, TurnOpened) and event.turn_id == 0:
            return []  # opened during the greeting: dropped
        if isinstance(event, ClauseQueued):
            return [caption(greeting if event.reply_id == 0 else frame)]
        if isinstance(event, Transcribed) and event.turn_id == 1:
            return [frame, heard]
        if isinstance(event, Ending):
            return [HangUp(reason=event.reason)]
        return [greeting] if isinstance(event, Connected) else []

    io.attach(FakeSession(io.setup, io.commands, replies=replies))

    async def call() -> None:
        await io.connected()
        await io.clause_queued(0, 0)
        await io.clock.advance(0.2)
        await io.turn_opened(0)  # its speech began while the greeting played
        await io.clock.advance(0.3)
        await io.clause_played(0, 0, audio_s=0.5)
        await io.turn_closed(0)
        await io.transcribing(0)
        await io.transcribed(0, LEAKED)
        await io.clock.advance(1.0)
        await io.turn_opened(1)
        await io.turn_closed(1)
        await io.transcribing(1)
        await io.transcribed(1, HEARD, language="en")
        await io.clause_queued(1, 0)
        await io.synthesizing(1, 1)
        await io.ending()
        with pytest.raises(RuntimeError, match="FIX: "):  # the end cut the echo
            await io.clause_played(1, 0)
        await io.close()

    asyncio.run(call())
    speaks = io.commands.of(Speak)
    assert speaks == [greeting, frame, heard]
    assert len({(s.reply_id, s.clause) for s in speaks}) == len(speaks)
    assert [s.turn_id for s in speaks] == [None, 1, 1]
    played = [(e.reply_id, e.clause) for e in io.events if isinstance(e, ClauseQueued)]
    captions = [m for m in io.commands.sent if isinstance(m, Caption)]
    assert played == [(0, 0), (1, 0)] and [(c.reply_id, c.clause) for c in captions] == played
    opened = [e for e in io.events if isinstance(e, TurnOpened)]
    greeted = next(e.at for e in io.events if isinstance(e, ClausePlayed))
    assert opened[0].speech_at < greeted < opened[1].speech_at  # turn 0's began in the greeting
    assert io.commands.commands[-1] == HangUp(reason="caller_left")
    played_from_the_cache(io)


def test_a_call_that_ends_with_a_turn_open_hands_none_of_the_turns_events(
    settings: VoiceSettings,
) -> None:
    """The caller leaves mid-turn: the `Ending` ends the call, so no `TurnClosed` or
    `Transcribed` of the turn follows, and the session hangs up (Track D keeps the turn in the
    report as unfinished)."""
    io = FakeSessionIO(settings)

    def replies(event: SessionEvent) -> list[Command]:
        return [HangUp(reason=event.reason)] if isinstance(event, Ending) else []

    io.attach(FakeSession(io.setup, io.commands, replies=replies))

    async def call() -> None:
        await io.connected()
        await io.turn_opened(0)
        await io.ending()
        for late in (io.turn_closed(0), io.transcribed(0, None)):
            with pytest.raises(RuntimeError, match="FIX: "):
                await late

    asyncio.run(call())
    assert [type(e) for e in io.events][-2:] == [TurnOpened, Ending]
    assert io.commands.commands == [HangUp(reason="caller_left")]


def test_a_stop_drops_every_reply_asked_for_and_the_session_goes_on(
    settings: VoiceSettings,
) -> None:
    """Echo 1's heard words fail while its frame plays, so the session queues the `error`
    notice as reply 2 behind it. The caller presses Stop: one `StopSpeaking`, naming reply 2,
    the newest, drops both replies; no event of either follows, the session waits for none,
    and turn 1 is said back as reply 3 (the greeting left out)."""
    io = FakeSessionIO(settings)
    error = io.setup.language.notices["error"]
    told: list[Command] = [Send(message=Notice(kind="error", text=error)), cached(io, 2, error)]

    def replies(event: SessionEvent) -> list[Command]:
        if isinstance(event, Transcribed):
            return echo(io, 1 if event.turn_id == 0 else 3, event.turn_id, HEARD)
        if isinstance(event, ClauseFailed):
            return told
        if isinstance(event, FromClient) and isinstance(event.message, Stop):
            return [StopSpeaking(reply_id=2)]  # the newest reply the session has asked for
        return [HangUp(reason=event.reason)] if isinstance(event, Ending) else []

    io.attach(FakeSession(io.setup, io.commands, replies=replies))

    async def call() -> None:
        await io.connected()
        for turn in (0, 1):
            await io.turn_opened(turn)
            await io.turn_closed(turn)
            await io.transcribing(turn)
            await io.transcribed(turn, HEARD, language="en")
            if turn == 0:
                await io.clause_queued(1, 0)
                await io.synthesizing(1, 1)
                await io.clause_failed(1, 1)
                await io.client('{"v": 1, "type": "stop"}')
                for late in (io.clause_played(1, 0), io.clause_queued(2, 0)):
                    with pytest.raises(RuntimeError, match="FIX: hand no event of a clause"):
                        await late
                await io.clock.advance(1.0)
        await io.clause_queued(3, 0)
        await io.clause_played(3, 0)
        await io.ending()

    asyncio.run(call())
    assert io.commands.of(StopSpeaking) == [StopSpeaking(reply_id=2)]
    assert io.dropped == {(1, 0), (1, 1), (2, 0)}
    assert [(s.reply_id, s.clause) for s in io.commands.of(Speak)][-2:] == [(3, 0), (3, 1)]
    assert io.commands.commands[-1] == HangUp(reason="caller_left")
    played_from_the_cache(io)


def test_a_stop_that_drops_the_ended_notice_hangs_up_at_once(settings: VoiceSettings) -> None:
    """At `limits.max_call_s` the session queues the `ended` notice as reply 2 behind echo 1,
    still playing. A stop drops both, so the notice will never play: the session hangs up at
    once rather than wait for it, and no event follows."""
    io = FakeSessionIO(settings)
    ended = io.setup.language.notices["ended"]
    bye: list[Command] = [Send(message=Ended(reason="max_call")), HangUp(reason="max_call")]

    def replies(event: SessionEvent) -> list[Command]:
        if isinstance(event, Transcribed):
            return echo(io, 1, event.turn_id, HEARD)
        if isinstance(event, FromClient) and isinstance(event.message, Stop):
            return [StopSpeaking(reply_id=2), *bye]  # the ended notice was dropped
        return []

    session = FakeSession(io.setup, io.commands, replies=replies)
    io.attach(session)

    async def call() -> None:
        await io.connected()
        await io.turn_opened(0)
        await io.turn_closed(0)
        await io.transcribing(0)
        await io.transcribed(0, HEARD, language="en")
        await io.clause_queued(1, 0)
        await session.give(Send(message=Notice(kind="ended", text=ended)))  # the limit
        await session.give(cached(io, 2, ended))
        await io.client({"v": 1, "type": "stop"})
        with pytest.raises(RuntimeError, match="FIX: "):
            await io.clause_queued(2, 0)
        await io.close()

    asyncio.run(call())
    assert io.commands.commands[-3:] == [StopSpeaking(reply_id=2), *bye] and session.closed
    played_from_the_cache(io)


@pytest.mark.parametrize("reason", ["hangup", "max_call"])
def test_the_hang_up_leaves_a_turn_whose_transcript_is_still_to_come_unfinished(
    settings: VoiceSettings, reason: EndReason
) -> None:
    """Whatever ends the call, the session's `HangUp` ends a turn closed with its transcript
    still to come: no `Transcribed` of it follows, while the report of its request, which went
    before the Pipecat side carried the `HangUp` out, is still read until the stream ends. A
    `hangup` message ends the call at once; `max_call` once the `ended` notice has played."""
    io = FakeSessionIO(settings)
    ended = io.setup.language.notices["ended"]

    def replies(event: SessionEvent) -> list[Command]:
        if isinstance(event, FromClient) and isinstance(event.message, Hangup):
            return [Send(message=Ended(reason="hangup")), HangUp(reason="hangup")]
        if isinstance(event, ClausePlayed):  # the ended notice has played
            return [Send(message=Ended(reason="max_call")), HangUp(reason="max_call")]
        return []

    session = FakeSession(io.setup, io.commands, replies=replies)
    io.attach(session)

    async def call() -> None:
        await io.connected()
        await io.turn_opened(0)
        await io.turn_closed(0)
        if reason == "hangup":
            await io.client({"v": 1, "type": "hangup"})
        else:  # the session's own timer reached the limit
            await session.give(Send(message=Notice(kind="ended", text=ended)))
            await session.give(cached(io, 1, ended))
            await io.clause_queued(1, 0)
            await io.clause_played(1, 0, audio_s=0.5)
        await io.transcribing(0, audio_s=2.0)
        with pytest.raises(RuntimeError, match="only a request's report follows"):
            await io.transcribed(0, HEARD)
        await io.close()

    asyncio.run(call())
    assert io.commands.commands[-1] == HangUp(reason=reason) and unfinished(session) == {0}
    assert [e.audio_s for e in session.events if isinstance(e, Transcribing)] == [2.0]
    played_from_the_cache(io)


def _ended_by(event: SessionEvent) -> list[Command]:
    """The session's answer to an `Ending`: its `HangUp`, at once."""
    return [HangUp(reason=event.reason)] if isinstance(event, Ending) else []


def test_a_whisper_request_the_end_cancelled_is_still_counted(settings: VoiceSettings) -> None:
    """`TurnClosed`, its `Transcribing`, then an `Ending`: the request went, so the report
    counts it, its audio sent and billed at Whisper's 10 s minimum, though no transcript came
    and the turn stays unfinished. The usage is counted here as io.py says the session counts
    it."""
    io = FakeSessionIO(settings)
    session = FakeSession(io.setup, io.commands, replies=_ended_by)
    io.attach(session)

    async def call() -> None:
        await io.connected()
        await io.turn_opened(0)
        await io.turn_closed(0)
        await io.transcribing(0, audio_s=4.0)
        await io.ending()
        await io.close()

    asyncio.run(call())
    stt = [e for e in session.events if isinstance(e, Transcribing)]
    whisper = ModelUsage(
        model=settings.stt.model,
        requests=len(stt),
        audio_sent_s=sum(e.audio_s for e in stt),
        billed_s=sum(max(10.0, e.audio_s) for e in stt),
    )
    assert (whisper.requests, whisper.audio_sent_s, whisper.billed_s) == (1, 4.0, 10.0)
    assert unfinished(session) == {0} and session.closed


def test_a_synthesis_request_the_end_cancelled_is_still_counted(settings: VoiceSettings) -> None:
    """The echo's heard words are sent to the provider, and the caller leaves before their
    first audio: the request went, so it counts with its characters, while the cached frame,
    which sent none, is a cache hit."""
    io = FakeSessionIO(settings)
    tag = io.setup.language.tag

    def replies(event: SessionEvent) -> list[Command]:
        return echo(io, 1, event.turn_id, HEARD) if isinstance(event, Transcribed) else []

    session = FakeSession(io.setup, io.commands, replies=lambda e: replies(e) + _ended_by(e))
    io.attach(session)

    async def call() -> None:
        await io.connected()
        await io.turn_opened(0)
        await io.turn_closed(0)
        await io.transcribing(0)
        await io.transcribed(0, HEARD, language="en")
        await io.clause_queued(1, 0)
        await io.synthesizing(1, 1)
        await io.ending()
        await io.close()

    asyncio.run(call())
    speaks = {(s.reply_id, s.clause): s for s in io.commands.of(Speak)}
    sent = [speaks[e.reply_id, e.clause] for e in session.events if isinstance(e, Synthesizing)]
    orpheus = ModelUsage(
        model=settings.tts.languages[tag].model,
        requests=len(sent),
        characters=sum(len(s.text) for s in sent),
        cache_hits=sum(s.audio is not None for s in speaks.values()),
    )
    assert (orpheus.requests, orpheus.characters, orpheus.cache_hits) == (1, len(HEARD), 1)
    played_from_the_cache(io)

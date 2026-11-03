"""Each verdict of the two-step interruption through the session (voice/session/interrupter.py;
io.py's overlaps), under `interruptions.mode = "two_step"`, the rule a fake (conftest.py's `rule`):
a turn over the echo lowers the agent's voice and asks for its overlap's transcripts; a stop word
stops the reply at once (`StopSpeaking`, then `unduck`, the cut caption, one `Interrupted`) and is
never said back; new words or a correction stop it and are answered from the turn's own
transcript; a listening sound lets it go on (`unduck` once the whole overlap is heard, the turn
not answered, yet seen by observers); a repeat request stops it and says the last reply again,
its frame from the phrase cache. The stop's scope, the history's marks and the debt paid are
test_overlap_stop.py's; the tail, two overlaps and the held transcript test_overlap_order.py's."""

from __future__ import annotations

import asyncio

import pytest
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.events import AgentSpeechEnded, Interrupted, UserTurnEnded
from t2_agentic_voice.domain.fixed_phrases import fixed_phrases
from t2_agentic_voice.domain.interruptions import Verdict
from t2_agentic_voice.domain.text.invisible import provider_text
from t2_agentic_voice.voice.protocol import Caption, Duck, State, Unduck
from t2_agentic_voice.voice.session.commands import Command, HearOverlap, Send, StopSpeaking
from t2_agentic_voice.voice.session.history import HeardTurn

from tests.t2_agentic_voice.session_fakes import FakeSessionIO
from tests.t2_agentic_voice.voice.session.overlap_support import (
    CORRECTION,
    LISTENING_TEXT,
    NEW_TEXT,
    NEW_WORDS,
    REPEAT_TEXT,
    STOP_TEXT,
    FakeRule,
    echo_playing,
    overlap_part,
    two_step,
)
from tests.t2_agentic_voice.voice.session.session_support import (
    HEARD,
    call,
    captions,
    emitted,
    play,
    report,
    sent,
    speaks,
)


def _after(io: FakeSessionIO, command: Command) -> list[Command]:
    """The commands given after `command`, its last one."""
    given = io.commands.commands
    last = max(i for i, each in enumerate(given) if each == command)
    return given[last + 1 :]


def test_a_stop_word_over_the_echo_stops_it_at_once_and_is_never_said_back(
    settings: VoiceSettings, rule: FakeRule
) -> None:
    """The window holds a stop word: the reply stops (`StopSpeaking`), the voice comes back
    (`unduck`) right after it, the playing clause's caption is sent again marked cut, and the
    agent listens. The whole overlap's transcript changes nothing, and the turn, a command, is
    not said back, though its words reach the observers."""
    io, session = call(two_step(settings))
    frame = io.setup.language.echo_frame

    async def drive() -> None:
        await echo_playing(io)
        await io.turn_opened(1)
        assert io.commands.commands[-2:] == [
            Send(message=Duck(level=0.25)),
            HearOverlap(turn_id=1, window_ms=750),
        ]
        await overlap_part(io, 1, STOP_TEXT, part="window", audio_s=0.75)
        cut = Caption(
            speaker="agent", text=frame, final=True, turn_id=0, reply_id=1, clause=0, cut=True
        )
        assert _after(io, HearOverlap(turn_id=1, window_ms=750)) == [
            StopSpeaking(reply_id=1),
            Send(message=Unduck()),
            Send(message=cut),
            Send(message=State(state="listening")),
        ]
        await overlap_part(io, 1, STOP_TEXT)
        await io.turn_closed(1)
        await io.transcribed(1, STOP_TEXT, language="en")
        await io.ending()
        await io.close()

    asyncio.run(drive())
    assert rule.texts == [STOP_TEXT] * 2  # the whole overlap judged still, deciding nothing
    (stopped,) = emitted(io, Interrupted)
    assert (stopped.turn_id, stopped.kind, stopped.reason) == (0, "stop", "stop_word")
    assert speaks(io, 2) == [] and [c.turn_id for c in captions(io, "caller")] == [0]
    assert sent(io, State)[-1].state == "listening"  # never thinking for a command
    assert [e.turn_id for e in emitted(io, UserTurnEnded)] == [0, 1]
    assert session.history.turns() == (
        HeardTurn(turn_id=0, words=HEARD, fate="rolled_back", reply_id=1),
        HeardTurn(turn_id=1, words=STOP_TEXT, fate="command"),
    )
    assert [c.fate for c in session.history.reply(1).clauses] == ["cut", "unplayed"]
    first, second = report(io).turns
    assert first.stopped and (second.heard, second.said, second.dropped) == (STOP_TEXT, "", False)


@pytest.mark.parametrize("verdict", [NEW_WORDS, CORRECTION], ids=["new-words", "correction"])
def test_new_words_or_a_correction_stop_the_reply_and_are_answered_from_the_turn(
    settings: VoiceSettings, rule: FakeRule, verdict: Verdict
) -> None:
    rule.script[NEW_TEXT] = verdict
    whole = f"{NEW_TEXT} and the rest of it"
    io, session = call(two_step(settings))

    async def drive() -> None:
        await echo_playing(io)
        await io.turn_opened(1)
        await overlap_part(io, 1, NEW_TEXT, part="window", audio_s=0.75)
        assert io.commands.of(StopSpeaking) == [StopSpeaking(reply_id=1)]
        await overlap_part(io, 1, NEW_TEXT)
        await io.turn_closed(1)
        assert sent(io, State)[-1].state == "thinking"  # its answer is awaited
        await io.transcribing(1, audio_s=2.0)  # speech followed: the turn's own request
        await io.transcribed(1, whole, language="en")
        await play(io, 2)
        await io.ending()
        await io.close()

    asyncio.run(drive())
    (stopped,) = emitted(io, Interrupted)
    assert (stopped.turn_id, stopped.kind, stopped.reason) == (0, verdict.kind, "enough_words")
    echo = speaks(io, 2)
    assert [s.turn_id for s in echo] == [1, 1] and echo[1].text == whole
    assert [c.turn_id for c in captions(io, "caller")] == [0, 1]
    assert session.history.turns()[1] == HeardTurn(
        turn_id=1, words=whole, fate="answered", reply_id=2
    )
    assert sent(io, Unduck) == [Unduck()]


def test_a_listening_sound_lets_the_reply_go_on_unducked_and_is_not_answered(
    settings: VoiceSettings, rule: FakeRule
) -> None:
    """The window's verdict to go on waits for the whole overlap, whose verdict decides: the
    voice comes back, the reply plays to its end, and the turn is not answered (`went_on`),
    though its `UserTurnEnded` and an `Interrupted` of kind false tell the observers. The rule
    reads the clauses played lately and the one playing as the agent's own words."""
    io, session = call(two_step(settings))
    frame = io.setup.language.echo_frame

    async def drive() -> None:
        await echo_playing(io)
        await io.turn_opened(1)
        await overlap_part(io, 1, LISTENING_TEXT, part="window", audio_s=0.75)
        assert sent(io, Unduck) == []  # the window's verdict decides nothing
        await overlap_part(io, 1, LISTENING_TEXT)
        assert sent(io, Unduck) == [Unduck()]
        await io.turn_closed(1)
        await io.transcribed(1, LISTENING_TEXT, language="en")  # the overlap's, reused
        _, words = speaks(io, 1)
        await io.clause_played(1, 0)
        await io.synthesizing(1, words.clause)
        await io.clause_queued(1, words.clause)
        await io.clause_played(1, words.clause)
        await io.ending()
        await io.close()

    asyncio.run(drive())
    assert io.commands.of(StopSpeaking) == [] and speaks(io, 2) == []
    assert rule.texts == [LISTENING_TEXT, LISTENING_TEXT]
    greeting = io.setup.language.greeting
    assert rule.judged[0].played == (greeting, frame)  # within own_words_s, then the one playing
    (went_on,) = emitted(io, Interrupted)
    assert (went_on.turn_id, went_on.kind, went_on.reason) == (0, "false", "listening")
    assert [e.turn_id for e in emitted(io, UserTurnEnded)] == [0, 1]
    assert [h.fate for h in session.history.turns()] == ["answered", "went_on"]
    assert emitted(io, AgentSpeechEnded)[-1].played_fraction == 1.0
    assert [c.turn_id for c in captions(io, "caller")] == [0]


def test_a_repeat_request_stops_the_reply_and_says_the_last_reply_again(
    settings: VoiceSettings, rule: FakeRule
) -> None:
    """Over the echo's heard words, a repeat request stops it, then says the whole echo again
    as the reply answering the request: its frame from the phrase cache, its words through
    text-to-speech again, no heard words asked of the phrase cache; the request is a command."""
    io, session = call(two_step(settings))
    frame = io.setup.language.echo_frame

    async def drive() -> None:
        await echo_playing(io)
        _, words = speaks(io, 1)
        await io.clause_played(1, 0)
        await io.synthesizing(1, words.clause)
        await io.clause_queued(1, words.clause)
        await io.turn_opened(1)
        await overlap_part(io, 1, REPEAT_TEXT, part="window", audio_s=0.75)
        await overlap_part(io, 1, REPEAT_TEXT)
        await play(io, 2)
        await io.turn_closed(1)
        await io.transcribed(1, REPEAT_TEXT, language="en", part="turn")
        await io.ending()
        await io.close()

    asyncio.run(drive())
    caption = speaks(io, 1)[1].text
    again = speaks(io, 2)
    assert [(s.clause, s.turn_id, s.audio is not None) for s in again] == [
        (0, 1, True),
        (1, 1, False),
    ]
    assert (again[0].text, again[1].text) == (frame, provider_text(caption))
    stop = io.commands.commands.index(StopSpeaking(reply_id=1))
    assert io.commands.commands[stop + 1] == Send(message=Unduck())
    cut = [c for c in captions(io) if c.cut]
    assert [(c.reply_id, c.clause) for c in cut] == [(1, 1)]
    fixed = {phrase.text for phrase in fixed_phrases(io.setup.agent)}
    assert {text for text, _ in io.phrases.asked} <= fixed  # no heard words reach the cache
    (repeated,) = emitted(io, Interrupted)
    assert (repeated.kind, repeated.reason) == ("new_words", "repeat_word")
    assert session.history.turns()[1] == HeardTurn(
        turn_id=1, words=REPEAT_TEXT, fate="command", reply_id=2
    )
    assert report(io).turns[1].said == f"{frame} {caption}"
    assert [e.turn_id for e in emitted(io, AgentSpeechEnded)][-1] == 1


def test_a_repeat_while_the_ended_notice_plays_hangs_up_and_says_nothing_after(
    settings: VoiceSettings, rule: FakeRule
) -> None:
    """At the call's limit the `ended` notice plays; a repeat request over it stops it, which
    ends the call at once: nothing is said again, and `HangUp` is the last command."""
    from t2_agentic_voice.core.settings.limits import LimitSettings
    from t2_agentic_voice.voice.protocol import Ended
    from t2_agentic_voice.voice.session.commands import HangUp

    limits = LimitSettings(max_call_s=30.0, idle_s=60.0)
    io, _ = call(two_step(settings).model_copy(update={"limits": limits}))

    async def drive() -> None:
        await echo_playing(io)
        await io.clock.advance(limits.max_call_s)  # the notice is asked for behind the echo
        await play(io, 1)
        await io.clause_queued(2, 0)  # the notice plays
        await io.turn_opened(1)
        await overlap_part(io, 1, REPEAT_TEXT, part="window", audio_s=0.75)
        await io.close()

    asyncio.run(drive())
    assert _after(io, HearOverlap(turn_id=1, window_ms=750)) == [
        StopSpeaking(reply_id=2),
        Send(message=Unduck()),
        Send(message=Ended(reason="max_call")),
        HangUp(reason="max_call"),
    ]
    assert speaks(io, 3) == []

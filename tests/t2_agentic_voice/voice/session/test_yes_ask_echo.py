"""What the session tells the yes rule's echo rail (voice/session/read_back.py's
`Confirming.over_read_back` and `over_follow_up`, yes_ask.py; D-082, the owner's third ruling of
2026-11-10): the read-back, and a line that asked it again, are heard from their reply's first
audio to the end of its tail after it ended (the drop rule's window), and only speech begun then
may be its echo; the session keeps the rail when it cannot tell. On the real yes rule, its words
and a fake chat model, for an agent that asks: words that copy the ask-again line, said over it,
are asked again whatever the model says, and said once it and its tail ended, or words that copy
the closing question said so, are the model's to judge (test_yes_ask_tail.py has the tail)."""

from __future__ import annotations

import asyncio

import pytest
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.events import ConfirmationAnswered
from t2_agentic_voice.testing.llm_fakes import ScriptedLLM
from t2_agentic_voice.voice.session.call import CallSession
from t2_agentic_voice.voice.session.playback import DROP_AFTER_S

from tests.t2_agentic_voice.session_fakes import FakeSessionIO
from tests.t2_agentic_voice.voice.session.read_back_support import asked, over, read_whole
from tests.t2_agentic_voice.voice.session.session_support import emitted, speaks
from tests.t2_agentic_voice.voice.session.talker_support import AGENT, settle, talked
from tests.t2_agentic_voice.voice.session.yes_support import (
    FakeJobs,
    confirm_call,
    play_reply,
    read_back_played,
)

ASKS = AGENT.model_copy(update={"ask_on_unlisted_answers": True})
UNCLEAR = "please"  # a filler alone: the lists ask it again, and ask no model
# Words that copy the read-back_support plan's ask-again line, "Made-up line asking again.",
# and its closing question, "Made-up closing question, shall I go ahead?".
COPIES_ASKED = "asking again"
COPIES_QUESTION = "shall I go ahead"


def _call(settings: VoiceSettings) -> tuple[FakeSessionIO, CallSession, ScriptedLLM, FakeJobs]:
    """A confirming call of an agent that asks, whose chat model says `send` to every check."""
    llm, jobs = ScriptedLLM([ScriptedLLM.reply("send") for _ in range(3)]), FakeJobs()
    io, session, _ = confirm_call(settings, jobs, agent=ASKS, overlap_model=llm)
    llm.clock = io.clock
    return io, session, llm, jobs


def _answered(io: FakeSessionIO) -> list[tuple[int | None, str, str]]:
    return [(e.turn_id, e.decision, e.by) for e in emitted(io, ConfirmationAnswered)]


def test_the_read_back_is_heard_while_its_reply_plays_and_within_its_tail(
    settings: VoiceSettings,
) -> None:
    """`over_read_back`: the read-back's reply playing, or within `DROP_AFTER_S` after it
    ended (playback.py's, the drop rule's); True when the session cannot tell."""
    io, session, _, _ = _call(settings)
    confirming = session._confirming
    seen: dict[str, bool] = {}

    async def drive() -> None:
        seen["none current"] = confirming.over_read_back(io.clock.now())
        await asked(io)
        await read_whole(io)
        await settle()
        ended = io.clock.now()
        seen["its question plays"] = confirming.over_read_back(ended - 0.1)
        seen["at its end"] = confirming.over_read_back(ended)
        seen["within its tail"] = confirming.over_read_back(ended + 0.25)
        seen["at its tail's end"] = confirming.over_read_back(ended + DROP_AFTER_S)
        seen["past its tail"] = confirming.over_read_back(ended + 0.4)
        seen["no time"] = confirming.over_read_back(None)

    asyncio.run(drive())
    assert seen == {
        "none current": True,
        "its question plays": True,
        "at its end": True,
        "within its tail": True,
        "at its tail's end": True,
        "past its tail": False,
        "no time": True,
    }


def test_a_line_that_asked_again_is_heard_from_its_first_audio_to_its_tails_end(
    settings: VoiceSettings,
) -> None:
    io, session, _, _ = _call(settings)
    confirming = session._confirming
    seen: dict[str, bool] = {}

    async def drive() -> None:
        await read_back_played(io)
        seen["none asked"] = confirming.over_follow_up(io.clock.now())
        await talked(io, 1, UNCLEAR)  # asked again: reply 2, nothing of it played yet
        asked_at = io.clock.now()
        seen["asked, not playing"] = confirming.over_follow_up(asked_at)
        (speak,) = speaks(io, 2)
        await io.synthesizing(2, speak.clause)
        await io.clock.advance(0.2)
        await io.clause_queued(2, speak.clause)
        began = io.clock.now()
        seen["its first audio"] = confirming.over_follow_up(began)
        seen["before it"] = confirming.over_follow_up(began - 0.1)
        await io.clock.advance(0.5)
        await io.clause_played(2, speak.clause, audio_s=0.5)
        await settle()
        ended = io.clock.now()
        seen["as it plays"] = confirming.over_follow_up(ended - 0.1)
        seen["at its end"] = confirming.over_follow_up(ended)
        seen["within its tail"] = confirming.over_follow_up(ended + 0.25)
        seen["past its tail"] = confirming.over_follow_up(ended + 0.4)
        seen["after it"] = confirming.over_follow_up(ended + 1.0)
        seen["no time"] = confirming.over_follow_up(None)
        confirming._follow_ups.add(99)  # a line the session no longer holds
        seen["unknown line"] = confirming.over_follow_up(ended + 1.0)

    asyncio.run(drive())
    assert seen == {
        "none asked": False,
        "asked, not playing": False,
        "its first audio": True,
        "before it": False,
        "as it plays": True,
        "at its end": True,
        "within its tail": True,
        "past its tail": False,
        "after it": False,
        "no time": True,
        "unknown line": True,
    }


def test_words_that_copy_the_ask_again_line_over_it_are_asked_again_whatever_the_model_says(
    settings: VoiceSettings,
) -> None:
    io, _session, llm, jobs = _call(settings)

    async def drive() -> None:
        await read_back_played(io)
        await talked(io, 1, UNCLEAR)
        (speak,) = speaks(io, 2)
        await io.synthesizing(2, speak.clause)
        await io.clause_queued(2, speak.clause)  # the line that asks again plays
        await over(io, 2, COPIES_ASKED)
        await io.clock.advance(5.0)
        await settle()

    asyncio.run(drive())
    assert _answered(io) == [(1, "asked_again", "words"), (2, "asked_again", "model")]
    assert len(llm.requests) == 1 and jobs.runs == []


@pytest.mark.parametrize("words", [COPIES_ASKED, COPIES_QUESTION])
def test_words_that_copy_a_line_said_once_it_ended_are_the_models_to_judge(
    settings: VoiceSettings, words: str
) -> None:
    """Speech begun when no line played cannot be the agent's echo: the model's `send`
    confirms."""
    io, _session, llm, jobs = _call(settings)

    async def drive() -> None:
        await read_back_played(io)
        await talked(io, 1, UNCLEAR)
        await play_reply(io, 2)
        await io.clock.advance(1.0)
        await talked(io, 2, words)
        await settle()

    asyncio.run(drive())
    assert _answered(io) == [(1, "asked_again", "words"), (2, "yes", "model")]
    assert len(llm.requests) == 1
    (run,) = jobs.runs
    assert (run.confirmed.turn_id, run.confirmed.words) == (2, words)

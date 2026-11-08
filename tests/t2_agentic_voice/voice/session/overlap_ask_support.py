"""What the tests of a chat model's word on an uncertain overlap share
(voice/session/overlap_ask.py; D-069): an agent that asks for it, a reply of two clauses to speak
over, and a call whose overlaps ask a fake chat model, on the fake session I/O and the real
rule."""

from __future__ import annotations

from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.conversation import TalkerTurn
from t2_agentic_voice.domain.declaration import Language, VoiceAgent
from t2_agentic_voice.domain.words import PRESET_WORDS
from t2_agentic_voice.testing.llm_fakes import ScriptedLLM, ScriptStep
from t2_agentic_voice.voice.session.call import CallSession

from tests.t2_agentic_voice.session_fakes import FakeSessionIO
from tests.t2_agentic_voice.voice.session.overlap_support import overlap_part, two_step
from tests.t2_agentic_voice.voice.session.session_support import greeted
from tests.t2_agentic_voice.voice.session.talker_support import (
    FakeTalker,
    Step,
    answer,
    settle,
    talked,
    talker_call,
)

ASKING = VoiceAgent(
    name="asking-test",
    languages=[Language.english(greeting="Welcome to the test line")],
    instructions="Answer briefly.",
    ask_on_uncertain_overlaps=True,
)
TWO_WORDS = "need agent"  # the rule's short output, on its two words
ONE_WORD = "agent"
LISTENING = PRESET_WORDS["en"].backchannel[-1]
STOP_WORD = PRESET_WORDS["en"].stop[0]
STOP = ScriptedLLM.reply("stop")
GO_ON = ScriptedLLM.reply("go_on")


def two_clauses(turn: TalkerTurn) -> list[Step]:
    """A reply of two clauses to turn 0; one clause to any later turn."""
    if turn.turn_id == 0:
        return answer("Open Settings first.", "Then press Reset.")
    return answer("Made-up answer.")


def asking_call(
    settings: VoiceSettings, *entries: tuple[ScriptStep, ...], agent: VoiceAgent = ASKING
) -> tuple[FakeSessionIO, CallSession, FakeTalker, ScriptedLLM]:
    """A session of the talker agent `agent` whose overlaps may ask the fake model `entries`
    scripts, on the fake session I/O, the model's pauses on its clock."""
    llm = ScriptedLLM(entries)
    io, session, talker = talker_call(
        two_step(settings), two_clauses, agent=agent, overlap_model=llm
    )
    llm.clock = io.clock
    return io, session, talker, llm


async def over_the_reply(io: FakeSessionIO, text: str, *, played_s: float = 0.2) -> None:
    """Turn 0's reply (reply 1, two clauses) plays its first; the caller says `text` over it
    (turn 1), its whole overlap heard `played_s` after the speech began."""
    await greeted(io)
    await talked(io, 0, "How do I reset my password?")
    await io.synthesizing(1, 0)
    await io.clause_queued(1, 0)
    await io.clock.advance(0.2)
    await io.turn_opened(1)
    await io.clock.advance(played_s)
    await overlap_part(io, 1, text)
    await settle()

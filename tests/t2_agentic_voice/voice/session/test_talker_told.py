"""What the talker's failures leave behind in a call (voice/session/talking.py, D-077 and D-078):
a clause that fails after another played told at the reply's end, after a beat, and a tool call
in the trace with what failed. The fake talker is the tests' own (talker_support.py)."""

from __future__ import annotations

import asyncio

from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from t2_agentic_voice.agent.talker import ToolBegan, ToolEnded
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.conversation import TalkerTurn
from t2_agentic_voice.core.tracing import Tracing
from t2_agentic_voice.voice.session.echo import BEAT_S

from tests.t2_agentic_voice.voice.session.session_support import greeted, play, speaks
from tests.t2_agentic_voice.voice.session.talker_support import (
    AGENT,
    Step,
    answer,
    talked,
    talker_call,
)


def test_a_clause_that_fails_after_one_played_is_told_at_the_replys_end_after_a_beat(
    settings: VoiceSettings,
) -> None:
    """D-077: no clause of the reply follows the line, which says the answer was cut off and is
    longer than its phrase by the beat before it."""

    def script(turn: TalkerTurn) -> list[Step]:
        return [*answer("First.", "Second.", "Third.")]

    io, _, _ = talker_call(settings, script, language="en")

    async def drive() -> None:
        await greeted(io)
        await talked(io, 0, "Where is my ticket?", language="en")
        await io.clause_queued(1, 0)
        await io.clause_played(1, 0)
        await io.clause_failed(1, 1)
        assert len(speaks(io)) == 4  # the greeting and the three clauses: nothing told yet
        await io.clause_queued(1, 2)
        await io.clause_played(1, 2)
        await io.ending()
        await io.close()

    asyncio.run(drive())
    english = AGENT.languages[0]
    [told] = speaks(io, 2)
    assert told.text == english.notices["cut_off"]
    phrase = io.setup.phrases.audio(told.text, language="en")
    assert told.audio is not None
    assert len(told.audio.pcm16) - len(phrase.pcm16) == 2 * round(BEAT_S * phrase.sample_rate)


def test_a_tool_call_of_the_talker_reaches_the_trace(settings: VoiceSettings) -> None:
    exporter = InMemorySpanExporter()

    def script(turn: TalkerTurn) -> list[Step]:
        return [
            ToolBegan(call_id="t-1", tool="search_help", arguments='{"query": "my ticket"}'),
            ToolEnded(
                call_id="t-1",
                tool="search_help",
                ok=False,
                ms=900.0,
                failure="timeout",
                result='{"error": "the tool failed"}',
            ),
            *answer("Sorry."),
        ]

    io, session, _ = talker_call(settings, script, tracing=Tracing(exporter=exporter))

    async def drive() -> None:
        await greeted(io)
        await talked(io, 0, "Where is my ticket?", language="en")
        await play(io, 1)
        await io.ending()
        await io.close()

    asyncio.run(drive())
    session._setup.tracing.shutdown()
    [tool] = [s for s in exporter.get_finished_spans() if s.name == "tool"]
    assert (tool.attributes or {})["tool.failure"] == "timeout"
    assert (tool.attributes or {})["input.value"] == '{"query": "my ticket"}'
    assert (tool.attributes or {})["output.value"] == '{"error": "the tool failed"}'
    [root] = [s for s in exporter.get_finished_spans() if s.name == "turn"]
    assert (root.attributes or {})["input.value"] == "Where is my ticket?"
    assert (root.attributes or {})["output.value"] == "Sorry."

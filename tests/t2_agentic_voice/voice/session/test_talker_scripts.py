"""The stray-script filter as a call plays the talker's reply (agent/turn.py's filter,
voice/session/talker_play.py, voice/session/report.py): the library's `ChatTalker` on a fake
chat model, in a session on the fake session I/O. The caption, the heard history,
`AgentSpeechEnded.text`, the turn span's said text and `ToolStarted.arguments` hold the
filtered text; the turn's span carries `turn.stray_characters` and `turn.stray_scripts` only on
a turn with a removal; `talker_stray_script_removed` logs the call, the turn, the count and the
labels, never a character or the reply's words; and a reply the filter leaves nothing to say
(«重置 → 确认» alone, or a reply wholly in a stray script) gives the `error` notice, as an
empty answer does."""

from __future__ import annotations

import asyncio
import dataclasses
import json
import logging

import pytest
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from t2_agentic_voice.actions.runner import ToolRunner
from t2_agentic_voice.actions.tools import tool
from t2_agentic_voice.agent.talker import ChatTalker, TalkerCall
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.events import AgentSpeechEnded, ToolStarted
from t2_agentic_voice.core.tracing import Tracing
from t2_agentic_voice.domain.declaration import Language, VoiceAgent
from t2_agentic_voice.voice.session.call import CallSession

from tests.leaks import holding, shown
from tests.t2_agentic_voice.agent.chat_support import FakeChat, Step, call, calls, said
from tests.t2_agentic_voice.session_fakes import FakeSessionIO
from tests.t2_agentic_voice.voice.session.session_support import captions, greeted, play, speaks
from tests.t2_agentic_voice.voice.session.talker_support import talked

ENGLISH = Language.english(greeting="Welcome to the test line")


@tool(description="Find a made-up help page.")
async def find_page(query: str) -> dict[str, str]:
    return {"found": "a made-up page"}


AGENT = VoiceAgent(
    name="talker-test", languages=[ENGLISH], instructions="Answer briefly.", tools=[find_page]
)


def _call(
    settings: VoiceSettings, *entries: list[Step], exporter: InMemorySpanExporter | None = None
) -> tuple[FakeSessionIO, CallSession]:
    """A session of `AGENT` whose talker is the library's own, on a fake chat model that plays
    `entries`, traced to `exporter` when given."""
    io = FakeSessionIO(settings, agent=AGENT)
    talker = ChatTalker(
        AGENT,
        model=FakeChat(*entries),
        runner=ToolRunner([find_page]),
        settings=settings,
        call=TalkerCall(call_id=io.setup.call_id, caller=io.setup.caller, language="en"),
        clock=io.clock,
    )
    tracing = io.setup.tracing if exporter is None else Tracing(exporter=exporter)
    io.setup = dataclasses.replace(io.setup, talker=talker, tracing=tracing)
    session = CallSession(io.setup, io.commands)
    io.attach(session)
    return io, session


def _run(io: FakeSessionIO, *turns: str) -> None:
    """The call greets, each of `turns` is said and its reply played whole, and it ends."""

    async def drive() -> None:
        await greeted(io)
        for index, words in enumerate(turns):
            await talked(io, index, words)
            await play(io, index + 1)
            await io.clock.advance(1.0)
        await io.ending()
        await io.close()

    asyncio.run(drive())


def test_everything_the_call_shows_of_the_reply_holds_the_filtered_text(
    settings: VoiceSettings,
) -> None:
    exporter = InMemorySpanExporter()
    io, session = _call(
        settings,
        calls(call("find_page", query="reset重 password"), before="Let me 重check. "),
        said("Open Settings😀, then Reset重置."),
        exporter=exporter,
    )
    _run(io, "How do I reset my password?")
    said_clauses = ["Let me check.", "Open Settings, then Reset."]
    assert [c.text for c in captions(io) if c.reply_id == 1] == said_clauses
    [reply] = [r for r in session.history.replies() if r.turn_id == 0]
    assert [clause.text for clause in reply.clauses] == said_clauses
    [spoken] = [e for e in io.emitted if isinstance(e, AgentSpeechEnded) and e.turn_id == 0]
    assert spoken.text == " ".join(said_clauses)
    tool_events = [e for e in io.emitted if isinstance(e, ToolStarted)]  # ToolFinished too
    assert [json.loads(e.arguments) for e in tool_events] == [{"query": "reset password"}] * 2
    session._setup.tracing.shutdown()
    [turn] = [s for s in exporter.get_finished_spans() if s.name == "turn"]
    attributes = turn.attributes or {}
    assert attributes["output.value"] == " ".join(said_clauses)
    assert "重" not in json.dumps(dict(attributes), ensure_ascii=False)
    [traced] = [s for s in exporter.get_finished_spans() if s.name == "tool"]
    assert json.loads(str((traced.attributes or {})["input.value"])) == {"query": "reset password"}


def test_the_turns_span_counts_a_removal_only_on_a_turn_that_had_one(
    settings: VoiceSettings,
) -> None:
    exporter = InMemorySpanExporter()
    io, session = _call(
        settings, said("Restart重 it 😀 now."), said("All good."), exporter=exporter
    )
    _run(io, "My laptop is stuck.", "Thanks.")
    session._setup.tracing.shutdown()
    turns = sorted(
        (s for s in exporter.get_finished_spans() if s.name == "turn"),
        key=lambda span: span.start_time or 0,
    )
    first, second = (dict(span.attributes or {}) for span in turns)
    assert (first["turn.stray_characters"], first["turn.stray_scripts"]) == (2, "CJK,PICTOGRAPH")
    assert "turn.stray_characters" not in second and "turn.stray_scripts" not in second


def test_the_log_line_holds_counts_and_labels_only(
    settings: VoiceSettings, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG, logger="t2_agentic_voice")
    io, _ = _call(settings, said("Restart重 it 😀 now."), said("All good."))
    _run(io, "My laptop is stuck.", "Thanks.")
    [record] = [r for r in caplog.records if r.getMessage() == "talker_stray_script_removed"]
    fields = dict(record.fields)  # type: ignore[attr-defined]
    assert fields == {
        "call_id": "call-1",
        "turn_id": 0,
        "characters": 2,
        "scripts": ("CJK", "PICTOGRAPH"),
    }
    surfaces = shown(caplog=caplog)
    for value in ("重", "😀", "Restart", "My laptop"):
        assert holding(value, surfaces) == [], value


@pytest.mark.parametrize("written", ["重置 → 确认", "重置确认。", "😀"])
def test_a_reply_the_filter_leaves_nothing_to_say_gives_the_error_notice(
    settings: VoiceSettings, written: str
) -> None:
    io, _ = _call(settings, said(written))
    _run(io, "How do I reset it?")
    assert [s.text for s in speaks(io, 1)] == [ENGLISH.notices["error"]]

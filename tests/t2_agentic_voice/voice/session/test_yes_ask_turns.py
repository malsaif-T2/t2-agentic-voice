"""A judged answer's turn (voice/session/yes_ask.py, turn_book.py; D-082): while a chat model's
word on it is awaited the turn is neither answered nor settled, so it settles once its verdict's
reply has played, as any turn does: its `TurnMetrics` then carry its time to first audio, the
wait for the word included, its trace ends after that reply, the reply's and its tools' spans
under the turn's, and the heard history holds the reply that answers it. A request a newer
answer or a stale read-back drops leaves the turn answered by nothing; one the call's end
cancels leaves it unfinished; each settles once."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence

import pytest
from openinference.semconv.trace import SpanAttributes
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from t2_agentic_voice.agent.talker import ToolBegan, ToolEnded
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.conversation import TalkerTurn
from t2_agentic_voice.core.events import TurnMetrics
from t2_agentic_voice.core.tracing import Tracing
from t2_agentic_voice.domain.words import PRESET_WORDS
from t2_agentic_voice.testing.llm_fakes import Pause, ScriptedLLM
from t2_agentic_voice.voice.session.call import CallSession

from tests.t2_agentic_voice.session_fakes import FakeSessionIO
from tests.t2_agentic_voice.voice.session.read_back_support import reads_back
from tests.t2_agentic_voice.voice.session.session_support import emitted, report, spans, turn
from tests.t2_agentic_voice.voice.session.talker_support import (
    AGENT,
    Step,
    answer,
    settle,
    talked,
)
from tests.t2_agentic_voice.voice.session.yes_support import (
    FakeJobs,
    confirm_call,
    play_reply,
    read_back_played,
)

ASKS = AGENT.model_copy(update={"ask_on_unlisted_answers": True})
UNLISTED = "go for it"  # words on none of the lists
WAIT_S = 0.4  # the model's time to its word, which the caller waits through in silence
TOOL = "search_help"


def _script(turn: TalkerTurn) -> Sequence[Step]:
    """Turn 0's reply reads the plan back; a later turn's runs a tool, then says one clause."""
    if turn.turn_id == 0:
        return reads_back(turn)
    ran: list[Step] = [
        ToolBegan(call_id="t-1", tool=TOOL),
        ToolEnded(call_id="t-1", tool=TOOL, ok=True, ms=1.0),
    ]
    return [*ran, *answer("Made-up answer.")]


def _call(
    settings: VoiceSettings, word: str, *, wait_s: float = WAIT_S
) -> tuple[FakeSessionIO, CallSession, InMemorySpanExporter]:
    """A confirming call of an agent that asks, traced to memory, whose chat model gives `word`
    `wait_s` after it is asked."""
    exporter = InMemorySpanExporter()
    llm = ScriptedLLM([(Pause(wait_s), *ScriptedLLM.reply(word))])
    io, session, _ = confirm_call(
        settings,
        FakeJobs(),
        _script,
        agent=ASKS,
        overlap_model=llm,
        tracing=Tracing(exporter=exporter),
    )
    llm.clock = io.clock
    return io, session, exporter


def _told(io: FakeSessionIO, turn_id: int) -> list[TurnMetrics]:
    return [m for m in emitted(io, TurnMetrics) if m.turn_id == turn_id]


def _under(every: list[ReadableSpan], parent: ReadableSpan) -> list[str]:
    """The names of the spans directly under `parent`."""
    return [s.name for s in every if s.parent is not None and s.parent == parent.context]


@pytest.mark.parametrize("word", ["send", "unclear", "change"])
def test_a_judged_turn_settles_once_its_verdicts_reply_has_played(
    settings: VoiceSettings, word: str
) -> None:
    io, session, exporter = _call(settings, word)
    stop_s = settings.turns.vad_stop_ms / 1000

    async def drive() -> None:
        await read_back_played(io)
        await talked(io, 1, UNLISTED)
        assert _told(io, 1) == []  # its answer is judged: the turn is not settled
        await io.clock.advance(WAIT_S)  # the model's word lands: reply 2 answers the turn
        await settle()
        await io.clock.advance(0.1)
        await play_reply(io, 2)
        await io.ending()
        await io.close()

    asyncio.run(drive())
    times = report(io).turns[1].times
    (metrics,) = _told(io, 1)
    assert metrics.ttfa_ms is not None and metrics.ttfa_ms == times.ttfa_ms
    assert metrics.ttfa_ms == pytest.approx((WAIT_S + 0.1 + stop_s) * 1000)
    (heard,) = [t for t in session.history.turns() if t.turn_id == 1]
    assert (heard.fate, heard.reply_id) == ("answered", 2)
    every = spans(session, exporter)
    (root,) = [s for s in every if s.parent is None and (s.attributes or {}).get("turn.id") == 1]
    attributes = root.attributes or {}
    assert attributes["turn.ttfa_ms"] == metrics.ttfa_ms
    assert attributes[SpanAttributes.OUTPUT_VALUE] == session.history.reply(2).text
    under = _under(every, root)
    assert "text_to_speech" in under  # the reply's span, under the turn's
    if word == "change":
        assert "tool" in under  # the talker's tool call, while the turn's span was open


@pytest.mark.parametrize(
    ("how", "fate"), [("newer", "answered"), ("stale", "answered"), ("end", "unfinished")]
)
def test_a_judged_turn_whose_word_decides_nothing_settles_once(
    settings: VoiceSettings, how: str, fate: str
) -> None:
    """A newer listed no cancels the request; a stop word declines the read-back before the
    word lands (stale); the call's end cancels it: the turn is answered by nothing, or is
    unfinished, and its times go out once, with no time to first audio."""
    io, session, _ = _call(settings, "send", wait_s=1.0)
    newer = {"newer": "no", "stale": PRESET_WORDS["en"].stop[0]}

    async def drive() -> None:
        await read_back_played(io)
        await talked(io, 1, UNLISTED)
        if how in newer:
            await turn(io, 2, newer[how], audio_s=0.2)
            await settle()
            await io.clock.advance(5.0)
            await settle()
        await io.ending()
        await io.close()

    asyncio.run(drive())
    (metrics,) = _told(io, 1)
    assert metrics.ttfa_ms is None
    (heard,) = [t for t in session.history.turns() if t.turn_id == 1]
    assert (heard.fate, heard.reply_id) == (fate, None)

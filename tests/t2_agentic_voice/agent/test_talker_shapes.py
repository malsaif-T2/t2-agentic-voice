"""The talker as the session sees it (agent/talker.py, prompt.py; plan 006, Block 0): the events
it streams load and refuse a wrong value; the session's cancel scope is the scope it starts its
work in, and the call's clock the one it times its work on; and the loop and the prompt are
given."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import date
from typing import Any

import pytest
from pydantic import ValidationError
from t2_agentic_voice.actions.runner import ToolRunner
from t2_agentic_voice.agent.prompt import compose_prompt, render_prompt
from t2_agentic_voice.agent.talker import (
    ChatTalker,
    ClauseBlocked,
    ModelReplied,
    ModelRequested,
    ProgressDue,
    ReplyDone,
    ReplyScope,
    ShownCard,
    SpokenClause,
    Talker,
    TalkerCall,
    ToolBegan,
    ToolEnded,
)
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.conversation import TalkerTurn
from t2_agentic_voice.core.identity import Caller
from t2_agentic_voice.domain.cards import Card
from t2_agentic_voice.domain.declaration import Language, VoiceAgent
from t2_agentic_voice.domain.ports.chat_model import Usage
from t2_agentic_voice.testing.llm_fakes import ScriptedLLM
from t2_agentic_voice.voice.session.scope import CancelScope

from tests.t2_agentic_voice.fakes import FakeClock

AGENT = VoiceAgent(
    name="helper", languages=[Language.english(greeting="Hi")], instructions="Answer briefly."
)
CALL = TalkerCall(call_id="call-1", caller=Caller(subject="made-up"), language="en")


def test_the_events_a_reply_streams_load() -> None:
    events = [
        ModelRequested(model="openai/gpt-oss-120b"),
        SpokenClause(text="Open Settings first.", language="en"),
        ToolBegan(call_id="c-1", tool="search_help"),
        ProgressDue(tool="search_help", key="searching", language="en"),
        ToolEnded(call_id="c-1", tool="search_help", ok=True, ms=840.0),
        ShownCard(card=Card(title="Reset a password", steps=("Open", "Reset"))),
        ClauseBlocked(text="Your number is 4521.", language="en", unsupported=("4521",)),
        ModelReplied(model="openai/gpt-oss-120b", usage=Usage(input_tokens=9, output_tokens=3)),
        ReplyDone(),
    ]
    assert [type(event).__name__ for event in events][-1] == "ReplyDone"
    with pytest.raises(ValidationError):
        events[1].text = "other"  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    ("model", "values"),
    [
        (SpokenClause, {"text": "", "language": "en"}),
        (SpokenClause, {"text": "x", "language": "fr"}),
        (ToolEnded, {"call_id": "c", "tool": "t", "ok": True, "ms": -1}),
        (ProgressDue, {"tool": "t", "key": "Searching", "language": "en"}),
        (ModelReplied, {"model": "m", "first_token_s": float("inf")}),
        (TalkerCall, {"call_id": "call 1", "caller": {"subject": "x"}, "language": "en"}),
        (ReplyDone, {"reason": "x"}),
    ],
)
def test_a_wrong_value_is_refused(model: type[Any], values: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        model.model_validate(values)


def test_the_reply_runs_in_the_sessions_cancel_scope_on_the_calls_clock() -> None:
    """The loop's behaviour: test_talker.py and test_talker_tools.py beside this file."""
    clock = FakeClock()
    scope: ReplyScope = CancelScope(name="reply-1", clock=clock)
    settings = VoiceSettings(env="test")
    chat = ChatTalker(
        AGENT,
        model=ScriptedLLM([]),
        runner=ToolRunner([]),
        settings=settings,
        call=CALL,
        clock=clock,
    )
    talker: Talker = chat
    assert chat.clock is clock
    stream = talker.reply(TalkerTurn(turn_id=0, words="hello"), scope=scope)
    assert isinstance(stream, AsyncIterator)  # nothing runs before it is iterated
    assert not scope.cancelled


def test_the_prompt_is_composed() -> None:
    """Its behaviour: test_prompt.py beside this file."""
    assert "Answer briefly." in render_prompt(AGENT, "en")
    assert "Today is 2026-11-06." in compose_prompt(AGENT, language="en", today=date(2026, 11, 6))

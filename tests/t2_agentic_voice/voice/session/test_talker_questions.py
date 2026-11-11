"""The question limit as a call plays the talker's reply (agent/turn.py's limit, D-085;
voice/session/talker_play.py): the library's `ChatTalker` on a fake chat model, in a session on
the fake session I/O. A reply that asks two questions is said up to its first: the caption, the
heard history, `AgentSpeechEnded.text` and the next turn's request hold only what was said, and
no notice is said in place of the rest. An action's read-back after a talker's question is said
whole, its closing question too: the session's own lines neither count nor stop. The log line
`talker_reply_stopped` holds the call, the turn, the reason and how many clauses went unsaid,
never a word of the reply."""

from __future__ import annotations

import asyncio
import dataclasses
import logging
from typing import Annotated

import pytest
from pydantic import BaseModel, Field
from t2_agentic_voice.actions.action import ActionContext, action
from t2_agentic_voice.actions.action_runner import ActionRunner
from t2_agentic_voice.actions.memory_outbox import MemoryOutbox
from t2_agentic_voice.actions.runner import ToolRunner
from t2_agentic_voice.actions.tools import tool
from t2_agentic_voice.agent.talker import ChatTalker, TalkerCall
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.events import AgentSpeechEnded
from t2_agentic_voice.domain.action_declaration import Claims, ReadBack, Say
from t2_agentic_voice.domain.declaration import Language, VoiceAgent
from t2_agentic_voice.voice.session.call import CallSession

from tests.leaks import holding, shown
from tests.t2_agentic_voice.agent.chat_support import FakeChat, Step, call, calls, said
from tests.t2_agentic_voice.session_fakes import FakeSessionIO
from tests.t2_agentic_voice.voice.session.session_support import captions, greeted, play, speaks
from tests.t2_agentic_voice.voice.session.talker_support import talked

ENGLISH = Language.english(greeting="Welcome to the test line")
TWO = "Is it urgent? Is it blocking your work? Tell me more."
SUMMARY = "my made up laptop will not start"


class OpenRequest(BaseModel):
    summary: Annotated[str, Field(min_length=1, max_length=120)]


class RequestOpened(BaseModel):
    number: str


@tool(description="Find a made-up help page.")
async def find_page(query: str) -> dict[str, str]:
    return {"found": "a made-up page"}


@action(
    description="Open a made-up help desk request.",
    read_back=ReadBack({"en": ("I'll open a request about: {summary}.", "Shall I send it?")}),
    done=Say(en="Done, your request number is {number:id}."),
    claims=Claims({"en": ["opened your request"]}),
)
async def open_request(ctx: ActionContext, draft: OpenRequest) -> RequestOpened:
    return RequestOpened(number="4521")


AGENT = VoiceAgent(
    name="talker-test", languages=[ENGLISH], instructions="Answer briefly.", tools=[find_page]
)
ACTING = VoiceAgent(
    name="talker-test", languages=[ENGLISH], instructions="Answer briefly.", tools=[open_request]
)


def _call(
    settings: VoiceSettings, *entries: list[Step], acts: bool = False
) -> tuple[FakeSessionIO, CallSession, FakeChat]:
    """A session of `AGENT` (or `ACTING`, with its action's runner) whose talker is the
    library's own, on a fake chat model that plays `entries`."""
    agent = ACTING if acts else AGENT
    io = FakeSessionIO(settings, agent=agent)
    model = FakeChat(*entries)
    talker = ChatTalker(
        agent,
        model=model,
        runner=ToolRunner([] if acts else [find_page]),
        settings=settings,
        call=TalkerCall(call_id=io.setup.call_id, caller=io.setup.caller, language="en"),
        clock=io.clock,
        actions=ActionRunner([open_request], outbox=MemoryOutbox()) if acts else None,
    )
    io.setup = dataclasses.replace(io.setup, talker=talker)
    session = CallSession(io.setup, io.commands)
    io.attach(session)
    return io, session, model


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


def test_everything_the_call_holds_of_the_reply_is_what_was_said(settings: VoiceSettings) -> None:
    io, session, model = _call(settings, said(TWO), said("Thanks, I have noted it."))
    _run(io, "My laptop will not start.", "Yes, very urgent.")
    assert [c.text for c in captions(io) if c.reply_id == 1] == ["Is it urgent?"]
    assert [s.text for s in speaks(io, 1)] == ["Is it urgent?"]  # no notice in its place
    [reply] = [r for r in session.history.replies() if r.turn_id == 0]
    assert [clause.text for clause in reply.clauses] == ["Is it urgent?"]
    [spoken] = [e for e in io.emitted if isinstance(e, AgentSpeechEnded) and e.turn_id == 0]
    assert spoken.text == "Is it urgent?"
    sent = " ".join(m.content for m in model.requests[1].messages)
    assert "Is it urgent?" in sent
    assert "blocking" not in sent and "Tell me more" not in sent


@pytest.mark.parametrize(
    "before", ["Is it the office laptop? ", "Is it the office laptop? Is it urgent? "]
)
def test_a_read_back_after_a_talkers_question_is_said_whole(
    settings: VoiceSettings, before: str
) -> None:
    io, _, _ = _call(
        settings, calls(call("open_request", summary=SUMMARY), before=before), acts=True
    )
    _run(io, f"please open a request, {SUMMARY}")
    [spoken] = [e for e in io.emitted if isinstance(e, AgentSpeechEnded) and e.turn_id == 0]
    assert spoken.text == (
        f"Is it the office laptop? I'll open a request about: {SUMMARY}. Shall I send it?"
    )


def test_the_log_line_holds_counts_only(
    settings: VoiceSettings, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG, logger="t2_agentic_voice")
    io, _, _ = _call(settings, said(TWO))
    _run(io, "My laptop will not start.")
    [record] = [r for r in caplog.records if r.getMessage() == "talker_reply_stopped"]
    fields = dict(record.fields)  # type: ignore[attr-defined]
    assert fields == {
        "call_id": "call-1",
        "turn_id": 0,
        "reason": "question_limit",
        "unsaid_clauses": 2,
    }
    surfaces = shown(caplog=caplog)
    for value in ("Is it urgent", "blocking", "Tell me more", "My laptop"):
        assert holding(value, surfaces) == [], value

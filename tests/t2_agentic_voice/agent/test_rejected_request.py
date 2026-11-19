"""A request the provider rejected, sent once more (agent/turn_answer.py's `requested` under
`llm.retry_rejected`, D-132; the owner's call of 2026-11-19, where Groq refused a request whose
tool call the model wrote malformed, `tool_use_failed`, and the caller heard the error notice).

- **Off, the default**: the reply raises the ProviderError after one request, as before (GP-18).
- **On**: a request rejected before any clause of it was given is sent once more, rebuilt with a
  new first line, the same messages and tools, nothing of the first said or run (its text held,
  its tool call), logged by its kind; each request of a turn at most once, so one rejected twice
  ends the reply with the error, and a later request of the turn may be sent again too; a
  rejection after a clause was said, or another kind of failure, ends the reply as before; the
  settings name it, off, and refuse a value that is no bool."""

from __future__ import annotations

import logging

import pytest
from pydantic import ValidationError
from t2_agentic_voice.actions.tools import tool
from t2_agentic_voice.agent.talker import SpokenClause, TalkerEvent
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.conversation import TalkerTurn
from t2_agentic_voice.core.errors import ProviderError
from t2_agentic_voice.core.settings.llm import LlmSettings
from t2_agentic_voice.domain.ports.chat_model import TextDelta

from tests.t2_agentic_voice.agent.chat_support import FakeChat, Step, call, calls, kinds, said
from tests.t2_agentic_voice.agent.chat_support import reply as replied
from tests.t2_agentic_voice.agent.chat_support import talker as talker_of

TURN = TalkerTurn(turn_id=1, words="Any flights to Jeddah tomorrow?", language="en")
DONE = "The 8:15 is the cheapest."


def _rejected() -> ProviderError:
    return ProviderError(
        "rejected", False, details={"error": "stream_error", "code": "tool_use_failed"}
    )


@tool(description="Do a made-up quick search.")
async def quick() -> dict[str, bool]:
    return {"ok": True}


def _settings(on: bool) -> VoiceSettings:
    return VoiceSettings(env="test", llm=LlmSettings(retry_rejected=on))


def _spoken(events: list[TalkerEvent]) -> list[str]:
    return [event.text for event in events if isinstance(event, SpokenClause)]


def _reply(model: FakeChat, on: bool) -> list[TalkerEvent]:
    return replied(talker_of(model, quick, settings=_settings(on)), TURN)


# The rejected request: some text held (no sentence's end yet), a tool call, then the refusal.
REJECTED: list[Step] = [TextDelta(text="Let me see"), call("quick"), _rejected()]


def test_off_a_rejected_request_ends_the_reply_with_the_error() -> None:
    model = FakeChat(REJECTED)
    with pytest.raises(ProviderError) as raised:
        _reply(model, on=False)
    assert raised.value.kind == "rejected" and len(model.requests) == 1


def test_on_a_rejected_request_is_sent_once_more_with_nothing_of_it_kept(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG, logger="t2_agentic_voice")
    model = FakeChat(REJECTED, calls(call("quick")), said(DONE))
    events = _reply(model, on=True)
    assert _spoken(events) == [DONE] and kinds(events)[-1] == "ReplyDone"
    assert kinds(events).count("ToolEnded") == 1  # the rejected request's call never ran
    first, again, after = model.requests
    assert again.messages[1:] == first.messages[1:] and again.tools == first.tools
    head, rest = first.messages[0].content.split("\n", 1)
    assert again.messages[0].content.split("\n", 1)[1] == rest  # the same prompt
    assert again.messages[0].content.split("\n", 1)[0] != head  # its first line new
    assert kinds(events)[:2] == ["ModelRequested", "ModelRequested"]
    [record] = [r for r in caplog.records if r.getMessage() == "talker_request_sent_again"]
    assert dict(record.fields)["kind"] == "rejected"  # type: ignore[attr-defined]
    assert after.tools  # the next request is the turn's second, as without the refusal


def test_on_a_request_rejected_twice_ends_the_reply_with_the_error() -> None:
    model = FakeChat(REJECTED, [_rejected()])
    with pytest.raises(ProviderError) as raised:
        _reply(model, on=True)
    assert raised.value.kind == "rejected" and len(model.requests) == 2


def test_on_each_request_of_the_turn_may_be_sent_once_more() -> None:
    model = FakeChat(REJECTED, calls(call("quick")), [_rejected()], said(DONE))
    events = _reply(model, on=True)
    assert _spoken(events) == [DONE] and len(model.requests) == 4
    assert kinds(events).count("ModelRequested") == 4


def test_on_a_rejection_after_a_clause_was_said_ends_the_reply() -> None:
    model = FakeChat([TextDelta(text="Sure. "), TextDelta(text="One mo"), _rejected()])
    with pytest.raises(ProviderError):
        _reply(model, on=True)  # "Sure." was said: the session says the notice after it
    assert len(model.requests) == 1


@pytest.mark.parametrize("kind", ["timeout", "server_error", "connection_lost"])
def test_on_another_failure_ends_the_reply_as_before(kind: str) -> None:
    model = FakeChat([TextDelta(text="Let me"), ProviderError(kind, True)])  # type: ignore[arg-type]
    with pytest.raises(ProviderError) as raised:
        _reply(model, on=True)
    assert raised.value.kind == kind and len(model.requests) == 1


def test_the_setting_is_off_by_default_and_takes_only_a_bool() -> None:
    assert LlmSettings().retry_rejected is False
    assert LlmSettings(retry_rejected=True).retry_rejected is True
    with pytest.raises(ValidationError):
        LlmSettings(retry_rejected="sometimes")  # type: ignore[arg-type]

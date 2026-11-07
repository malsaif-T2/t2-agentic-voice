"""The talker's loop (agent/talker.py, agent/turn.py; plan 006): a turn with no tool in one
request, its clauses given as soon as each is whole, on the call's clock; the model's settings
on the request; the output guard's rule B on every clause, by `guard.on_block`; a model's failure
ending the reply after what was given; a cancel of the reply's scope stopping the model at once;
and the reply language per turn, Saudi, MSA and English in one call."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import pytest
from t2_agentic_voice.agent.context import BLOCKED
from t2_agentic_voice.agent.prompt import LANGUAGE_SECTIONS, MSA_SECTION
from t2_agentic_voice.agent.talker import (
    ClauseBlocked,
    ModelReplied,
    ModelRequested,
    ReplyDone,
    SpokenClause,
    TalkerEvent,
)
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.conversation import (
    Conversation,
    PastTurn,
    TalkerTurn,
)
from t2_agentic_voice.core.errors import ProviderError
from t2_agentic_voice.core.settings.guard import GuardSettings
from t2_agentic_voice.core.settings.llm import LlmSettings
from t2_agentic_voice.domain.ports.chat_model import TextDelta, Usage
from t2_agentic_voice.voice.session.scope import CancelScope

from tests.leaks import holding, shown
from tests.t2_agentic_voice.agent.chat_support import (
    HOLD,
    FakeChat,
    kinds,
    reply,
    said,
    settle,
    talker,
)
from tests.t2_agentic_voice.fakes import FakeClock

TURN = TalkerTurn(turn_id=1, words="How do I reset my password?", language="en")


def test_a_turn_with_no_tool_is_one_request_its_clauses_streamed() -> None:
    model = FakeChat(said("Open the portal, ", "then choose Forgot", " password. Done."))
    events = reply(talker(model), TURN)
    assert events == [
        ModelRequested(model="openai/gpt-oss-120b"),
        SpokenClause(text="Open the portal,", language="en"),
        SpokenClause(text="then choose Forgot password.", language="en"),
        SpokenClause(text="Done.", language="en"),
        ModelReplied(
            model="openai/gpt-oss-120b",
            usage=Usage(input_tokens=20, output_tokens=8),
            first_token_s=0.0,
        ),
        ReplyDone(),
    ]
    [request] = model.requests
    assert [m.role for m in request.messages] == ["system", "user"]
    assert request.messages[-1].content == "How do I reset my password?"
    assert model.closed == 1


def test_each_clause_is_given_as_soon_as_it_is_whole_while_the_model_still_writes() -> None:
    model = FakeChat([TextDelta(text="First open it. "), HOLD, TextDelta(text="Then reset.")])

    async def steps(task: Any, events: list[TalkerEvent], scope: CancelScope, clock: Any) -> None:
        await settle()
        assert events[-1] == SpokenClause(text="First open it.", language="en")
        assert model.release is not None
        model.release.set()

    events = reply(talker(model), TURN, steps=steps)
    assert kinds(events)[-3:] == ["SpokenClause", "ModelReplied", "ReplyDone"]


def test_the_first_token_is_timed_on_the_calls_clock() -> None:
    clock = FakeClock()
    model = FakeChat([HOLD, TextDelta(text="Sure.")])

    async def steps(task: Any, events: list[TalkerEvent], scope: CancelScope, used: Any) -> None:
        await settle()
        await clock.advance(0.35)
        assert model.release is not None
        model.release.set()

    events = reply(talker(model, clock=clock), TURN, steps=steps)
    [replied] = [e for e in events if isinstance(e, ModelReplied)]
    assert replied.first_token_s == pytest.approx(0.35)


@pytest.mark.parametrize(
    ("model_name", "effort"),
    [("openai/gpt-oss-20b", "medium"), ("llama-3.3-70b-versatile", None)],
)
def test_the_request_carries_the_models_settings(model_name: Any, effort: str | None) -> None:
    llm = LlmSettings(model=model_name, reasoning_effort="medium", max_output_tokens=300)
    model = FakeChat(said("Sure."))
    reply(talker(model, settings=VoiceSettings(env="test", llm=llm)), TURN)
    [request] = model.requests
    assert (request.model, request.reasoning_effort, request.max_output_tokens) == (
        model_name,
        effort,
        300,
    )


def test_a_model_failure_ends_the_reply_after_the_clauses_given() -> None:
    """The session says the `error` notice: the reply raises the ProviderError, no ReplyDone."""
    failure = ProviderError("server_error", True)
    model = FakeChat([TextDelta(text="Open the portal. "), TextDelta(text="Then "), failure])
    seen: list[TalkerEvent] = []

    async def steps(task: Any, events: list[TalkerEvent], scope: CancelScope, clock: Any) -> None:
        await settle()
        seen.extend(events)

    with pytest.raises(ProviderError) as raised:
        reply(talker(model), TURN, steps=steps)
    assert raised.value is failure
    assert kinds(seen) == ["ModelRequested", "SpokenClause"]
    assert model.closed == 1


def test_a_cancel_of_the_scope_stops_the_model_at_once() -> None:
    model = FakeChat([TextDelta(text="Open the portal. "), HOLD, TextDelta(text="Never said.")])

    async def steps(task: Any, events: list[TalkerEvent], scope: CancelScope, clock: Any) -> None:
        await settle()
        await scope.cancel()
        assert task.cancelled() and model.closed == 1

    events = reply(talker(model), TURN, steps=steps)
    assert kinds(events) == ["ModelRequested", "SpokenClause"]  # no ReplyDone


def test_an_id_with_no_evidence_is_blocked_and_drops_the_rest_of_the_reply() -> None:
    model = FakeChat(said("Sure. Your request number is 4521. It is open."))
    chat = talker(model)
    events = reply(chat, TURN)
    assert [e for e in events if isinstance(e, SpokenClause | ClauseBlocked)] == [
        SpokenClause(text="Sure.", language="en"),
        ClauseBlocked(text="Your request number is 4521.", language="en", unsupported=("4521",)),
    ]
    assert kinds(events)[-2:] == ["ModelReplied", "ReplyDone"] and model.closed == 1
    model.entries.append(said("Sorry."))
    reply(
        chat,
        TalkerTurn(
            turn_id=2,
            words="and?",
            conversation=Conversation(
                turns=(PastTurn(turn_id=1, words=TURN.words, fate="answered", reply_id=1),)
            ),
        ),
    )
    notes = [m.content for m in model.requests[-1].messages if m.role == "system"][1:]
    assert notes == [BLOCKED]  # the developer note, in the history after the turn


def test_with_drop_clause_only_the_blocked_clause_goes() -> None:
    settings = VoiceSettings(env="test", guard=GuardSettings(on_block="drop_clause"))
    model = FakeChat(said("Your number is 4521. It is open."))
    events = reply(talker(model, settings=settings), TURN)
    assert [type(e).__name__ for e in events if isinstance(e, SpokenClause | ClauseBlocked)] == [
        "ClauseBlocked",
        "SpokenClause",
    ]


def test_the_callers_own_words_are_evidence() -> None:
    turn = TalkerTurn(turn_id=1, words="Is ticket four five two one closed?", language="en")
    model = FakeChat(said("Ticket 4521 is closed."))
    events = reply(talker(model), turn)
    assert SpokenClause(text="Ticket 4521 is closed.", language="en") in events


def test_the_current_year_passes_with_no_evidence() -> None:
    model = FakeChat(said("Since 2026, it is free."))  # the fake clock's wall is in 2026
    assert SpokenClause(text="Since 2026,", language="en") in reply(talker(model), TURN)


def _system(model: FakeChat, index: int) -> str:
    return model.requests[index].messages[0].content


def test_the_reply_language_follows_each_turn_in_one_call() -> None:
    """Saudi, MSA and English turns in one Saudi call: each reply in the turn's language, the
    team's instructions for it, and the language section of its register: the Saudi turn's asks
    for the Saudi register unless the caller speaks MSA, the MSA turn's for MSA."""
    model = FakeChat(said("أبشر."), said("حسنا."), said("Sure."), said("Sure."))
    chat = talker(model, language="ar-SA")
    turns = [
        TalkerTurn(turn_id=1, words="ابي اغير كلمة السر", language="ar"),
        TalkerTurn(turn_id=2, words="أريد تغيير كلمة المرور", language="ar"),
        TalkerTurn(turn_id=3, words="How do I change my password?", language="en"),
        TalkerTurn(turn_id=4, words="How do I change my password?", language="ar"),  # Q9
    ]
    languages = []
    for turn in turns:
        events = reply(chat, turn)
        languages.append([e.language for e in events if isinstance(e, SpokenClause)])
    assert languages == [["ar-SA"], ["ar-SA"], ["en"], ["en"]]
    assert "Made-up Saudi instructions." in _system(model, 0)
    assert _system(model, 0).endswith(LANGUAGE_SECTIONS["ar-SA"])
    assert _system(model, 1).endswith(MSA_SECTION)
    assert "Made-up English instructions." in _system(model, 2)
    assert _system(model, 3).endswith(LANGUAGE_SECTIONS["en"])


def test_an_msa_call_replies_in_its_own_tag() -> None:
    model = FakeChat(said("حسنا."))
    events = reply(
        talker(model, language="ar"), TalkerTurn(turn_id=1, words="مرحبا", language="ar")
    )
    assert [e.language for e in events if isinstance(e, SpokenClause)] == ["ar"]
    assert "Made-up MSA instructions." in _system(model, 0)


def test_a_reply_that_says_nothing_still_ends() -> None:
    """It ends as any other: the session says the `error` notice for a reply with no clause."""
    model = FakeChat(said(" "))
    assert kinds(reply(talker(model), TURN)) == ["ModelRequested", "ModelReplied", "ReplyDone"]


def test_an_answer_cut_at_the_models_limit_is_logged_by_its_model_never_its_text(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A request that ends at `max_output_tokens` (`length`, gpt-oss's reasoning filling it):
    its words so far are still given, and a warning names the model and the finish reason."""
    caplog.set_level(logging.DEBUG, logger="t2_agentic_voice")
    model = FakeChat(said("To reset your password,", " open", finish="length"))
    events = reply(talker(model), TURN)
    assert [e.text for e in events if isinstance(e, SpokenClause)] == [
        "To reset your password,",
        "open",
    ]
    [record] = [r for r in caplog.records if r.getMessage() == "talker_reply_truncated"]
    assert record.levelno == logging.WARNING
    fields = record.fields  # type: ignore[attr-defined]
    assert (fields["model"], fields["finish_reason"], fields["turn_id"]) == (
        "openai/gpt-oss-120b",
        "length",
        1,
    )
    assert holding("reset your password", shown(caplog=caplog)) == []


def test_the_talker_reads_no_time_but_its_clock() -> None:
    """A fake clock on another day dates the prompt: never the system's date."""
    clock = FakeClock()
    asyncio.run(clock.advance(86_400 * 30))
    model = FakeChat(said("Sure."))
    reply(talker(model, clock=clock), TURN)
    assert f"Today is {clock.wall().date().isoformat()}." in _system(model, 0)


def test_the_clauses_after_a_blocked_one_in_the_same_piece_are_dropped_too() -> None:
    model = FakeChat(said("Your number is 4521. Then open it. And wait."))
    events = reply(talker(model), TURN)
    assert kinds(events) == ["ModelRequested", "ClauseBlocked", "ModelReplied", "ReplyDone"]

"""A chat model's word on an answer to an action's read-back that the yes rule's lists leave
unplaced (voice/session/yes_ask.py, yes_turns.py; D-082), on the real yes rule and its words and
a fake chat model: only for an agent that asks and only for unplaced words, one request a turn
holding the read-back and the words; its word decided by the rule (`judged`) and carried out as
any answer is, told `by="model"`, its no on a question reaching the talker declined as a no
(the owner's answer of 2026-11-11); a timeout on the call's clock, a failure and a word that is
none asked again; a newer answer, the client's stop, the call's end and a stop word that
declined the read-back each leave a request still in flight deciding nothing; the request
counted in the call's usage, its outcome logged by kind, never the words."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.conversation import DeclinedAction, DeclineKind
from t2_agentic_voice.core.errors import ProviderError
from t2_agentic_voice.core.events import ConfirmationAnswered
from t2_agentic_voice.domain.consent_check import TIMEOUT_S, is_consent_check
from t2_agentic_voice.domain.ports.chat_model import Usage
from t2_agentic_voice.domain.text.invisible import provider_text
from t2_agentic_voice.domain.words import PRESET_WORDS
from t2_agentic_voice.testing.llm_fakes import Pause, ScriptedLLM, ScriptStep
from t2_agentic_voice.voice.session.call import CallSession

from tests.leaks import holding, shown
from tests.t2_agentic_voice.session_fakes import FakeSessionIO
from tests.t2_agentic_voice.voice.session.read_back_support import ASKED, PLAN
from tests.t2_agentic_voice.voice.session.session_support import emitted, report, speaks, turn
from tests.t2_agentic_voice.voice.session.talker_support import (
    AGENT,
    MODEL,
    FakeTalker,
    settle,
    talked,
)
from tests.t2_agentic_voice.voice.session.yes_support import (
    FakeJobs,
    confirm_call,
    read_back_played,
)

ASKS = AGENT.model_copy(update={"ask_on_unlisted_answers": True})
UNLISTED = "go for it"  # words on none of the lists
QUESTION_WORDS = "How do I reset my password?"  # a question about something else
SENDING = [provider_text(PLAN.sending.spoken)]
ASKED_AGAIN = [provider_text(ASKED)]
STOP_WORD = PRESET_WORDS["en"].stop[0]


def _call(
    settings: VoiceSettings, *entries: tuple[ScriptStep, ...], agent: Any = ASKS
) -> tuple[FakeSessionIO, CallSession, FakeTalker, ScriptedLLM, FakeJobs]:
    """A confirming call of `agent`, its read-back `PLAN`, its chat model `entries` scripts."""
    llm, jobs = ScriptedLLM(entries), FakeJobs()
    io, session, talker = confirm_call(settings, jobs, agent=agent, overlap_model=llm)
    llm.clock = io.clock
    return io, session, talker, llm, jobs


def _answered(io: FakeSessionIO) -> list[tuple[int | None, str, str]]:
    return [(e.turn_id, e.decision, e.by) for e in emitted(io, ConfirmationAnswered)]


def _said(io: FakeSessionIO, reply_id: int) -> list[str]:
    return [speak.text for speak in speaks(io, reply_id)]


def _messages(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [record.getMessage() for record in caplog.records]


def _dropped(caplog: pytest.LogCaptureFixture) -> list[str]:
    """Why each request still in flight decided nothing, as logged."""
    found = [r for r in caplog.records if r.getMessage() == "yes_model_dropped"]
    return [getattr(r, "fields", {})["why"] for r in found]


def test_unlisted_words_are_put_to_the_model_once_and_its_send_confirms(
    settings: VoiceSettings, caplog: pytest.LogCaptureFixture
) -> None:
    usage = Usage(input_tokens=90, output_tokens=3)
    io, _session, talker, llm, jobs = _call(settings, ScriptedLLM.reply("send", usage=usage))

    async def drive() -> None:
        await read_back_played(io)
        await talked(io, 1, UNLISTED)
        await io.ending()
        await io.close()

    asyncio.run(drive())
    (request,) = llm.requests  # one request a turn
    assert is_consent_check(request)
    assert json.loads(request.messages[1].content) == {
        "read_back": PLAN.summary.text,
        "question": PLAN.question.text,
        "answer": UNLISTED,
    }
    assert _answered(io) == [(1, "yes", "model")]
    (run,) = jobs.runs
    assert (run.confirmed.turn_id, run.confirmed.words) == (1, UNLISTED)
    assert _said(io, 2) == SENDING
    assert [t.turn_id for t in talker.turns] == [0]  # the talker never heard the yes
    chat = {u.model: u for u in report(io).usage}[MODEL]
    assert (chat.requests, chat.input_tokens, chat.output_tokens) == (1, 90, 3)
    assert "yes_model_answered" in _messages(caplog)
    assert holding(UNLISTED, shown(caplog=caplog)) == []  # GP-19


@pytest.mark.parametrize(
    ("word", "decision", "kind"),
    [
        ("yes", "yes", None),  # agreement, once the question ended
        ("no", "declined", "no"),
        ("change", "correction", "correction"),
        ("unclear", "asked_again", None),
        ("maybe", "asked_again", None),  # a word that is none of the five
    ],
)
def test_the_models_word_is_the_yes_rules_and_is_carried_out_as_any_answer(
    settings: VoiceSettings, word: str, decision: str, kind: DeclineKind | None
) -> None:
    io, session, talker, _llm, jobs = _call(settings, ScriptedLLM.reply(word))

    async def drive() -> None:
        await read_back_played(io)
        await talked(io, 1, UNLISTED)

    asyncio.run(drive())
    assert _answered(io) == [(1, decision, "model")]
    assert len(jobs.runs) == (1 if decision == "yes" else 0)
    if kind is not None:
        (handed,) = [t for t in talker.turns if t.turn_id == 1]
        assert handed.declined is not None and handed.declined.kind == kind
    if decision == "asked_again":
        assert _said(io, 2) == ASKED_AGAIN and session._confirming.active


def test_a_question_the_model_calls_no_reaches_the_talker_declined_and_sends_nothing(
    settings: VoiceSettings,
) -> None:
    """The owner's answer of 2026-11-11 (D-082): a question in answer to the read-back drops it,
    and the talker answers it in its own words; nothing is asked again or sent."""
    io, session, talker, llm, jobs = _call(settings, ScriptedLLM.reply("no"))

    async def drive() -> None:
        await read_back_played(io)
        await talked(io, 1, QUESTION_WORDS)

    asyncio.run(drive())
    (request,) = llm.requests
    assert json.loads(request.messages[1].content)["answer"] == QUESTION_WORDS
    assert _answered(io) == [(1, "declined", "model")]
    (handed,) = [t for t in talker.turns if t.turn_id == 1]
    assert handed.declined == DeclinedAction(action=PLAN.action, kind="no", words=QUESTION_WORDS)
    assert jobs.runs == [] and not session._confirming.active
    assert _said(io, 2) != ASKED_AGAIN  # the talker's answer, never the ask-again line


def test_listed_words_ask_nothing(settings: VoiceSettings) -> None:
    io, _session, _talker, llm, jobs = _call(settings)

    async def drive() -> None:
        await read_back_played(io)
        await talked(io, 1, "yes send it")

    asyncio.run(drive())
    assert llm.requests == []
    assert _answered(io) == [(1, "yes", "words")] and len(jobs.runs) == 1


def test_an_agent_that_does_not_ask_hears_unlisted_words_as_a_correction(
    settings: VoiceSettings,
) -> None:
    io, _session, talker, llm, jobs = _call(settings, agent=AGENT)

    async def drive() -> None:
        await read_back_played(io)
        await talked(io, 1, UNLISTED)

    asyncio.run(drive())
    assert llm.requests == []
    assert _answered(io) == [(1, "correction", "words")] and jobs.runs == []
    (handed,) = [t for t in talker.turns if t.turn_id == 1]
    assert handed.declined is not None and handed.declined.kind == "correction"


def test_a_request_that_times_out_on_the_calls_clock_is_asked_again(
    settings: VoiceSettings,
) -> None:
    io, session, _talker, _llm, jobs = _call(settings, (Pause(5.0), *ScriptedLLM.reply("send")))

    async def drive() -> None:
        await read_back_played(io)
        await talked(io, 1, UNLISTED)
        await io.clock.advance(TIMEOUT_S - 0.1)
        await settle()
        assert _answered(io) == [] and _said(io, 2) == []  # the caller waits, nothing said
        await io.clock.advance(0.2)
        await settle()

    asyncio.run(drive())
    assert TIMEOUT_S in io.clock.sleeps  # the call's clock
    assert _answered(io) == [(1, "asked_again", "model")]
    assert _said(io, 2) == ASKED_AGAIN and jobs.runs == [] and session._confirming.active


def test_a_request_that_fails_is_asked_again_logged_by_its_kind_alone(
    settings: VoiceSettings, caplog: pytest.LogCaptureFixture
) -> None:
    io, _session, _talker, _llm, jobs = _call(settings, (ProviderError("server_error", True),))

    async def drive() -> None:
        await read_back_played(io)
        await talked(io, 1, UNLISTED)

    asyncio.run(drive())
    assert _answered(io) == [(1, "asked_again", "model")] and jobs.runs == []
    (failed,) = [r for r in caplog.records if r.getMessage() == "yes_model_failed"]
    assert getattr(failed, "fields", {})["failure"] == "server_error"
    assert holding(UNLISTED, shown(caplog=caplog)) == []


def test_a_newer_answer_cancels_a_request_still_in_flight(
    settings: VoiceSettings, caplog: pytest.LogCaptureFixture
) -> None:
    late = (Pause(TIMEOUT_S - 0.1), *ScriptedLLM.reply("send"))
    io, session, talker, llm, jobs = _call(settings, late)

    async def drive() -> None:
        await read_back_played(io)
        await talked(io, 1, UNLISTED)
        await turn(io, 2, "no", audio_s=0.2)  # a listed no, before the model's word
        await settle()
        await io.clock.advance(5.0)
        await settle()

    asyncio.run(drive())
    assert len(llm.requests) == 1
    assert _answered(io) == [(2, "declined", "words")] and jobs.runs == []
    assert [t.turn_id for t in talker.turns] == [0, 2]
    assert _dropped(caplog) == ["cancel"]
    assert not session._confirming.active


def test_the_clients_stop_cancels_a_request_and_decides_nothing(
    settings: VoiceSettings, caplog: pytest.LogCaptureFixture
) -> None:
    io, _session, _talker, _llm, jobs = _call(settings, (Pause(1.0), *ScriptedLLM.reply("send")))

    async def drive() -> None:
        await read_back_played(io)
        await talked(io, 1, UNLISTED)
        await io.client({"v": 1, "type": "stop"})
        await settle()
        await io.clock.advance(5.0)
        await settle()

    asyncio.run(drive())
    assert _answered(io) == [] and jobs.runs == [] and speaks(io, 2) == []
    assert _dropped(caplog) == ["cancel"]


def test_the_calls_end_cancels_a_request_and_decides_nothing(
    settings: VoiceSettings, caplog: pytest.LogCaptureFixture
) -> None:
    io, _session, _talker, _llm, jobs = _call(settings, (Pause(1.0), *ScriptedLLM.reply("send")))

    async def drive() -> None:
        await read_back_played(io)
        await talked(io, 1, UNLISTED)
        await io.ending()
        await io.clock.advance(5.0)
        await settle()
        await io.close()

    asyncio.run(drive())
    assert _answered(io) == [] and jobs.runs == [] and speaks(io, 2) == []
    assert _dropped(caplog) == ["cancel"]


def test_a_late_word_after_a_stop_word_declined_the_read_back_decides_nothing(
    settings: VoiceSettings, caplog: pytest.LogCaptureFixture
) -> None:
    """The owner's stop ruling ends confirming; the model's word that lands after it is of a
    read-back no longer current."""
    io, session, talker, _llm, jobs = _call(settings, (Pause(1.0), *ScriptedLLM.reply("send")))

    async def drive() -> None:
        await read_back_played(io)
        await talked(io, 1, UNLISTED)
        await turn(io, 2, STOP_WORD, audio_s=0.2)
        await settle()
        await io.clock.advance(5.0)
        await settle()

    asyncio.run(drive())
    assert _answered(io) == [] and jobs.runs == []
    (handed,) = [t for t in talker.turns if t.turn_id == 2]
    assert handed.declined is not None and handed.declined.kind == "stopped"
    assert _dropped(caplog) == ["stale"]
    assert not session._confirming.active

"""Each turn's warm flag in the call (voice/session/talker_play.py, report.py, model_word.py):
whether its first chat request went out on a kept-alive connection (`ModelReplied`'s
`warm_connection`), kept on its record in the call's report and on its span, None when the chat
model does not say; and the session's own chat request logged with its flag, never its words."""

from __future__ import annotations

import asyncio
import logging

import pytest
from t2_agentic_voice.agent.talker import ModelReplied, ModelRequested, ReplyDone, SpokenClause
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.conversation import TalkerTurn
from t2_agentic_voice.core.logging import FIELDS
from t2_agentic_voice.testing.llm_fakes import ScriptedLLM

from tests.t2_agentic_voice.voice.session.overlap_ask_support import (
    TWO_WORDS,
    asking_call,
    over_the_reply,
)
from tests.t2_agentic_voice.voice.session.session_support import greeted, play, report
from tests.t2_agentic_voice.voice.session.talker_support import MODEL, Step, talked, talker_call


def _replied(warm: bool | None) -> ModelReplied:
    return ModelReplied(model=MODEL, first_token_s=0.3, warm_connection=warm)


def test_each_turns_record_and_span_keep_its_first_requests_flag(settings: VoiceSettings) -> None:
    flags: dict[int, list[bool | None]] = {0: [False, True], 1: [True], 2: [None]}

    def script(turn: TalkerTurn) -> list[Step]:
        requests: list[Step] = []
        for warm in flags[turn.turn_id]:  # a tool's round trip between two requests
            requests += [ModelRequested(model=MODEL), _replied(warm)]
        return [*requests, SpokenClause(text="Done.", language="en"), ReplyDone()]

    io, session, _talker = talker_call(settings, script)

    async def drive() -> None:
        await greeted(io)
        for turn_id in flags:
            await talked(io, turn_id, "How do I reset my password?", language="en")
            await play(io, turn_id + 1)
        await io.ending()
        await io.close()

    asyncio.run(drive())
    assert [t.warm_connection for t in report(io).turns] == [False, True, None]
    spans = [session._turns.turn(turn_id).outcome() for turn_id in flags]
    assert [span.get("turn.warm_connection") for span in spans] == [False, True, None]
    assert "turn.warm_connection" not in spans[2]


@pytest.mark.parametrize("warm", [None, False, True])
def test_the_sessions_own_request_is_logged_with_its_flag_and_no_words(
    settings: VoiceSettings, warm: bool | None, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)
    io, _session, _talker, llm = asking_call(settings, ScriptedLLM.reply("go_on"))
    if warm is not None:  # a chat model that says whether its connection is kept
        setattr(llm, "warm", lambda: warm)  # noqa: B010

    async def drive() -> None:
        await over_the_reply(io, TWO_WORDS)
        await io.turn_closed(1)
        await io.transcribed(1, TWO_WORDS, language="en")
        await io.ending()
        await io.close()

    asyncio.run(drive())
    (sent,) = [r for r in caplog.records if r.getMessage() == "model_word_sent"]
    fields = getattr(sent, FIELDS)
    assert (fields["asker"], fields["turn_id"]) == ("overlap", 1)
    assert fields["warm_connection"] is warm
    assert TWO_WORDS not in caplog.text

"""A chat model's word on an uncertain overlap (voice/session/overlap_ask.py; D-069, plan 006,
Q28), on the real rule and a fake chat model: `stop` stops the agent as new words and the turn
reaches the talker, and `go_on`, a word neither, a failure or a timeout leave the rule's verdict,
with exactly one `unduck` either way; a single word, a window, the rule's own stop and an agent
that does not ask for it send nothing; and the request is one of the call's chat requests. The
wait itself is test_overlap_ask_wait.py's."""

from __future__ import annotations

import asyncio

import pytest
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.errors import ProviderError
from t2_agentic_voice.core.events import Interrupted
from t2_agentic_voice.domain.ports.chat_model import Done, TextDelta, Usage
from t2_agentic_voice.testing.llm_fakes import Pause, ScriptedLLM
from t2_agentic_voice.voice.protocol import Unduck
from t2_agentic_voice.voice.session.commands import StopSpeaking

from tests.t2_agentic_voice.voice.session.overlap_ask_support import (
    ASKING,
    GO_ON,
    LISTENING,
    ONE_WORD,
    STOP,
    STOP_WORD,
    TWO_WORDS,
    asking_call,
    over_the_reply,
    two_clauses,
)
from tests.t2_agentic_voice.voice.session.overlap_support import overlap_part, two_step
from tests.t2_agentic_voice.voice.session.session_support import emitted, greeted, report, sent
from tests.t2_agentic_voice.voice.session.talker_support import (
    AGENT,
    MODEL,
    settle,
    talked,
    talker_call,
)


def test_the_model_saying_stop_stops_the_reply_as_new_words_and_the_talker_answers(
    settings: VoiceSettings,
) -> None:
    io, _session, talker, llm = asking_call(settings, STOP)

    async def drive() -> None:
        await over_the_reply(io, TWO_WORDS)
        assert io.commands.of(StopSpeaking) == [StopSpeaking(reply_id=1)]
        await io.turn_closed(1)
        await io.transcribed(1, TWO_WORDS, language="en")
        await settle()
        await io.ending()
        await io.close()

    asyncio.run(drive())
    (request,) = llm.requests
    assert (request.model, request.reasoning_effort, request.max_output_tokens) == (
        MODEL,
        "low",
        256,
    )
    assert "Open Settings first. Then press Reset." in request.messages[1].content
    assert TWO_WORDS in request.messages[1].content
    (stopped,) = emitted(io, Interrupted)
    assert (stopped.turn_id, stopped.kind, stopped.reason) == (0, "new_words", "model")
    assert [t.words for t in talker.turns] == ["How do I reset my password?", TWO_WORDS]
    assert talker.turns[1].cut_reply == 1
    assert len(sent(io, Unduck)) == 1


@pytest.mark.parametrize(
    "word",
    ["go_on", "maybe", "stop now"],
    ids=["go-on", "unclear", "not-one-word"],
)
def test_the_model_saying_go_on_or_something_unclear_leaves_the_rule(
    settings: VoiceSettings, word: str, caplog: pytest.LogCaptureFixture
) -> None:
    io, session, talker, _llm = asking_call(settings, ScriptedLLM.reply(word))

    async def drive() -> None:
        await over_the_reply(io, TWO_WORDS)
        await io.turn_closed(1)
        await io.transcribed(1, TWO_WORDS, language="en")
        await settle()
        await io.ending()
        await io.close()

    asyncio.run(drive())
    assert not io.commands.of(StopSpeaking)
    (went_on,) = emitted(io, Interrupted)
    assert (went_on.kind, went_on.reason) == ("false", "short_output")
    assert [t.turn_id for t in talker.turns] == [0]
    assert session._turns.turn(1).fate == "went_on"
    assert len(sent(io, Unduck)) == 1
    assert "overlap_model_answered" in [r.getMessage() for r in caplog.records]
    assert TWO_WORDS not in caplog.text


def test_a_model_that_fails_leaves_the_rule_logged_by_kind_alone(
    settings: VoiceSettings, caplog: pytest.LogCaptureFixture
) -> None:
    io, _session, _talker, _llm = asking_call(settings, (ProviderError("server_error", True),))

    async def drive() -> None:
        await over_the_reply(io, TWO_WORDS)
        await io.turn_closed(1)
        await io.transcribed(1, TWO_WORDS, language="en")
        await settle()
        await io.ending()
        await io.close()

    asyncio.run(drive())
    (went_on,) = emitted(io, Interrupted)
    assert (went_on.kind, went_on.reason) == ("false", "short_output")
    assert not io.commands.of(StopSpeaking)
    assert len(sent(io, Unduck)) == 1
    (failed,) = [r for r in caplog.records if r.getMessage() == "overlap_model_failed"]
    assert getattr(failed, "fields", {})["failure"] == "server_error"
    assert TWO_WORDS not in caplog.text


def test_a_model_that_times_out_on_the_calls_clock_leaves_the_rule(
    settings: VoiceSettings,
) -> None:
    io, _session, talker, _llm = asking_call(settings, (Pause(5.0), *STOP))

    async def drive() -> None:
        await over_the_reply(io, TWO_WORDS)
        await io.clock.advance(0.9)
        await settle()
        assert not sent(io, Unduck) and not emitted(io, Interrupted)  # the voice stays ducked
        await io.clock.advance(0.2)
        await settle()
        assert len(sent(io, Unduck)) == 1
        assert 1.0 in io.clock.sleeps  # the call's clock
        await io.turn_closed(1)
        await io.transcribed(1, TWO_WORDS, language="en")
        await settle()
        await io.ending()
        await io.close()

    asyncio.run(drive())
    (went_on,) = emitted(io, Interrupted)
    assert (went_on.kind, went_on.reason) == ("false", "short_output")
    assert not io.commands.of(StopSpeaking)
    assert [t.turn_id for t in talker.turns] == [0]


def test_too_few_words_is_asked_too(settings: VoiceSettings) -> None:
    """The rule's step 7, past its step 6: two words, one a listening sound, over 1.2 s."""
    io, _session, _talker, llm = asking_call(settings, GO_ON)
    words = f"{LISTENING} agent"

    async def drive() -> None:
        await over_the_reply(io, words, played_s=1.5)
        await settle()
        await io.turn_closed(1)
        await io.transcribed(1, words, language="en")
        await settle()
        await io.ending()
        await io.close()

    asyncio.run(drive())
    (request,) = llm.requests
    assert words in request.messages[1].content
    (went_on,) = emitted(io, Interrupted)
    assert (went_on.kind, went_on.reason) == ("false", "too_few_words")


def test_a_single_word_keeps_the_rule_and_asks_nothing(settings: VoiceSettings) -> None:
    io, _session, _talker, llm = asking_call(settings)

    async def drive() -> None:
        await over_the_reply(io, ONE_WORD)
        await io.turn_closed(1)
        await io.transcribed(1, ONE_WORD, language="en")
        await settle()
        await io.ending()
        await io.close()

    asyncio.run(drive())
    assert llm.requests == []
    (went_on,) = emitted(io, Interrupted)
    assert (went_on.kind, went_on.reason) == ("false", "short_output")


def test_a_window_is_never_asked_only_the_whole_overlap(settings: VoiceSettings) -> None:
    io, _session, _talker, llm = asking_call(settings, STOP)

    async def drive() -> None:
        await greeted(io)
        await talked(io, 0, "How do I reset my password?")
        await io.synthesizing(1, 0)
        await io.clause_queued(1, 0)
        await io.clock.advance(0.2)
        await io.turn_opened(1)
        await overlap_part(io, 1, TWO_WORDS, part="window", audio_s=0.75)
        await settle()
        assert llm.requests == []
        await overlap_part(io, 1, TWO_WORDS)
        await settle()
        assert len(llm.requests) == 1
        await io.ending()
        await io.close()

    asyncio.run(drive())


def test_the_rules_own_stop_is_not_asked(settings: VoiceSettings) -> None:
    io, _session, _talker, llm = asking_call(settings)

    async def drive() -> None:
        await over_the_reply(io, STOP_WORD)
        await io.ending()
        await io.close()

    asyncio.run(drive())
    assert llm.requests == []
    (stopped,) = emitted(io, Interrupted)
    assert (stopped.kind, stopped.reason) == ("stop", "stop_word")


def test_an_agent_that_does_not_ask_makes_no_request(settings: VoiceSettings) -> None:
    io, _session, _talker, llm = asking_call(settings, agent=AGENT)

    async def drive() -> None:
        await over_the_reply(io, TWO_WORDS)
        await io.turn_closed(1)
        await io.transcribed(1, TWO_WORDS, language="en")
        await settle()
        await io.ending()
        await io.close()

    asyncio.run(drive())
    assert llm.requests == []
    (went_on,) = emitted(io, Interrupted)
    assert (went_on.kind, went_on.reason) == ("false", "short_output")
    assert len(sent(io, Unduck)) == 1


def test_an_agent_that_asks_but_has_no_chat_model_keeps_the_rule(
    settings: VoiceSettings,
) -> None:
    io, _session, _talker = talker_call(two_step(settings), two_clauses, agent=ASKING)

    async def drive() -> None:
        await over_the_reply(io, TWO_WORDS)
        await io.turn_closed(1)
        await io.transcribed(1, TWO_WORDS, language="en")
        await settle()
        await io.ending()
        await io.close()

    asyncio.run(drive())
    (went_on,) = emitted(io, Interrupted)
    assert (went_on.kind, went_on.reason) == ("false", "short_output")
    assert len(sent(io, Unduck)) == 1


def test_the_request_is_counted_in_the_calls_usage(settings: VoiceSettings) -> None:
    usage = Usage(input_tokens=90, output_tokens=12)
    io, _session, _talker, _llm = asking_call(settings, ScriptedLLM.reply("go_on", usage=usage))

    async def drive() -> None:
        await over_the_reply(io, TWO_WORDS)
        await io.turn_closed(1)
        await io.transcribed(1, TWO_WORDS, language="en")
        await settle()
        await io.ending()
        await io.close()

    asyncio.run(drive())
    chat = {u.model: u for u in report(io).usage}[MODEL]
    assert (chat.requests, chat.input_tokens, chat.output_tokens) == (2, 120 + 90, 30 + 12)


def test_a_stream_that_gives_text_only_is_read_whole(settings: VoiceSettings) -> None:
    """A model's text may come in pieces, `go_on`'s underscore among them."""
    pieces = (
        TextDelta(text="go"),
        TextDelta(text="_"),
        TextDelta(text="on"),
        Done(finish_reason="stop"),
    )
    io, _session, _talker, _llm = asking_call(settings, pieces)

    async def drive() -> None:
        await over_the_reply(io, TWO_WORDS)
        await io.ending()
        await io.close()

    asyncio.run(drive())
    assert not io.commands.of(StopSpeaking)

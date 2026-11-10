"""An action's call end to end through `TextCall` (plan 007's integration; the design's 9.2): the
library's own talker on a fake model that calls the action as a tool, the session's own read-back
and confirming, the real yes rule, guard and interruption rule, and the real action runner over a
`MemoryOutbox`, in English and in Saudi Arabic (action_call_support.py). A yes over the summary
confirms nothing and the summary plays on; a bare yes over the closing question is asked again;
a yes with a send word once the question played confirms, the sending line then the outcome
said, one write. A stop or pause word over the read-back, or a stop said whole while
confirming, sends nothing, the talker asked what to change with its draft in view, and only a
new read-back, once the model calls the action again, can earn a yes. A repeat request while
confirming, whole or over the closing question, says the read-back again, and only a yes after
that reading confirms. The turn holds the action call with the arguments the model wrote."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from t2_agentic_voice.core.events import ActionCompleted, ConfirmationAnswered
from t2_agentic_voice.domain.words import PRESET_WORDS, rule_form
from t2_agentic_voice.domain.yes_words import PRESET_CONSENT
from t2_agentic_voice.testing.text_call import TextCall
from t2_agentic_voice.testing.text_read_back import readings, summary_played_at
from t2_agentic_voice.testing.text_watch import plans_of

from tests.t2_agentic_voice.testing.action_call_support import (
    ACTION,
    ENGLISH,
    ROOM,
    SAUDI,
    SETTLE_S,
    Backend,
    Words,
    agent_of,
    asked_with,
    call_action,
    drafts_in,
    events,
    model,
    note,
    say,
    told,
)

LANGUAGES = [ENGLISH, SAUDI]


def _ids(words: Words) -> str:
    return words.tag


def test_each_languages_words_are_the_presets() -> None:
    for words in LANGUAGES:
        consent, commands = PRESET_CONSENT[words.code], PRESET_WORDS[words.code]
        assert rule_form(words.yes) in consent.yes and rule_form(words.send) in consent.send
        assert words.stop in commands.stop and words.wait in commands.wait
        assert words.repeat in commands.repeat and words.no in commands.no


@pytest.mark.parametrize("words", LANGUAGES, ids=_ids)
def test_a_draft_is_written_once_after_a_yes_with_a_send_word_heard_once_it_played(
    words: Words,
) -> None:
    backend = Backend()
    llm = model({words.request: call_action(words.note)})

    async def scene() -> tuple[str, ...]:
        async with TextCall(agent_of(backend), llm=llm, language=words.tag) as call:
            asked = await call.user(words.request)
            over = await call.user(words.yes_send, during="read_back")
            over.expect.no_action()
            assert backend.writes == 0 and over.fate == "went_on"
            asked.expect.read_back(contains=ROOM, room=ROOM, note=words.note)
            bare = await call.user(words.yes, during="closing_question")
            bare.expect.asked_again()
            bare.expect.no_action()
            assert backend.writes == 0
            await call.advance(10.0)
            sent = await call.user(words.yes_send)
            await call.advance(SETTLE_S)
            sent.expect.confirmed(ACTION, room=ROOM, note=words.note)
            sent.expect.action_ended(ACTION, "done")
            sent.expect.action_completed(ACTION)
            _, session = call._parts()
            (plan,) = plans_of(call._watched)
            (reading,) = readings(session.playback, [plan])
            assert reading.summary and reading.question  # the summary, then its question
            assert max(reading.summary) < min(reading.question)
            assert summary_played_at(session.playback, reading) is not None  # it played on
            assert backend.writes == 1 and backend.numbers() == ["5101"]
            assert len(await call.outbox.entries(action=ACTION)) == 1
            done = [e for e in events(call) if isinstance(e, ActionCompleted)]
            assert [(e.action, e.turn_id) for e in done] == [(ACTION, sent.turn_id)]
            answered = [e.decision for e in events(call) if isinstance(e, ConfirmationAnswered)]
            assert answered == ["asked_again", "yes"]
            return call.violations

    assert asyncio.run(scene()) == ()


def test_the_turn_holds_the_action_call_with_the_arguments_the_model_wrote() -> None:
    llm = model({ENGLISH.request: call_action(ENGLISH.note)})

    async def scene() -> None:
        async with TextCall(agent_of(Backend()), llm=llm, language="en") as call:
            asked = await call.user(ENGLISH.request)
            asked.expect.tool_call(ACTION, room=ROOM, note=ENGLISH.note)
            (made,) = asked.tool_calls
            assert dict(made.arguments) == {"room": ROOM, "note": ENGLISH.note}

    asyncio.run(scene())


# A stop or pause word over the read-back's summary, a stop over its closing question, or one
# said whole once it played.
STOPS = [("stop", "read_back"), ("wait", "read_back"), ("stop", "closing_question"), ("stop", None)]


@pytest.mark.parametrize(
    ("kind", "during"), STOPS, ids=["over", "pause_over", "over_question", "whole"]
)
@pytest.mark.parametrize("words", LANGUAGES, ids=_ids)
def test_a_stop_word_over_the_read_back_sends_nothing_and_keeps_the_draft(
    words: Words, kind: str, during: Any
) -> None:
    backend = Backend()
    stopping = words.stop if kind == "stop" else words.wait
    what = "What would you like to change?"
    llm = model(
        {
            words.request: call_action(words.note),
            stopping: say(what),
            words.yes_send: say("Tell me what to change first."),
            words.changed: call_action(words.changed),
        }
    )

    async def scene() -> tuple[str, ...]:
        async with TextCall(agent_of(backend), llm=llm, language=words.tag) as call:
            asked = await call.user(words.request)
            if during is None:
                await call.advance(SETTLE_S)
                asked.expect.read_back(room=ROOM, note=words.note)
            stop = await call.user(stopping, during=during)
            await call.advance(SETTLE_S)
            stop.expect.no_action()
            stop.expect.no_read_back()
            stop.expect.said(contains=what)
            (request,) = asked_with(llm, stopping)
            assert note("stopped") in told(request)
            assert {"room": ROOM, "note": words.note} in drafts_in(request)  # the draft kept
            eager = await call.user(words.yes_send)
            await call.advance(SETTLE_S)
            eager.expect.no_action()
            eager.expect.no_read_back()
            assert backend.writes == 0 and call._jobs is not None and not call._jobs.runs
            changed = await call.user(words.changed)
            await call.advance(SETTLE_S)
            changed.expect.read_back(room=ROOM, note=words.changed)
            sent = await call.user(words.yes_send)
            await call.advance(SETTLE_S)
            sent.expect.confirmed(ACTION, note=words.changed)
            sent.expect.action_completed(ACTION)
            assert backend.writes == 1
            (booked,) = backend.desk.booked.values()
            assert booked.note == words.changed
            return call.violations

    assert asyncio.run(scene()) == ()


@pytest.mark.parametrize("during", [None, "closing_question"], ids=["whole", "over_question"])
@pytest.mark.parametrize("words", LANGUAGES, ids=_ids)
def test_a_repeat_request_while_confirming_reads_it_again_and_a_yes_after_it_counts(
    words: Words, during: Any
) -> None:
    backend = Backend()
    llm = model({words.request: call_action(words.note)})

    async def scene() -> tuple[str, ...]:
        async with TextCall(agent_of(backend), llm=llm, language=words.tag) as call:
            asked = await call.user(words.request)
            if during is None:
                await call.advance(SETTLE_S)
            asked.expect.read_back(room=ROOM, note=words.note)
            again = await call.user(words.repeat, during=during)
            again.expect.read_back(room=ROOM, note=words.note)
            again.expect.no_action()
            over = await call.user(words.yes_send, during="read_back")
            over.expect.no_action()
            await call.advance(SETTLE_S)
            sent = await call.user(words.yes_send)
            await call.advance(SETTLE_S)
            sent.expect.confirmed(ACTION, room=ROOM, note=words.note)
            sent.expect.action_completed(ACTION)
            _, session = call._parts()
            first, second = readings(session.playback, plans_of(call._watched))
            assert call._jobs is not None
            (run,) = call._jobs.runs
            assert run.confirmed.reply_id == second.reply_id != first.reply_id
            assert backend.writes == 1
            assert len(await call.outbox.entries(action=ACTION)) == 1
            return call.violations

    assert asyncio.run(scene()) == ()

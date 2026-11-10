"""The caller's answers to an action's read-back end to end through `TextCall` (plan 007's
integration; the owner's rulings of 2026-11-10), on the library's own talker, session, yes rule
and action runner over a `MemoryOutbox` (action_call_support.py). A plain no sends nothing, and
the model's own next reply is spoken, its request holding the no note; a yes with a change in it
(«نعم بس غيّر ...») is a correction, nothing sent, its request holding the correction note, and
the new draft is read back anew; only unclear answers past the last ask-again hear the session's
fixed declined line. A read-back whose summary came back cut short or with no audio earns no
receipt, so a later yes confirms nothing."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from t2_agentic_voice.testing.text_call import TextCall
from t2_agentic_voice.testing.text_read_back import fold
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
    model,
    note,
    said_texts,
    say,
    told,
)

LANGUAGES = [ENGLISH, SAUDI]
# A yes with a change in it, in each language: "yes, but change the note"; «na'am bas ghayyir
# al-mulaaHaDHa», yes but change the note.
CHANGES = {"en": "yes but change the note", "ar-SA": "نعم بس غيّر الملاحظة"}
LEAVE_IT = "All right, I'll leave it. Anything else?"


def _ids(words: Words) -> str:
    return words.tag


def _folded(call: TextCall) -> str:
    return "".join(fold(text) for text in said_texts(call))


@pytest.mark.parametrize("words", LANGUAGES, ids=_ids)
def test_a_plain_no_sends_nothing_and_the_model_answers_in_its_own_words(words: Words) -> None:
    backend = Backend()
    llm = model({words.request: call_action(words.note), words.no: say(LEAVE_IT)})

    async def scene() -> tuple[str, ...]:
        async with TextCall(agent_of(backend), llm=llm, language=words.tag) as call:
            asked = await call.user(words.request)
            await call.advance(SETTLE_S)
            asked.expect.read_back(room=ROOM, note=words.note)
            no = await call.user(words.no)
            await call.advance(SETTLE_S)
            no.expect.no_action()
            no.expect.said(contains=LEAVE_IT)
            (request,) = asked_with(llm, words.no)
            assert note("no") in told(request)
            (plan,) = plans_of(call._watched)
            assert fold(plan.declined.text) not in _folded(call)  # the talker answered
            assert backend.writes == 0 and call._jobs is not None and not call._jobs.runs
            return call.violations

    assert asyncio.run(scene()) == ()


@pytest.mark.parametrize("words", LANGUAGES, ids=_ids)
def test_a_yes_with_a_change_is_a_correction_and_its_new_draft_is_read_back(words: Words) -> None:
    backend = Backend()
    change = CHANGES[words.tag]
    llm = model({words.request: call_action(words.note), change: call_action(words.changed)})

    async def scene() -> tuple[str, ...]:
        async with TextCall(agent_of(backend), llm=llm, language=words.tag) as call:
            await call.user(words.request)
            await call.advance(SETTLE_S)
            corrected = await call.user(change)
            await call.advance(SETTLE_S)
            corrected.expect.no_action()
            (request,) = asked_with(llm, change)
            assert note("correction") in told(request)
            corrected.expect.read_back(room=ROOM, note=words.changed)
            assert backend.writes == 0 and call._jobs is not None and not call._jobs.runs
            return call.violations

    assert asyncio.run(scene()) == ()


def test_only_unclear_answers_past_the_last_ask_again_hear_the_declined_line() -> None:
    backend = Backend()
    send = ENGLISH.send  # a send word with no yes word: unclear, never a yes
    llm = model({ENGLISH.request: call_action(ENGLISH.note)})

    async def scene() -> tuple[str, ...]:
        async with TextCall(agent_of(backend), llm=llm, language="en") as call:
            await call.user(ENGLISH.request)
            await call.advance(SETTLE_S)
            (plan,) = plans_of(call._watched)
            for _ in range(plan.max_attempts):
                unclear = await call.user(send)
                await call.advance(SETTLE_S)
                unclear.expect.asked_again()
                assert fold(plan.declined.text) not in _folded(call)
            last = await call.user(send)
            await call.advance(SETTLE_S)
            last.expect.said(contains=plan.declined.text)
            last.expect.no_action()
            assert asked_with(llm, send) == []  # the session's lines, not the talker's
            late = await call.user(ENGLISH.yes_send)  # confirming has ended
            await call.advance(SETTLE_S)
            late.expect.no_action()
            assert backend.writes == 0
            return call.violations

    assert asyncio.run(scene()) == ()


@pytest.mark.parametrize("fault", ["cut_short", "no_audio"])
@pytest.mark.parametrize("words", LANGUAGES, ids=_ids)
def test_a_summary_that_never_played_whole_lets_no_later_yes_confirm(
    words: Words, fault: Any
) -> None:
    backend = Backend()
    llm = model({words.request: call_action(words.note)})

    async def scene() -> tuple[str, ...]:
        async with TextCall(agent_of(backend), llm=llm, language=words.tag) as call:
            call.fault_read_back(fault)
            await call.user(words.request)
            await call.advance(SETTLE_S)
            assert len(plans_of(call._watched)) == 1
            yes = await call.user(words.yes_send)
            await call.advance(SETTLE_S)
            yes.expect.no_action()
            again = await call.user(words.yes_send)
            await call.advance(SETTLE_S)
            again.expect.no_action()
            assert backend.writes == 0 and call._jobs is not None and not call._jobs.runs
            assert await call.outbox.entries(action=ACTION) == ()
            return call.violations

    assert asyncio.run(scene()) == ()

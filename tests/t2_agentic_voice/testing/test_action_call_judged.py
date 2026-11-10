"""The yes rule's model check end to end through `TextCall` (D-082; the owner's rulings of
2026-11-10): the library's own talker on a fake model, the session's read-back and confirming,
the real yes rule and its check, the guard, the interruption rule and the action runner over a
`MemoryOutbox` (action_call_support.py), for an agent that asks, in English and in Saudi Arabic,
each answer said once the closing question ended and over it: the brief's table of expected
answers, each judged answer told `by="model"`, the lists' answers asking no model.

«اكيد» and "sure" are on the lists' yes words (Track A's), so they ask no model: they send once
the question ended and are asked again over it, as the table says, by the words; «صح» and "sure
thing", on no list, are the model's `yes`, and land the same, by the model."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass

import pytest
from t2_agentic_voice.core.errors import ProviderError
from t2_agentic_voice.core.events import ConfirmationAnswered
from t2_agentic_voice.domain.consent_check import TIMEOUT_S, is_consent_check
from t2_agentic_voice.testing.llm_fakes import Pause, ScriptStep
from t2_agentic_voice.testing.text_call import TextCall

from tests.t2_agentic_voice.testing.action_call_support import (
    ACTION,
    ENGLISH,
    ROOM,
    SAUDI,
    SETTLE_S,
    Backend,
    Words,
    agent_of,
    call_action,
    events,
    model,
    say,
)

LANGUAGES = [ENGLISH, SAUDI]
# A decision of the yes rule's, and what made it.
Answer = tuple[str, str]
YES_BY_MODEL: Answer = ("yes", "model")
AGAIN_BY_MODEL: Answer = ("asked_again", "model")
CORRECTION_BY_MODEL: Answer = ("correction", "model")
GO_AHEAD = {"en": "go for it", "ar-SA": "يلا أرسلها"}  # yalla arsilha: come on, send it
CHANGE = {
    "en": "yes, but make it urgent",
    "ar-SA": "ايه بس خلها عاجلة",  # eeh bas khalliha 'aajla: yes, but make it urgent
}
# The closing question heard back: "Shall I send it?"; «arsil aT-Talab?», send the request?
ECHO = {"en": "Shall I send it", "ar-SA": "أرسل الطلب"}


@dataclass(frozen=True)
class Row:
    """One row of the table: what the caller says in each language, what the check answers
    (None when the lists place the words, so no check is asked), and the answer once the
    closing question ended and over it."""

    words: dict[str, str]
    judged: Sequence[ScriptStep] | None
    after: Answer
    over: Answer


ROWS = {
    "listed_yes_and_send": Row(
        {"en": "yes send it", "ar-SA": "نعم أرسلها"}, None, ("yes", "words"), ("yes", "words")
    ),
    "listed_yes": Row(
        {"en": "sure", "ar-SA": "اكيد"}, None, ("yes", "words"), ("asked_again", "words")
    ),
    "agreement": Row(
        {"en": "sure thing", "ar-SA": "صح"}, say("yes"), YES_BY_MODEL, AGAIN_BY_MODEL
    ),  # sah: right
    "go_ahead": Row(GO_AHEAD, say("send"), YES_BY_MODEL, YES_BY_MODEL),
    "yes_but_change": Row(CHANGE, say("change"), CORRECTION_BY_MODEL, CORRECTION_BY_MODEL),
    "yes_but_change_judged_yes": Row(  # the change marker's rail
        CHANGE, say("yes"), CORRECTION_BY_MODEL, CORRECTION_BY_MODEL
    ),
    "hesitation": Row(
        {"en": "uhhh", "ar-SA": "امممم"}, say("unclear"), AGAIN_BY_MODEL, AGAIN_BY_MODEL
    ),  # ummmm, on no list
    "echo": Row(ECHO, say("unclear"), AGAIN_BY_MODEL, AGAIN_BY_MODEL),
    "echo_judged_send": Row(ECHO, say("send"), AGAIN_BY_MODEL, AGAIN_BY_MODEL),  # the echo rail
    "asked_back": Row(  # tawakkal ya ghaali?: go ahead, dear?
        {"en": "go for it?", "ar-SA": "توكل يا غالي؟"}, say("send"), AGAIN_BY_MODEL, AGAIN_BY_MODEL
    ),
    "check_failed": Row(
        GO_AHEAD, (ProviderError("server_error", True),), AGAIN_BY_MODEL, AGAIN_BY_MODEL
    ),
    "check_timed_out": Row(
        GO_AHEAD, (Pause(TIMEOUT_S + 1.0), *say("send")), AGAIN_BY_MODEL, AGAIN_BY_MODEL
    ),
}


def _ids(words: Words) -> str:
    return words.tag


@pytest.mark.parametrize("over", [False, True], ids=["after", "over"])
@pytest.mark.parametrize("words", LANGUAGES, ids=_ids)
@pytest.mark.parametrize("name", list(ROWS))
def test_each_answer_in_the_table_lands_as_the_brief_says(
    name: str, words: Words, over: bool
) -> None:
    row, backend = ROWS[name], Backend()
    said = row.words[words.tag]
    judged = {} if row.judged is None else {said: row.judged}
    llm = model({words.request: call_action(words.note)}, judged=judged)
    decision, by = row.over if over else row.after

    async def scene() -> tuple[str, ...]:
        async with TextCall(agent_of(backend, asks=True), llm=llm, language=words.tag) as call:
            await call.user(words.request)
            if over:
                answer = await call.user(said, during="closing_question")
            else:
                await call.advance(SETTLE_S)
                answer = await call.user(said)
            await call.advance(SETTLE_S)
            found = [
                (e.decision, e.by)
                for e in events(call)
                if isinstance(e, ConfirmationAnswered) and e.turn_id == answer.turn_id
            ]
            assert found == [(decision, by)]
            checks = [request for request in llm.requests if is_consent_check(request)]
            assert len(checks) == (0 if row.judged is None else 1)  # one a turn, none listed
            if decision == "yes":
                answer.expect.confirmed(ACTION, room=ROOM, note=words.note)
                answer.expect.action_completed(ACTION)
                assert backend.writes == 1
            else:
                answer.expect.no_action()
                assert backend.writes == 0
            if decision == "asked_again":
                answer.expect.asked_again()
            return call.violations

    assert asyncio.run(scene()) == ()


@pytest.mark.parametrize("words", LANGUAGES, ids=_ids)
def test_an_agent_that_does_not_ask_hears_unlisted_words_as_before(words: Words) -> None:
    """The flag off: a go-ahead the lists cannot place is unclear or a correction, as before,
    and no check is asked."""
    backend = Backend()
    said = GO_AHEAD[words.tag]
    llm = model({words.request: call_action(words.note)}, judged={said: say("send")})

    async def scene() -> tuple[str, ...]:
        async with TextCall(agent_of(backend), llm=llm, language=words.tag) as call:
            await call.user(words.request)
            await call.advance(SETTLE_S)
            answer = await call.user(said)
            await call.advance(SETTLE_S)
            answer.expect.no_action()
            assert not [request for request in llm.requests if is_consent_check(request)]
            answered = [e for e in events(call) if isinstance(e, ConfirmationAnswered)]
            assert [e.by for e in answered] == ["words"]
            assert backend.writes == 0
            return call.violations

    assert asyncio.run(scene()) == ()

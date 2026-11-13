"""The yes rule's model check end to end through `TextCall` (D-082; the owner's rulings of
2026-11-10): the library's own talker on a fake model, the session's read-back and confirming,
the real yes rule and its check, the guard, the interruption rule and the action runner over a
`MemoryOutbox` (action_call_support.py), for an agent that asks, in English and in Saudi Arabic,
each answer said once the closing question ended and over it: the brief's table of expected
answers, each judged answer told `by="model"`, the lists' answers asking no model.

«اكيد» and "sure" are on the lists' yes words, so they ask no model: they send once
the question ended and are asked again over it, as the table says, by the words; «صح» and "sure
thing", on no list, are the model's `yes`, and land the same, by the model.

A send word said alone goes to the model too (the owner's third ruling, 2026-11-10): it sends on
the model's `send`, over the closing question unless it copies the question, and on its `yes`
only once the question ended; words that copy a line are its echo only when heard as that line
plays or within its reply's tail, the closing question's or the ask-again line's (the library's
English one, "Shall I go ahead?", holds "go ahead"), and the caller's own once it and its tail
ended, as a turn said while the agent is silent is (the tail itself is test_yes_ask_tail.py's).

No word from the check (it failed, or ran out of its time) asks again, but declines words that
hold a no word (the owner's "Yes, all three", 2026-11-11): the turn then goes to the talker, so
a `ScriptedLLM` whose script ran out on the check fails the test at the talker's request
(docs/guide/testing.md, "The fake model and the yes rule's check")."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass

import pytest
from t2_agentic_voice.core.errors import ProviderError
from t2_agentic_voice.core.events import ConfirmationAnswered
from t2_agentic_voice.domain.consent_check import TIMEOUT_S, is_consent_check
from t2_agentic_voice.testing.llm_fakes import (
    Pause,
    ScriptedLLM,
    ScriptExhaustedError,
    ScriptStep,
)
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
DECLINED_BY_MODEL: Answer = ("declined", "model")
GO_AHEAD = {"en": "go for it", "ar-SA": "يلا أرسلها"}  # yalla arsilha: come on, send it
CHANGE = {
    "en": "yes, but make it urgent",
    "ar-SA": "ايه بس خلها عاجلة",  # eeh bas khalliha 'aajla: yes, but make it urgent
}
# The closing question heard back: "Shall I send it?"; «arsil aT-Talab?», send the request?
ECHO = {"en": "Shall I send it", "ar-SA": "أرسل الطلب"}
# A send word said alone (the owner's third ruling): ones that copy neither the summary nor the
# closing question («tawakkal», go ahead; «arsilha», send it), and one that copies the question
# («arsil», send).
OWN_SEND = {"en": "go ahead", "ar-SA": "توكل"}
OTHER_SEND = {"en": "proceed", "ar-SA": "أرسلها"}
COPYING_SEND = {"en": "send it", "ar-SA": "أرسل"}
# The library's ask-again line heard back: "... Shall I go ahead?", which holds a send word;
# «... asajjil at-talab?», shall I register the request?, which holds none.
ASKED_ECHO = {"en": "go ahead", "ar-SA": "أسجل الطلب"}
HESITATION = {"en": "uhhh", "ar-SA": "امممم"}  # ummmm, on no list
# A no that asks for another visit instead (run A's a3-dev, a44's kind): a no word beside words on
# no list, so the lists leave it to the model. «la, insaha, abgha ghurfa thaanya badaalha»: no,
# forget it, I want another room instead.
NO_AND_ANOTHER = {
    "en": "No, forget that one, I want another room instead",
    "ar-SA": "لا، انسها، أبغى غرفة ثانية بدالها",
}


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
    "hesitation": Row(HESITATION, say("unclear"), AGAIN_BY_MODEL, AGAIN_BY_MODEL),
    "echo": Row(ECHO, say("unclear"), AGAIN_BY_MODEL, AGAIN_BY_MODEL),
    # the echo rail over the question; said once it ended, the words are the caller's own
    "echo_judged_send": Row(ECHO, say("send"), YES_BY_MODEL, AGAIN_BY_MODEL),
    "send_alone": Row(OWN_SEND, say("send"), YES_BY_MODEL, YES_BY_MODEL),
    "other_send_alone": Row(OTHER_SEND, say("send"), YES_BY_MODEL, YES_BY_MODEL),
    "send_alone_copying_the_question": Row(COPYING_SEND, say("send"), YES_BY_MODEL, AGAIN_BY_MODEL),
    "send_alone_judged_yes": Row(OWN_SEND, say("yes"), YES_BY_MODEL, AGAIN_BY_MODEL),
    "send_alone_judged_unclear": Row(OWN_SEND, say("unclear"), AGAIN_BY_MODEL, AGAIN_BY_MODEL),
    "send_alone_check_failed": Row(
        OWN_SEND, (ProviderError("server_error", True),), AGAIN_BY_MODEL, AGAIN_BY_MODEL
    ),
    "send_alone_check_timed_out": Row(
        OWN_SEND, (Pause(TIMEOUT_S + 1.0), *say("send")), AGAIN_BY_MODEL, AGAIN_BY_MODEL
    ),
    "asked_back": Row(  # tawakkal ya ghaali?: go ahead, dear?
        {"en": "go for it?", "ar-SA": "توكل يا غالي؟"}, say("send"), AGAIN_BY_MODEL, AGAIN_BY_MODEL
    ),
    "check_failed": Row(
        GO_AHEAD, (ProviderError("server_error", True),), AGAIN_BY_MODEL, AGAIN_BY_MODEL
    ),
    "check_timed_out": Row(
        GO_AHEAD, (Pause(TIMEOUT_S + 1.0), *say("send")), AGAIN_BY_MODEL, AGAIN_BY_MODEL
    ),
    "no_and_another_check_failed": Row(
        NO_AND_ANOTHER, (ProviderError("server_error", True),), DECLINED_BY_MODEL, DECLINED_BY_MODEL
    ),
    "no_and_another_check_timed_out": Row(
        NO_AND_ANOTHER, (Pause(TIMEOUT_S + 1.0), *say("send")), DECLINED_BY_MODEL, DECLINED_BY_MODEL
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


@pytest.mark.parametrize(
    ("said", "over", "answer"),
    [
        (ASKED_ECHO, True, AGAIN_BY_MODEL),  # the ask-again line heard back as it plays
        (ASKED_ECHO, False, YES_BY_MODEL),  # its words said once it ended
        (OTHER_SEND, True, YES_BY_MODEL),  # a send word alone that copies no line, over it
        (COPYING_SEND, True, YES_BY_MODEL),  # one that copies the question, over the line
    ],
    ids=["echo", "echo_said_after", "send_alone", "copying_the_question"],
)
@pytest.mark.parametrize("words", LANGUAGES, ids=_ids)
def test_over_the_ask_again_line_only_its_own_words_are_its_echo(
    words: Words, said: dict[str, str], over: bool, answer: Answer
) -> None:
    """A hesitation asked again; then words said over the line that asks again, or once it
    ended, each judged `send`: only that line's own words, heard as it plays, are its echo."""
    backend, heard = Backend(), said[words.tag]
    judged = {HESITATION[words.tag]: say("unclear"), heard: say("send")}
    llm = model({words.request: call_action(words.note)}, judged=judged)

    async def scene() -> tuple[str, ...]:
        async with TextCall(agent_of(backend, asks=True), llm=llm, language=words.tag) as call:
            await call.user(words.request)
            await call.advance(SETTLE_S)
            unsure = await call.user(HESITATION[words.tag])
            if over:
                said_back = await call.user(heard, during="agent_speaking")
            else:
                await call.advance(SETTLE_S)
                said_back = await call.user(heard)
            await call.advance(SETTLE_S)
            found = [
                (e.turn_id, e.decision, e.by)
                for e in events(call)
                if isinstance(e, ConfirmationAnswered)
            ]
            assert found == [(unsure.turn_id, *AGAIN_BY_MODEL), (said_back.turn_id, *answer)]
            assert backend.writes == (1 if answer == YES_BY_MODEL else 0)
            return call.violations

    assert asyncio.run(scene()) == ()


@pytest.mark.parametrize("words", LANGUAGES, ids=_ids)
@pytest.mark.parametrize("said", [GO_AHEAD, OWN_SEND], ids=["go_ahead", "send_alone"])
def test_an_agent_that_does_not_ask_hears_unlisted_words_as_before(
    words: Words, said: dict[str, str]
) -> None:
    """The flag off: a go-ahead the lists cannot place, or a send word alone, is unclear or a
    correction, as before, and no check is asked."""
    backend, heard = Backend(), said[words.tag]
    llm = model({words.request: call_action(words.note)}, judged={heard: say("send")})

    async def scene() -> tuple[str, ...]:
        async with TextCall(agent_of(backend), llm=llm, language=words.tag) as call:
            await call.user(words.request)
            await call.advance(SETTLE_S)
            answer = await call.user(heard)
            await call.advance(SETTLE_S)
            answer.expect.no_action()
            assert not [request for request in llm.requests if is_consent_check(request)]
            answered = [e for e in events(call) if isinstance(e, ConfirmationAnswered)]
            assert [e.by for e in answered] == ["words"]
            assert backend.writes == 0
            return call.violations

    assert asyncio.run(scene()) == ()


@pytest.mark.parametrize("words", LANGUAGES, ids=_ids)
@pytest.mark.parametrize("said", [GO_AHEAD, NO_AND_ANOTHER], ids=["go_ahead", "no_and_another"])
def test_a_script_run_out_on_the_check_fails_the_test_only_when_the_talker_answers(
    words: Words, said: dict[str, str]
) -> None:
    """A `ScriptedLLM` with one entry, the talker's call of the action: the check finds none
    left, which is no word. On a go-ahead the caller is asked again and the test goes on; on
    words with a no word the read-back is declined and the turn goes to the talker, whose
    request finds no entry either, so the test fails there (testing.md, "No word")."""
    backend, heard = Backend(), said[words.tag]
    llm = ScriptedLLM([call_action(words.note)])

    async def scene() -> None:
        async with TextCall(agent_of(backend, asks=True), llm=llm, language=words.tag) as call:
            await call.user(words.request)
            await call.advance(SETTLE_S)
            answer = await call.user(heard)
            await call.advance(SETTLE_S)
            answer.expect.asked_again()
            answer.expect.no_action()

    if said is GO_AHEAD:
        asyncio.run(scene())
    else:
        with pytest.raises(ScriptExhaustedError):
            asyncio.run(scene())
    assert len([request for request in llm.requests if is_consent_check(request)]) == 1
    assert backend.writes == 0

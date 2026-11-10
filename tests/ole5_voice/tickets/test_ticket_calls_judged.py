"""Ole5's ticket calls end to end with the yes rule's model check (D-082; the owner's rulings of
2026-11-10): the served talker, which asks (`ask_on_unlisted_answers`), through `TextCall` on
the real session, talker, yes rule and its check, guard and action runner, as
test_ticket_calls.py runs it; `create_ticket` read back and answered in Saudi Arabic and English,
once the closing question ended and over it, the fake model answering each check (told by its
instruction) with the word a row gives.

- The brief's table: «اكيد» and "sure" are on the lists' yes words, so they ask no model, send
  once the question ended and are asked again over it, by the words; «صح» and "sure thing", on
  no list, are the model's yes and land the same, by the model; a go-ahead, "go for it" and
  «يلا أرسلها», sends either way; a hesitation, the closing question heard back (judged send,
  the echo's rail), a go-ahead asked back, a check that fails and one that times out are asked
  again. Each yes makes one ticket, its number said; nothing else makes any.
- A hesitation or a failed check asked again, a later yes makes one ticket.
- «ايه بس خلها عاجلة» and "yes, but make it urgent" are a correction, judged change or yes (the
  change marker's rail): the talker reads the ticket back again at priority High, and a listed
  yes makes that one ticket.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import pytest
from t2_agentic_voice import ProviderError
from t2_agentic_voice.domain.consent_check import TIMEOUT_S
from t2_agentic_voice.evals import Pause, ScriptedLLM, ScriptStep

from tests.ole5_voice.tickets.call_support import (
    SETTLE_S,
    Answer,
    Tag,
    answered,
    checks,
    grouped,
    model,
    ole5,
    said,
    text_call,
    yes_send,
)
from tests.ole5_voice.tickets.ticket_support import run

TAGS: list[Tag] = ["ar-SA", "en"]
# The caller's problem, said as not urgent, and the draft the model writes from it.
REQUEST = {
    "ar-SA": "صفحة التقارير في أوله فايف ما تطلع أي بيانات من الصبح، افتح لي تذكرة، مو مستعجلة.",
    "en": "My Ole5 reports page has shown no data since this morning. Open a ticket, not urgent.",
}
SUMMARY = {
    "ar-SA": "صفحة التقارير ما تعرض أي بيانات من الصبح.",
    "en": "The reports page has shown no data since this morning.",
}
DRAFT = {"type": "Report", "priority": "Medium"}
GO_AHEAD = {"ar-SA": "يلا أرسلها", "en": "go for it"}  # yalla arsilha: come on, send it
CHANGE = {
    "ar-SA": "ايه بس خلها عاجلة",  # eeh bas khalliha 'aajla: yes, but make it urgent
    "en": "yes, but make it urgent",
}
HESITATION = {"ar-SA": "امممم", "en": "uhhh"}  # ummmm, uhhh: on no list
# What the yes rule read a turn as, and by what.
Read = tuple[str, str]
YES_BY_MODEL: Read = ("yes", "model")
AGAIN_BY_MODEL: Read = ("asked_again", "model")


@dataclass(frozen=True)
class Row:
    """One row of the brief's table: the caller's words in each language, what the check
    answers (None when the lists place the words, so no check is asked), and what the yes rule
    reads once the closing question ended and over it."""

    words: Mapping[str, str]
    judged: tuple[ScriptStep, ...] | None
    after: Read
    over: Read


def _word(word: str) -> tuple[ScriptStep, ...]:
    return ScriptedLLM.reply(word)


ROWS = {
    "listed_sure": Row(
        {"ar-SA": "اكيد", "en": "sure"}, None, ("yes", "words"), ("asked_again", "words")
    ),  # akeed: sure
    "unlisted_agreement": Row(
        {"ar-SA": "صح", "en": "sure thing"}, _word("yes"), YES_BY_MODEL, AGAIN_BY_MODEL
    ),  # sah: right
    "go_ahead": Row(GO_AHEAD, _word("send"), YES_BY_MODEL, YES_BY_MODEL),
    "hesitation": Row(HESITATION, _word("unclear"), AGAIN_BY_MODEL, AGAIN_BY_MODEL),
    "echo_judged_send": Row(  # tabeeni arsilha: do you want me to send it (the closing question)
        {"ar-SA": "تبيني أرسلها", "en": "Shall I send it"},
        _word("send"),
        AGAIN_BY_MODEL,
        AGAIN_BY_MODEL,
    ),
    "asked_back": Row(  # tawakkal ya ghaali?: go ahead, dear?
        {"ar-SA": "توكل يا غالي؟", "en": "go for it?"},
        _word("send"),
        AGAIN_BY_MODEL,
        AGAIN_BY_MODEL,
    ),
    "check_failed": Row(
        GO_AHEAD, (ProviderError("server_error", True),), AGAIN_BY_MODEL, AGAIN_BY_MODEL
    ),
    "check_timed_out": Row(
        GO_AHEAD, (Pause(TIMEOUT_S + 1.0), *_word("send")), AGAIN_BY_MODEL, AGAIN_BY_MODEL
    ),
}


def _create(tag: Tag, *, priority: str = "Medium", heard: str | None = None) -> Answer:
    """The model's call of create_ticket for the caller's problem, at `priority`, in answer to
    the turn holding `heard` (the request unless given)."""
    steps = ScriptedLLM.call_tool(
        "create_ticket", summary=SUMMARY[tag], type=DRAFT["type"], priority=priority
    )
    return Answer(heard or REQUEST[tag], steps)


@pytest.mark.parametrize("over", [False, True], ids=["after", "over"])
@pytest.mark.parametrize("tag", TAGS)
@pytest.mark.parametrize("name", list(ROWS))
def test_each_answer_in_the_brief_lands_as_it_says_and_only_a_yes_makes_one_ticket(
    tmp_path: Path, name: str, tag: Tag, over: bool
) -> None:
    row = ROWS[name]
    words = row.words[tag]
    agent, tickets = ole5(tmp_path)
    llm = model(_create(tag), judged={} if row.judged is None else {words: row.judged})
    decision, by = row.over if over else row.after

    async def scene() -> None:
        async with text_call(agent, llm, tag) as call:
            asked = await call.user(REQUEST[tag])
            asked.expect.read_back(contains=SUMMARY[tag], summary=SUMMARY[tag], **DRAFT)
            if over:
                answer = await call.user(words, during="closing_question")
            else:
                await call.advance(SETTLE_S)
                answer = await call.user(words)
            await call.advance(SETTLE_S)
            assert answered(call, answer.turn_id) == [(decision, by)]
            assert checks(llm) == ([] if row.judged is None else [words])  # one a turn
            if decision == "yes":
                answer.expect.confirmed("create_ticket", summary=SUMMARY[tag], **DRAFT)
                answer.expect.action_completed("create_ticket")
                [made] = tickets.listed()
                assert grouped(made.number, tag) in said(call)
            else:
                answer.expect.no_action()
                answer.expect.asked_again()
                assert tickets.listed() == ()
            assert call.violations == ()

    run(scene())


@pytest.mark.parametrize("tag", TAGS)
@pytest.mark.parametrize(
    "judged",
    [_word("unclear"), (ProviderError("server_error", True),)],
    ids=["hesitation", "check_failed"],
)
def test_asked_again_after_a_hesitation_or_a_failed_check_a_later_yes_makes_one_ticket(
    tmp_path: Path, tag: Tag, judged: tuple[ScriptStep, ...]
) -> None:
    agent, tickets = ole5(tmp_path)
    llm = model(_create(tag), judged={HESITATION[tag]: judged})

    async def scene() -> None:
        async with text_call(agent, llm, tag) as call:
            await call.user(REQUEST[tag])
            await call.advance(SETTLE_S)
            unsure = await call.user(HESITATION[tag])
            await call.advance(SETTLE_S)
            assert answered(call, unsure.turn_id) == [AGAIN_BY_MODEL]
            unsure.expect.asked_again()
            assert tickets.listed() == ()
            sent = await call.user(yes_send(tag))
            await call.advance(SETTLE_S)
            assert answered(call, sent.turn_id) == [("yes", "words")]
            sent.expect.action_completed("create_ticket")
            assert call.violations == ()
        assert [made.summary for made in tickets.listed()] == [SUMMARY[tag]]
        assert checks(llm) == [HESITATION[tag]]  # the listed yes asked no model

    run(scene())


@pytest.mark.parametrize("over", [False, True], ids=["after", "over"])
@pytest.mark.parametrize("tag", TAGS)
@pytest.mark.parametrize("word", ["change", "yes"])
def test_a_yes_with_a_change_is_read_back_changed_and_a_yes_makes_that_ticket(
    tmp_path: Path, word: str, tag: Tag, over: bool
) -> None:
    """Judged change, or judged yes beside the change marker (bas, but): a correction, so the
    talker is given the words, and its new read-back at priority High is the one sent."""
    agent, tickets = ole5(tmp_path)
    urgent = _create(tag, priority="High", heard=CHANGE[tag])
    llm = model(_create(tag), urgent, judged={CHANGE[tag]: _word(word)})

    async def scene() -> None:
        async with text_call(agent, llm, tag) as call:
            await call.user(REQUEST[tag])
            if over:
                changed = await call.user(CHANGE[tag], during="closing_question")
            else:
                await call.advance(SETTLE_S)
                changed = await call.user(CHANGE[tag])
            await call.advance(SETTLE_S)
            assert answered(call, changed.turn_id) == [("correction", "model")]
            changed.expect.no_action()
            changed.expect.read_back(contains=SUMMARY[tag], summary=SUMMARY[tag], priority="High")
            assert tickets.listed() == ()
            sent = await call.user(yes_send(tag))
            await call.advance(SETTLE_S)
            sent.expect.confirmed("create_ticket", summary=SUMMARY[tag], priority="High")
            sent.expect.action_completed("create_ticket")
            assert call.violations == ()
        [made] = tickets.listed()
        assert (made.summary, made.priority) == (SUMMARY[tag], "High")
        assert checks(llm) == [CHANGE[tag]]

    run(scene())

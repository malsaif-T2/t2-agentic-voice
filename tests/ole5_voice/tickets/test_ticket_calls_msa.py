"""Ole5's ticket calls in the caller's register (the owner's ruling of 2026-11-10, "Add MSA
read-backs"): the served talker through `TextCall`, as test_ticket_calls.py runs it, in an
`ar-SA` call for a caller who speaks MSA or Saudi Arabic and in an English one.

- A caller whose Arabic holds no dialect form hears Ole5's MSA read-back, sending and done lines
  (lines.py's `ar` texts) and the library's MSA ask-again line; a Saudi caller still hears the
  Saudi ones, and an English caller the English ones; every line is said in the call's voice.
- The yes rule and its echo rail read the lines the caller heard: the MSA closing question heard
  back over it («هل أرسلها», hal ursiluha: shall I send it), judged send, is its echo and asked
  again; the same words said once it ended are the caller's, and send.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Final, Literal

import pytest
from ole5_voice.tickets import lines
from ole5_voice.tickets.drafts import PRIORITY_LABELS, TYPE_LABELS
from t2_agentic_voice.domain.action_lines import default_action_lines
from t2_agentic_voice.evals import ScriptedLLM

from tests.ole5_voice.tickets.call_support import (
    SETTLE_S,
    Answer,
    Tag,
    answered,
    checks,
    model,
    ole5,
    said,
    text_call,
    yes,
    yes_send,
)
from tests.ole5_voice.tickets.ticket_support import run

Register = Literal["msa", "saudi", "en"]
# The call's tag, and the tag its action's lines are read in, by the caller's register.
CALLED: Final[Mapping[Register, Tag]] = {"msa": "ar-SA", "saudi": "ar-SA", "en": "en"}
WORDING: Final[Mapping[Register, Literal["ar", "ar-SA", "en"]]] = {
    "msa": "ar",
    "saudi": "ar-SA",
    "en": "en",
}
# The caller's problem and the draft's summary, in each register: the reports page in Ole5 has
# shown no data since the morning, open an urgent ticket ("SafHat at-taqaareer fi niDhaam ole5
# la ta'riD ayya bayaanaat mundhu aS-SabaaH, arjoo fatH tadhkira 'aajila").
REQUEST: Final[Mapping[Register, str]] = {
    "msa": "صفحة التقارير في نظام أوله فايف لا تعرض أي بيانات منذ الصباح، أرجو فتح تذكرة عاجلة.",
    "saudi": "صفحة التقارير في أوله فايف ما تطلع أي بيانات من الصبح، أبي تفتح لي تذكرة ضروري.",
    "en": "My Ole5 reports page has shown no data since this morning, please open a ticket, "
    "it's urgent.",
}
SUMMARY: Final[Mapping[Register, str]] = {
    "msa": "صفحة التقارير لا تعرض أي بيانات منذ الصباح.",
    "saudi": "صفحة التقارير ما تعرض أي بيانات من الصبح.",
    "en": "The reports page has shown no data since this morning.",
}
DRAFT: Final = {"type": "Report", "priority": "High"}
# Ole5's MSA closing question heard back, its question mark dropped.
ECHO: Final = "هل أرسلها"


def _create(register: Register) -> Answer:
    """The model's call of create_ticket for the caller's problem."""
    steps = ScriptedLLM.call_tool("create_ticket", summary=SUMMARY[register], **DRAFT)
    return Answer(REQUEST[register], steps)


def _filled(template: str, values: Mapping[str, str]) -> str:
    """`template` with each placeholder, `{field}` or `{field:id}`, given its value."""
    for name, value in values.items():
        template = template.replace(f"{{{name}}}", value).replace(f"{{{name}:id}}", value)
    return template


@pytest.mark.parametrize("register", ["msa", "saudi", "en"])
def test_a_caller_hears_the_read_back_sending_and_done_lines_in_their_own_register(
    tmp_path: Path, register: Register
) -> None:
    tag, wording = CALLED[register], WORDING[register]
    agent, tickets = ole5(tmp_path)
    llm = model(_create(register))

    async def scene() -> str:
        async with text_call(agent, llm, tag) as call:
            asked = await call.user(REQUEST[register])
            asked.expect.read_back(contains=SUMMARY[register], **DRAFT)
            bare = await call.user(yes(tag), during="closing_question")
            await call.advance(1.0)
            bare.expect.asked_again()
            await call.advance(SETTLE_S)
            sent = await call.user(yes_send(tag))
            await call.advance(SETTLE_S)
            sent.expect.action_completed("create_ticket")
            assert call.violations == ()
            for clause in [c for turn in (asked, bare, sent) for c in turn.clauses]:
                assert clause.language == tag  # the call's voice, for the MSA lines too
            return said(call)

    heard = run(scene())
    [made] = tickets.listed()
    labels = "ar-SA" if tag == "ar-SA" else "en"
    summary, question = lines.TICKET_READ_BACK.for_language(wording)
    values = {
        "type": TYPE_LABELS["Report"][labels],
        "priority": PRIORITY_LABELS["High"][labels],
        "summary": SUMMARY[register],
        **{f"part_{n + 1}": made.number[4 * n : 4 * n + 4] for n in range(4)},
    }
    expected = [
        _filled(summary, values),
        question,
        default_action_lines(wording).asked_again,
        lines.TICKET_SENDING.for_language(wording),
        _filled(lines.TICKET_DONE.for_language(wording), values),
    ]
    assert [line for line in expected if line not in heard] == [], heard
    if register == "msa":
        assert lines.TICKET_READ_BACK.for_language("ar-SA")[1] not in heard  # no Saudi line


@pytest.mark.parametrize(("over", "decision"), [(True, "asked_again"), (False, "yes")])
def test_the_msa_closing_question_heard_back_over_it_is_its_echo_and_said_after_it_sends(
    tmp_path: Path, over: bool, decision: str
) -> None:
    """D-082's echo rail on the MSA lines the caller heard: «هل أرسلها», on no list but its
    send word, is put to the model, which judges it send; over the MSA closing question it
    copies that question, so it is asked again, and nothing is sent; once the question ended
    it is the caller's own, and makes the ticket."""
    agent, tickets = ole5(tmp_path)
    llm = model(_create("msa"), judged={ECHO: ScriptedLLM.reply("send")})

    async def scene() -> None:
        async with text_call(agent, llm, "ar-SA") as call:
            await call.user(REQUEST["msa"])
            if over:
                answer = await call.user(ECHO, during="closing_question")
            else:
                await call.advance(SETTLE_S)
                answer = await call.user(ECHO)
            await call.advance(SETTLE_S)
            assert answered(call, answer.turn_id) == [(decision, "model")]
            assert len(tickets.listed()) == (0 if over else 1)
            assert call.violations == ()
        assert checks(llm) == [ECHO]

    run(scene())

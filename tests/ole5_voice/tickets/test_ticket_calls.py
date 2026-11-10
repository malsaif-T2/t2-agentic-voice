"""Ole5's ticket calls end to end (plan 007's integration): the served talker
(`talker_agent(FakeKnowledgeBase(...), tickets=MockTicketSystem(...))`) through `TextCall`, the
library's own talker on a fake model that calls the actions as tools, the session's own
read-back and confirming, the real yes rule, guard and interruption rule, and the real action
runner over an outbox in memory; the caller the demo customer, as the token route mints it.

- The rehearsal's step 6, in Saudi Arabic and in English: a yes with a send word over the
  closing question opens the ticket, its number said in four groups; a bare yes there is asked
  again, and once the read-back is said again at the caller's request, the yes over its closing
  question counts (invariant 1, the owner's rulings); the lists place each, so the talker,
  which asks, asks no model of them (D-082; test_ticket_calls_judged.py asks).
- The rehearsal's step 3: «أبغى موظف» over a search answer stops it, and the handoff read back
  and confirmed makes a Request ticket holding the call's lines (Q7).
- A stop or pause word over the read-back sends nothing, and the talker is told it stopped;
  a yes after it is the talker's, and only a new read-back earns one (the owner's ruling).
- Ticket status of the caller's own ticket by its last four digits; another customer's number
  gives nothing of theirs, and a claim naming its digits is blocked by rule A (Q4, Q6,
  invariants 2 and 3). In a later call, whose record is empty, only the status result backs the
  caller's own last four digits, in a claim too.
- A passage's made-up ticket number said as the caller's in a claim is blocked by rule A, a
  passage being evidence of no ticket (invariant 2).
- A note on the ticket made in this call, named by its last four digits, goes on that ticket
  alone.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import pytest
from ole5_voice.settings import DEMO_CUSTOMER_EMAIL
from ole5_voice.tickets.values import QUEUE_OF
from t2_agentic_voice.agent.context import DECLINED
from t2_agentic_voice.evals import ScriptedLLM, TextCall
from t2_agentic_voice.ports import Passage
from t2_agentic_voice.stores import MemoryOutbox

from tests.ole5_voice.tickets.call_support import (
    SETTLE_S,
    Answer,
    Tag,
    blocks,
    checks,
    grouped,
    model,
    ole5,
    repeat_word,
    results,
    said,
    stop_word,
    text_call,
    told,
    wait_word,
    yes,
    yes_send,
)
from tests.ole5_voice.tickets.ticket_support import NOTE, OTHER, new_ticket, run

# The caller's problem, and the draft the model writes from it, in each language.
REQUEST = {
    "ar-SA": "صفحة التقارير في أوله فايف ما تطلع أي بيانات من الصبح، أبي تفتح لي تذكرة ضروري.",
    "en": "My Ole5 reports page has shown no data since this morning, please open a ticket, "
    "it's urgent.",
}
SUMMARY = {
    "ar-SA": "صفحة التقارير ما تعرض أي بيانات من الصبح.",
    "en": "The reports page has shown no data since this morning.",
}
DRAFT = {"type": "Report", "priority": "High"}
# The rehearsal's step 3: a question, the answer from the guide, and a person asked for.
QUESTION = "كيف أؤرشف مراسلة في النظام؟"
ANSWER = (
    "تقدر تأرشف المراسلة من صفحة المراسلات، تفتح المراسلة وبعدين تضغط زر الأرشفة فوق، وبعدها "
    "تختار مجلد الأرشيف وتأكد، وتلقاها بعدين في قائمة المراسلات المؤرشفة."
)
GUIDE = Passage(
    id="made-up-archiving",
    title="أرشفة مراسلة",
    text="لأرشفة مراسلة افتحها واضغط زر الأرشفة ثم اختر مجلد الأرشيف.",
    score=0.8,
)
PERSON = "أبغى موظف"  # abgha muwazzaf: I want an employee
HANDOFF = "يبي يكلم أحد من فريق الدعم عن أرشفة المراسلات."
# Ticket status: the caller's own ticket, then another customer's last four digits; what the
# model says after each status result; and the other customer's ticket.
STATUS = {"ar-SA": "وش صار على تذكرتي؟", "en": "What is the status of my ticket?"}
THEIRS = {"ar-SA": "وتذكرتي اللي تنتهي بالأرقام", "en": "And my ticket ending"}
IS_OPEN = {"ar-SA": "تذكرتك اللي تنتهي بالأرقام {} مفتوحة.", "en": "Your ticket ending {} is open."}
CREATED = {
    "ar-SA": "تم إنشاء تذكرتك اللي تنتهي بالأرقام {}.",
    "en": "I've created your ticket ending {}.",
}
OTHER_SUMMARY = "A made-up summary of someone else's ticket."
# A guide's passage holding a made-up ticket number, and the caller asking for theirs.
NUMBER = "2026102282004417"
FAKE_NUMBER = Passage(
    id="made-up-follow-up",
    title="متابعة بلاغ",
    text=f"لمتابعة البلاغ استخدم رقم التذكرة {NUMBER}، ويرد عليك فريق الدعم خلال يوم عمل.",
    score=0.7,
)
FOLLOW_UP = {
    "ar-SA": "وش رقم البلاغ اللي رفعته عن المرفقات؟",
    "en": "What is the number of my ticket about attachments?",
}
# The model saying that number is the caller's, in a claim: I opened you a ticket, its number.
AS_YOURS = {
    "ar-SA": f"فتحت لك تذكرة رقمها {NUMBER}.",
    "en": f"I've opened your ticket, its number is {NUMBER}.",
}
ADD_NOTE = "Please add a note to my ticket ending"


def _create(tag: Tag) -> Answer:
    """The model's call of create_ticket for the caller's problem."""
    steps = ScriptedLLM.call_tool("create_ticket", summary=SUMMARY[tag], **DRAFT)
    return Answer(REQUEST[tag], steps)


@pytest.mark.parametrize("bare_first", [False, True], ids=["eager", "bare_first"])
@pytest.mark.parametrize("tag", ["ar-SA", "en"])
def test_step_6_a_yes_with_a_send_word_over_the_closing_question_opens_the_ticket(
    tmp_path: Path, tag: Tag, bare_first: bool
) -> None:
    """The eager yes with a send word over the closing question; or first a bare yes there,
    asked again, then the read-back said again at the caller's request and the yes over it."""
    agent, tickets = ole5(tmp_path)
    llm = model(_create(tag))

    async def scene() -> None:
        async with text_call(agent, llm, tag) as call:
            asked = await call.user(REQUEST[tag])
            asked.expect.read_back(contains=SUMMARY[tag], summary=SUMMARY[tag], **DRAFT)
            if bare_first:
                bare = await call.user(yes(tag), during="closing_question")
                await call.advance(1.0)
                bare.expect.asked_again()
                bare.expect.no_action()
                assert tickets.listed() == ()
                again = await call.user(repeat_word(tag))
                again.expect.read_back(contains=SUMMARY[tag])
            sent = await call.user(yes_send(tag), during="closing_question")
            await call.advance(SETTLE_S)
            sent.expect.confirmed("create_ticket", summary=SUMMARY[tag], **DRAFT)
            sent.expect.action_completed("create_ticket")
            [made] = tickets.listed()
            assert grouped(made.number, tag) in said(call)
            assert call.violations == ()
        assert (made.customer_email, made.summary) == (DEMO_CUSTOMER_EMAIL, SUMMARY[tag])
        assert (made.type, made.priority, made.queue) == ("Report", "High", QUEUE_OF["Report"])
        assert told(llm, yes(tag)) == []  # each yes went to the yes rule, never the talker
        assert checks(llm) == []  # the lists placed each, so no model was asked (D-082)

    run(scene())


def test_step_3_a_person_asked_for_over_an_answer_makes_the_handoff_ticket(
    tmp_path: Path,
) -> None:
    agent, tickets = ole5(tmp_path, [GUIDE])
    llm = model(
        Answer(QUESTION, ScriptedLLM.call_tool("search_knowledge", query="أرشفة مراسلة")),
        Answer(QUESTION, ScriptedLLM.reply(ANSWER), after="search_knowledge"),
        Answer(PERSON, ScriptedLLM.call_tool("hand_off", summary=HANDOFF)),
        stop_over=[PERSON],
    )

    async def scene() -> None:
        async with text_call(agent, llm, "ar-SA") as call:
            asked = await call.user(QUESTION)
            asked.expect.tool_call("search_knowledge")
            over = await call.user(PERSON, during="agent_speaking")
            await call.advance(1.0)
            fates = [clause.fate for clause in asked.clauses]
            assert "cut" in fates and fates[-1] == "unplayed"  # the answer was stopped
            over.expect.read_back(contains=HANDOFF, summary=HANDOFF)
            sent = await call.user(yes_send("ar-SA"))
            await call.advance(SETTLE_S)
            sent.expect.confirmed("hand_off", summary=HANDOFF)
            sent.expect.action_completed("hand_off")
            assert call.violations == ()
        [made] = tickets.listed()
        assert (made.type, made.queue, made.priority) == ("Request", "Ole5 Support", "Medium")
        assert (made.customer_email, made.summary) == (DEMO_CUSTOMER_EMAIL, HANDOFF)
        caller = [line.text for line in made.transcript if line.speaker == "caller"]
        agent_said = " ".join(line.text for line in made.transcript if line.speaker == "agent")
        assert caller == [QUESTION, PERSON, yes_send("ar-SA")]
        assert ANSWER.split("،")[0] in agent_said and HANDOFF in agent_said
        assert ANSWER.split("،")[-1].strip() not in agent_said  # as the caller heard it

    run(scene())


@pytest.mark.parametrize(
    ("word", "during"), [(stop_word("ar-SA"), "read_back"), (wait_word("ar-SA"), None)]
)
def test_a_stop_or_pause_word_over_the_read_back_sends_nothing_and_the_talker_is_told(
    tmp_path: Path, word: str, during: Literal["read_back"] | None
) -> None:
    """A stop word over the summary, or a pause word said whole while confirming."""
    tag: Tag = "ar-SA"
    agent, tickets = ole5(tmp_path)
    change = "وش تبي أغير في التذكرة؟"  # what do you want me to change in the ticket?
    llm = model(
        _create(tag),
        Answer(word, ScriptedLLM.reply(change)),
        Answer(yes_send(tag), _create(tag).steps),
    )

    async def scene() -> None:
        async with text_call(agent, llm, tag) as call:
            await call.user(REQUEST[tag])
            stopped = await call.user(word, during=during)
            await call.advance(SETTLE_S)
            stopped.expect.no_action()
            stopped.expect.said(contains=change)
            assert tickets.listed() == ()
            note = DECLINED["stopped"].format(action="create_ticket")
            assert [note in message for message in told(llm, word)] == [True]
            # Only a new read-back played in full can earn a yes: this one is the talker's.
            later = await call.user(yes_send(tag))
            await call.advance(SETTLE_S)
            later.expect.no_action()
            later.expect.read_back(contains=SUMMARY[tag])
            assert tickets.listed() == ()
            sent = await call.user(yes_send(tag))
            await call.advance(SETTLE_S)
            sent.expect.action_completed("create_ticket")
            assert call.violations == ()
        assert [made.summary for made in tickets.listed()] == [SUMMARY[tag]]

    run(scene())


async def _opened(call: TextCall, tag: Tag) -> None:
    """The caller's problem read back, a yes with a send word, and the ticket made."""
    await call.user(REQUEST[tag])
    sent = await call.user(yes_send(tag))
    await call.advance(SETTLE_S)
    sent.expect.action_completed("create_ticket")


@pytest.mark.parametrize("tag", ["ar-SA", "en"])
def test_status_tells_the_callers_own_ticket_and_nothing_of_another_customers(
    tmp_path: Path, tag: Tag
) -> None:
    """In the call that made the ticket, whose record backs its last four digits too; the next
    test asks in a later call, where only the status result can."""
    agent, tickets = ole5(tmp_path)

    async def scene() -> None:
        theirs = await tickets.create(new_ticket("req-theirs", OTHER, summary=OTHER_SUMMARY))
        their_four = theirs.number[-4:]
        mine = f"{int(their_four) + 1:04d}"  # the mock's next number that day
        own = f"{IS_OPEN[tag].format(mine)} {CREATED[tag].format(mine)}"  # both may be said
        llm = model(
            _create(tag),
            Answer(STATUS[tag], ScriptedLLM.call_tool("ticket_status")),
            Answer(STATUS[tag], ScriptedLLM.reply(own), "ticket_status"),
            Answer(THEIRS[tag], ScriptedLLM.call_tool("ticket_status", number=their_four)),
            Answer(
                THEIRS[tag], ScriptedLLM.reply(CREATED[tag].format(their_four)), "ticket_status"
            ),
        )
        async with text_call(agent, llm, tag) as call:
            await _opened(call, tag)
            status = await call.user(STATUS[tag])
            await call.advance(SETTLE_S)
            status.expect.tool_call("ticket_status")
            status.expect.said(contains=own)
            assert status.blocked == ()
            asked = await call.user(f"{THEIRS[tag]} {their_four}?")
            await call.advance(SETTLE_S)
            asked.expect.tool_call("ticket_status", number=their_four)
            assert [blocked.unsupported for blocked in asked.blocked] == [(their_four,)]
            assert [event.reason for event in blocks(call)] == ["unsupported_claim"]
            assert their_four not in " ".join(clause.text for clause in asked.heard())
            assert call.violations == ()
        listed, nothing = results(llm, "ticket_status")
        assert f'"ends_in": "{mine}"' in listed and OTHER_SUMMARY not in listed
        assert [
            held for held in (theirs.number, their_four, OTHER_SUMMARY) if held in nothing
        ] == []
        assert [made.number[-4:] for made in tickets.listed()] == [their_four, mine]

    run(scene())


@pytest.mark.parametrize("tag", ["ar-SA", "en"])
def test_status_in_a_later_call_lets_the_callers_own_last_four_pass(
    tmp_path: Path, tag: Tag
) -> None:
    """The ticket made in one call, its status asked in the next on the same outbox: that call's
    record is empty, so only the status result (`reports_on`) backs its last four digits, said
    as an ID (rule B) and in a claim (rule A; invariant 2)."""
    agent, tickets = ole5(tmp_path)
    outbox = MemoryOutbox()

    async def scene() -> None:
        async with text_call(agent, model(_create(tag)), tag, outbox) as first:
            await _opened(first, tag)
        [made] = tickets.listed()
        mine = made.number[-4:]
        own = f"{IS_OPEN[tag].format(mine)} {CREATED[tag].format(mine)}"
        llm = model(
            Answer(STATUS[tag], ScriptedLLM.call_tool("ticket_status")),
            Answer(STATUS[tag], ScriptedLLM.reply(own), "ticket_status"),
        )
        async with text_call(agent, llm, tag, outbox) as call:
            status = await call.user(STATUS[tag])
            await call.advance(SETTLE_S)
            status.expect.tool_call("ticket_status")
            status.expect.said(contains=own)
            assert status.blocked == ()
            assert call.violations == ()
        [listed] = results(llm, "ticket_status")
        assert f'"ends_in": "{mine}"' in listed

    run(scene())


@pytest.mark.parametrize("tag", ["ar-SA", "en"])
def test_a_passages_ticket_number_said_as_the_callers_ticket_is_blocked(
    tmp_path: Path, tag: Tag
) -> None:
    """In a claim phrase: a passage is evidence of no ticket (invariant 2), so rule A blocks
    it; rule B would pass it, a passage's number being evidence of a fact (the design's 8.2).
    Said with no claim phrase, as the caller's ticket number, it passes (the design's 8.4;
    TD-142)."""
    agent, tickets = ole5(tmp_path, [FAKE_NUMBER])
    llm = model(
        Answer(FOLLOW_UP[tag], ScriptedLLM.call_tool("search_knowledge", query=FOLLOW_UP[tag])),
        Answer(FOLLOW_UP[tag], ScriptedLLM.reply(AS_YOURS[tag]), "search_knowledge"),
    )

    async def scene() -> None:
        async with text_call(agent, llm, tag) as call:
            asked = await call.user(FOLLOW_UP[tag])
            await call.advance(SETTLE_S)
            asked.expect.tool_call("search_knowledge")
            assert [blocked.unsupported for blocked in asked.blocked] == [(NUMBER,)]
            assert [event.reason for event in blocks(call)] == ["unsupported_claim"]
            assert NUMBER not in said(call)
            assert call.violations == ()
        assert tickets.listed() == ()
        assert [NUMBER in result for result in results(llm, "search_knowledge")] == [True]

    run(scene())


def test_a_note_on_the_ticket_made_in_this_call_goes_on_that_ticket_alone(
    tmp_path: Path,
) -> None:
    tag: Tag = "en"
    agent, tickets = ole5(tmp_path)

    async def scene() -> None:
        theirs = await tickets.create(new_ticket("req-theirs", OTHER))
        older = await tickets.create(new_ticket("req-older", DEMO_CUSTOMER_EMAIL))
        mine = f"{int(older.number[-4:]) + 1:04d}"  # the mock's next number that day
        noted = ScriptedLLM.call_tool("add_ticket_note", ticket_ends_in=mine, note=NOTE)
        llm = model(_create(tag), Answer(ADD_NOTE, noted))
        async with text_call(agent, llm, tag) as call:
            await _opened(call, tag)
            asked = await call.user(f"{ADD_NOTE} {mine}: {NOTE}")
            asked.expect.read_back(contains=NOTE, ticket_ends_in=mine, note=NOTE)
            sent = await call.user(yes_send(tag))
            await call.advance(SETTLE_S)
            sent.expect.confirmed("add_ticket_note", ticket_ends_in=mine, note=NOTE)
            sent.expect.action_completed("add_ticket_note")
            assert call.violations == ()
        notes = {made.number[-4:]: [n.text for n in made.notes] for made in tickets.listed()}
        assert notes == {theirs.number[-4:]: [], older.number[-4:]: [], mine: [NOTE]}

    run(scene())

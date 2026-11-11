"""Ole5's actions on the library's own action runner (plan 007's integration; the design's 6.4),
over the mock ticket system on each test's own folder: the read-back, `sending` and `declined`
lines `propose` renders from Ole5's words in Saudi Arabic and English; `done` saying a ticket's
whole number in four groups (Q6); each of the mock's modes run as a job on a virtual clock, with
its outcome, its outbox row and what the mock holds (docs/SECURITY.md, invariant 6); a restart's
reconcile, which never makes a second ticket; a caller who names no customer refused before any
read-back (invariant 3); and what the record and the outbox keep of a ticket made, which
`ticket_status` and `add_ticket_note` read in the same call."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest
from ole5_voice.tickets import lines
from ole5_voice.tickets.actions import has_customer
from ole5_voice.tickets.drafts import (
    ADD_NOTE,
    CREATE_TICKET,
    HAND_OFF,
    HandoffDraft,
    NoteDraft,
    TicketDraft,
    TicketMade,
    made_in,
)
from ole5_voice.tickets.status import TICKET_STATUS, StatusAnswer
from ole5_voice.tickets.system import TicketRef
from t2_agentic_voice import ToolError
from t2_agentic_voice.core.settings.tts import LanguageTag
from t2_agentic_voice.core.settings.words import LanguageCode
from t2_agentic_voice.domain.action_lines import ReadBackPlan, default_action_lines
from t2_agentic_voice.domain.ports.action_jobs import ActionOutcome
from t2_agentic_voice.domain.ports.chat_model import ChatRequest
from t2_agentic_voice.evals import FunctionLLM, ScriptedLLM, ScriptStep, TextCall
from t2_agentic_voice.stores import SqliteOutbox

from tests.ole5_voice.tickets.action_support import caller
from tests.ole5_voice.tickets.runner_support import (
    CALL_ID,
    CONVERSATION,
    LATE_S,
    SUBJECT,
    Rig,
    seed,
    until,
)
from tests.ole5_voice.tickets.ticket_support import NOTE, SUMMARY, run

# The report page shows no rows since this morning.
SAUDI = "صفحة التقارير ما تطلع فيها أي بيانات من الصبح"
SUMMARIES = {"ar-SA": SAUDI, "en": SUMMARY}
TAGS: tuple[LanguageTag, ...] = ("ar-SA", "en")
READ_BACKS = {
    "ar-SA": (f"بفتح لك تذكرة نوعها خلل في النظام: {SAUDI}", "تبيني أرسلها؟"),
    "en": (f"I'll open a ticket, type bug: {SUMMARY}", "Shall I send it?"),
}
DIGITS = {
    "ar-SA": ("صفر", "واحد", "اثنان", "ثلاثة", "أربعة", "خمسة", "ستة", "سبعة", "ثمانية", "تسعة"),
    "en": ("zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine"),
}
COMMA = {"ar-SA": "، ", "en": ", "}
DONE = {"ar-SA": "تم، تذكرتك رقمها {}.", "en": "Done. The ticket number is {}."}


def draft(tag: LanguageTag = "en") -> TicketDraft:
    return TicketDraft(summary=SUMMARIES[tag], type="Bug", priority="High")


def code(tag: LanguageTag) -> LanguageCode:
    return "en" if tag == "en" else "ar"


@pytest.mark.parametrize("tag", TAGS)
def test_the_ticket_is_read_back_by_its_labels_with_ole5s_own_lines(
    tmp_path: Path, tag: LanguageTag
) -> None:
    """(a) The type said by its label, then the summary as written, the draft's priority
    (High) left unsaid (the owner's ruling of 2026-11-11); the closing question holds the send
    word; `sending` and `declined` are Ole5's, never the library's; nothing is written before a
    yes."""
    rig = Rig(tmp_path)
    plan = run(rig.plan(CREATE_TICKET, draft(tag), tag))
    assert (plan.summary.text, plan.question.text) == READ_BACKS[tag]
    assert plan.sending.text == lines.TICKET_SENDING.for_language(tag)
    assert plan.declined.text == lines.TICKET_DECLINED.for_language(tag)
    library = default_action_lines(tag)
    assert (plan.sending.text, plan.declined.text) != (library.sending, library.declined)
    assert plan.send_words == tuple(lines.SEND_WORDS[code(tag)])
    assert json.loads(plan.draft_json) == draft(tag).model_dump(mode="json")
    assert plan.language == tag
    assert rig.system.listed() == ()
    assert run(rig.outbox.entries()) == ()


@pytest.mark.parametrize("tag", TAGS)
def test_a_handoff_is_read_back_with_the_conversation_named(
    tmp_path: Path, tag: LanguageTag
) -> None:
    rig = Rig(tmp_path)
    plan = run(rig.plan(HAND_OFF, HandoffDraft(summary=SUMMARIES[tag]), tag))
    summary, question = lines.HANDOFF_READ_BACK.for_language(tag)
    assert plan.summary.text == summary.format(summary=SUMMARIES[tag])
    assert plan.question.text == question
    assert plan.sending.text == lines.HANDOFF_SENDING.for_language(tag)
    assert plan.declined.text == lines.HANDOFF_DECLINED.for_language(tag)


def spoken_groups(number: str, tag: LanguageTag) -> str:
    groups = [number[at : at + 4] for at in range(0, len(number), 4)]
    words = DIGITS[tag]
    return COMMA[tag].join(" ".join(words[int(d)] for d in group) for group in groups)


@pytest.mark.parametrize("tag", TAGS)
def test_done_says_the_whole_number_in_four_groups(tmp_path: Path, tag: LanguageTag) -> None:
    """(b) The mock's 917th ticket of the day: its number in four groups of four, a comma
    between them, and in the spoken form each group's digits one by one."""
    seed(tmp_path, 916)
    rig = Rig(tmp_path)

    async def scene() -> ActionOutcome:
        return await rig.run(await rig.plan(CREATE_TICKET, draft(tag), tag))

    outcome = run(scene())
    number = rig.system.listed()[-1].number
    assert number == "2026111082000917"
    assert outcome.kind == "done"
    assert outcome.line.text == DONE[tag].format(COMMA[tag].join(("2026", "1110", "8200", "0917")))
    assert outcome.line.spoken == DONE[tag].format(spoken_groups(number, tag))


def done_text(number: str) -> str:
    return DONE["en"].format(", ".join(number[at : at + 4] for at in range(0, 16, 4)))


def test_a_late_reply_is_found_by_the_lookup_and_said_done(tmp_path: Path) -> None:
    """(c) The mock makes the ticket at once and answers after the job's timeout: the lookup
    finds it, `done` says the real number, and the late answer, when it comes, makes nothing
    more."""

    async def scene() -> None:
        rig = Rig(tmp_path, mode="late", late_s=LATE_S)
        plan = await rig.plan(CREATE_TICKET, draft())
        outcome = await rig.run(plan, advance_s=rig.action(CREATE_TICKET).timeout_s)
        [ticket] = rig.system.listed()
        assert (outcome.kind, outcome.line.text) == ("done", done_text(ticket.number))
        [row] = await rig.rows(CREATE_TICKET)
        assert (row.state, row.note) == ("done", "looked_up")
        made = TicketMade.model_validate_json(row.result_json or "")
        assert (made.ticket_id, made.number) == (ticket.id, ticket.number)
        await asyncio.sleep(LATE_S * 1.5)  # the late answer comes
        assert len(rig.system.listed()) == 1
        assert [(r.state, r.note) for r in await rig.rows(CREATE_TICKET)] == [("done", "looked_up")]

    run(scene())


MODES: list[tuple[dict[str, Any], str, str, str, int]] = [
    ({"mode": "late", "lookup": False}, "unknown", "flagged", "timed_out, no_lookup", 1),
    ({"mode": "timeout"}, "unknown", "flagged", "timed_out, not_found", 0),
    ({"mode": "timeout", "lookup": False}, "unknown", "flagged", "timed_out, no_lookup", 0),
    ({"mode": "refuse"}, "failed", "rejected", "rejected", 0),
]


@pytest.mark.parametrize("tag", TAGS)
@pytest.mark.parametrize(("modes", "kind", "state", "note", "made"), MODES)
def test_each_mode_ends_as_its_meaning_says(
    tmp_path: Path,
    tag: LanguageTag,
    modes: dict[str, Any],
    kind: str,
    state: str,
    note: str,
    made: int,
) -> None:
    """(c) Late with no lookup: the ticket made, `unknown` said, the row flagged. Timeout:
    nothing made, `unknown`, flagged. Refuse: nothing made, `failed`, the row rejected. Each
    line is Ole5's own, with no number."""

    async def scene() -> None:
        rig = Rig(tmp_path, **modes)
        action = rig.action(CREATE_TICKET)
        plan = await rig.plan(CREATE_TICKET, draft(tag), tag)
        advance = 0.0 if modes["mode"] == "refuse" else action.timeout_s
        outcome = await rig.run(plan, advance_s=advance)
        line = lines.TICKET_FAILED if kind == "failed" else lines.TICKET_UNKNOWN
        assert (outcome.kind, outcome.line.text) == (kind, line.for_language(tag))
        assert not any(c.isdigit() for c in outcome.line.text)
        [row] = await rig.rows(CREATE_TICKET)
        assert (row.state, row.note, row.result_json) == (state, note, None)
        assert len(rig.system.listed()) == made
        assert rig.runner.record(CALL_ID).entries() == ()

    run(scene())


@pytest.mark.parametrize("lookup", [True, False])
def test_a_row_left_sending_at_a_restart_makes_no_second_ticket(
    tmp_path: Path, lookup: bool
) -> None:
    """(d) A process ends while its write runs, the ticket made and the row left `sending`;
    the next one, on the same outbox and the same mock's file, reconciles it at start and
    never sends it again. With the lookup on it is flagged too: a lookup at start has no
    session, so no customer to look the ticket up for (customer.py)."""

    async def scene() -> None:
        path = tmp_path / "outbox.sqlite3"
        first = await SqliteOutbox.open(path)
        before = Rig(tmp_path / "tickets", outbox=first, mode="late", lookup=lookup)
        job = asyncio.ensure_future(before.run(await before.plan(CREATE_TICKET, draft())))
        await until(lambda: len(before.system.listed()) == 1)
        assert [row.state for row in await first.entries()] == ["sending"]
        await first.aclose()  # the process ends here, its write still under way
        again = await SqliteOutbox.open(path)
        try:
            after = Rig(tmp_path / "tickets", outbox=again, lookup=lookup)
            assert await after.runner.reconcile(clock=after.clock) == 1
            note = "left, not_found" if lookup else "left, no_lookup"
            assert [(r.state, r.note) for r in await again.entries()] == [("flagged", note)]
            assert await after.runner.reconcile(clock=after.clock, flagged=True) == 1
            assert [(r.state, r.note) for r in await again.entries()] == [("flagged", note)]
            assert len(after.system.listed()) == 1
        finally:
            await again.aclose()
            job.cancel()

    run(scene())


@pytest.mark.parametrize("name", [CREATE_TICKET, HAND_OFF, ADD_NOTE])
def test_a_caller_with_no_customer_is_refused_before_any_read_back(
    tmp_path: Path, name: str
) -> None:
    """(e) `validate` gets the call's context before the read-back: a caller whose token named
    no customer gets the talker the ToolError's text, and no read-back, nothing written."""
    drafts = {
        CREATE_TICKET: draft(),
        HAND_OFF: HandoffDraft(summary=SUMMARY),
        ADD_NOTE: NoteDraft(ticket_ends_in="0001", note=NOTE),
    }
    rig = Rig(tmp_path)
    made = run(rig.propose(name, drafts[name], email=None))
    assert not isinstance(made, ReadBackPlan)
    with pytest.raises(ToolError) as refused:
        run(has_customer(rig.context(email=None), drafts[name]))
    assert (made.ok, made.failure, made.data) == (
        False,
        "draft_rejected",
        {"error": refused.value.message},
    )
    assert rig.system.listed() == ()
    assert run(rig.outbox.entries()) == ()


def test_the_talker_is_told_why_no_ticket_can_be_made_for_no_customer(tmp_path: Path) -> None:
    """(e) In a call: the talker reads the refusal as the tool's result and no read-back plays."""
    rig = Rig(tmp_path)
    told: list[str] = []
    asked = "Please open a ticket: the report page shows no rows."
    sorry = "Sorry, I can't do that in this call."

    def answer(request: ChatRequest) -> Sequence[ScriptStep]:
        newest = [m for m in request.messages if m.role in ("user", "tool")][-1]
        if newest.role == "tool":
            told.append(newest.content)
            return ScriptedLLM.reply(sorry)
        return ScriptedLLM.call_tool(CREATE_TICKET, **draft().model_dump(mode="json"))

    async def scene() -> None:
        llm = FunctionLLM(answer)
        async with TextCall(rig.agent, llm=llm, caller=caller(None), language="en") as call:
            turn = await call.user(asked)
            await call.advance(30.0)
            turn.expect.no_read_back()
            turn.expect.no_action()
            turn.expect.said(contains=sorry)
            assert call.violations == ()

    run(scene())
    with pytest.raises(ToolError) as refused:
        run(has_customer(rig.context(email=None), draft()))
    assert len(told) == 1 and refused.value.message in told[0]
    assert rig.system.listed() == ()


def test_a_ticket_made_is_read_back_from_the_outbox_and_the_record(tmp_path: Path) -> None:
    """(f) The result the outbox and the record keep is the ticket made, as drafts.made_in
    parses it: `ticket_status` lists it by its last four digits in the same call, and
    `add_ticket_note`'s `validate` finds it in the call's record."""

    async def scene() -> None:
        rig = Rig(tmp_path)
        assert (await rig.run(await rig.plan(CREATE_TICKET, draft()))).kind == "done"
        [ticket] = rig.system.listed()
        kept = TicketMade.of(TicketRef(id=ticket.id, number=ticket.number))
        past = await rig.runner.past(SUBJECT, CREATE_TICKET)
        record = rig.runner.record(CALL_ID).view()
        for entries in (past, record):
            assert [entry.result for entry in entries] == [kept.model_dump(mode="json")]
            assert made_in(entries) == [(CREATE_TICKET, kept)]
        last_four = ticket.number[-4:]
        for asked, echoed in (({}, None), ({"number": last_four}, last_four)):
            result = await rig.tool(TICKET_STATUS, **asked)
            assert result.ok, result.data
            status = StatusAnswer.model_validate(result.data)
            assert [(t.ends_in, t.by) for t in status.tickets] == [(last_four, CREATE_TICKET)]
            assert (status.total, status.asked_ends_in) == (1, echoed)
            assert ticket.number not in json.dumps(result.data)
        note = NoteDraft(ticket_ends_in=last_four, note=NOTE)
        plan = await rig.plan(ADD_NOTE, note)
        assert last_four in plan.summary.text
        assert (await rig.run(plan)).kind == "done"
        assert [n.text for n in rig.system.listed()[0].notes] == [NOTE]
        other = await rig.propose(ADD_NOTE, NoteDraft(ticket_ends_in="9999", note=NOTE))
        assert not isinstance(other, ReadBackPlan) and other.failure == "draft_rejected"

    run(scene())


def test_a_handoff_ticket_carries_the_calls_conversation(tmp_path: Path) -> None:
    """Q7: the handoff's ticket is a request to support staff with what both sides said, and
    a status in the same call lists it as the handoff's."""

    async def scene() -> None:
        rig = Rig(tmp_path)
        plan = await rig.plan(HAND_OFF, HandoffDraft(summary=SUMMARY))
        assert (await rig.run(plan)).kind == "done"
        [ticket] = rig.system.listed()
        assert (ticket.type, ticket.transcript) == ("Request", CONVERSATION)
        status = StatusAnswer.model_validate((await rig.tool(TICKET_STATUS)).data)
        assert [(t.ends_in, t.by) for t in status.tickets] == [(ticket.number[-4:], HAND_OFF)]

    run(scene())

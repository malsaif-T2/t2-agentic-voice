"""What the tests of Ole5's actions on the library's action runner share (plan 007's integration):
Ole5's actions as the runtime takes them from the talker's declaration, over the mock on a
test's own folder, on the real `ActionRunner` and an outbox; the call's context as the talker
builds it (agent/context.py's `call_context`); a draft confirmed by the real yes rule, from heard
words and a read-back receipt each built through its seal as `voice` builds them; and a job run
on a virtual clock, moved on once the write's timer is set.

The mock's late answer and its timeout take real seconds, while a job's own timeout runs on the
virtual clock: `UNWAITED_S` unless a test gives `LATE_S`, so the job's timeout always comes
first however slow the machine, and no test waits for that answer but the one that waits
`LATE_S`, a fraction of a second; an answer still due when a test ends is cancelled with it."""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ole5_voice.agent import talker_agent
from ole5_voice.tickets.mock import FILE_NAME, MockTicket, MockTicketSystem
from ole5_voice.tickets.values import NEW_STATUS, QUEUE_OF
from pydantic import BaseModel
from t2_agentic_voice import Action, CallContext, ConversationLine, Tool
from t2_agentic_voice.actions.action_runner import ActionRunner
from t2_agentic_voice.actions.runner import ToolRunner
from t2_agentic_voice.actions.tools import ToolResult
from t2_agentic_voice.agent.context import call_context
from t2_agentic_voice.core.settings.words import LanguageCode
from t2_agentic_voice.core.yes_inputs import (
    HEARD_WORDS_SEAL,
    READ_BACK_SEAL,
    HeardWords,
    ReadBackReceipt,
)
from t2_agentic_voice.domain.action_lines import ReadBackPlan
from t2_agentic_voice.domain.ports.action_jobs import ActionOutcome
from t2_agentic_voice.domain.ports.chat_model import ToolCallRequest
from t2_agentic_voice.domain.ports.outbox import Outbox, OutboxEntry
from t2_agentic_voice.domain.yes_rule import ConfirmedAction, Yes, decide
from t2_agentic_voice.domain.yes_words import consent_words
from t2_agentic_voice.evals import FakeKnowledgeBase
from t2_agentic_voice.stores import MemoryOutbox
from t2_agentic_voice.testing.text_side import VirtualClock

from tests.ole5_voice.tickets.action_support import caller
from tests.ole5_voice.tickets.ticket_support import CUSTOMER, MORNING, SUMMARY, mock

LATE_S = 0.5
UNWAITED_S = 30.0
CALL_ID = "call-1"
SUBJECT = "owner"
# A yes with the closing question's own send word, said once the question has ended.
YES = {"ar-SA": "نعم أرسلها", "en": "yes, send it"}
# What both sides said in the call, which a handoff's ticket carries.
CONVERSATION = (
    ConversationLine(speaker="caller", text=SUMMARY),
    ConversationLine(speaker="agent", text="I'll pass your request to the support team."),
)


def confirmed(plan: ReadBackPlan, words: str | None = None, *, turn_id: int = 3) -> ConfirmedAction:
    """The confirmed action of `plan`'s draft as the real yes rule issues it: `words` (a yes
    with the send word unless given) heard after the closing question ended."""
    code: LanguageCode = "en" if plan.language == "en" else "ar"
    heard = HeardWords.model_validate(
        {
            "turn_id": turn_id,
            "text": words or YES[plan.language],
            "language": code,
            "at": 9.0,
            "speech_at": 8.0,
        },
        context=HEARD_WORDS_SEAL,
    )
    receipt = ReadBackReceipt.model_validate(
        {
            "action": plan.action,
            "draft_json": plan.draft_json,
            "reply_id": 2,
            "summary_played_at": 6.0,
            "question_ended_at": 7.0,
        },
        context=READ_BACK_SEAL,
    )
    said = decide(heard, receipt, words=consent_words(code, action_send=plan.send_words), env="dev")
    assert isinstance(said, Yes), said
    return said.confirmed


async def until(condition: Callable[[], bool], *, within_s: float = 5.0) -> None:
    """Return once `condition` holds, the event loop let run."""
    deadline = time.monotonic() + within_s
    while not condition():
        if time.monotonic() > deadline:
            raise AssertionError("the condition never came")
        await asyncio.sleep(0.001)


def seed(folder: Path, counter: int) -> None:
    """The mock's file in `folder` holding one ticket of the clock's day, its counter
    `counter`, so the next ticket the mock makes that day takes the one after it."""
    ticket = MockTicket(
        id=str(counter),
        number=f"{MORNING:%Y%m%d}82{counter:06d}",
        queue=QUEUE_OF["Inquiry"],
        type="Inquiry",
        priority="Medium",
        status=NEW_STATUS,
        summary=SUMMARY,
        created_at=MORNING,
        request_id="req-seeded",
        customer_email=CUSTOMER,
    )
    folder.mkdir(parents=True, exist_ok=True)
    kept = {"tickets": [ticket.model_dump(mode="json")]}
    (folder / FILE_NAME).write_text(json.dumps(kept), encoding="utf-8")


class Rig:
    """Ole5's actions over a mock in `folder` (its `mode`, `read_mode` and `lookup` as given,
    taking `late_s`), on one real runner over `outbox` (one in memory unless given), on a
    virtual clock."""

    def __init__(
        self,
        folder: Path,
        *,
        outbox: Outbox | None = None,
        late_s: float = UNWAITED_S,
        **modes: Any,
    ) -> None:
        self.system: MockTicketSystem = mock(folder, late_s=late_s, **modes)
        self.agent = talker_agent(FakeKnowledgeBase(), tickets=self.system)
        self.actions = tuple(t for t in self.agent.tools if isinstance(t, Action))
        self.outbox: Outbox = outbox if outbox is not None else MemoryOutbox()
        self.runner = ActionRunner(self.actions, outbox=self.outbox)
        self.clock = VirtualClock()

    def action(self, name: str) -> Action:
        found = self.runner.action(name)
        assert found is not None
        return found

    def context(self, tag: Any = "en", *, email: str | None = CUSTOMER) -> CallContext:
        """What a tool or an action's `validate` sees of the call, as the talker builds it."""
        return call_context(
            caller=caller(email),
            call_id=CALL_ID,
            language=tag,
            actions=self.runner,
            record=self.runner.record(CALL_ID),
        )

    async def propose(
        self, name: str, draft: BaseModel, tag: Any = "en", *, email: str | None = CUSTOMER
    ) -> ReadBackPlan | ToolResult:
        """The talker's call of `name` with `draft`, as the runner answers it."""
        request = ToolCallRequest(id=f"tool-{name}", name=name, arguments=draft.model_dump_json())
        return await self.runner.propose(request, self.context(tag, email=email), clock=self.clock)

    async def plan(self, name: str, draft: BaseModel, tag: Any = "en") -> ReadBackPlan:
        made = await self.propose(name, draft, tag)
        assert isinstance(made, ReadBackPlan), made
        return made

    async def run(self, plan: ReadBackPlan, *, advance_s: float = 0.0) -> ActionOutcome:
        """`plan`'s draft confirmed and run as a job; with `advance_s`, the clock moved on that
        far once the write's timer is set."""
        job = asyncio.ensure_future(
            self.runner.run(
                confirmed(plan),
                caller=caller(),
                call_id=CALL_ID,
                language=plan.language,
                turn_id=3,
                conversation=CONVERSATION,
                clock=self.clock,
            )
        )
        if advance_s:
            await until(lambda: self.clock.next_due is not None)
            await self.clock.advance(advance_s)
        return await job

    async def tool(self, name: str, **arguments: Any) -> ToolResult:
        """The talker's call of the read tool `name`, run as the talker's tool runner runs it."""
        (found,) = [t for t in self.agent.tools if isinstance(t, Tool) and t.name == name]
        request = ToolCallRequest(id=f"tool-{name}", name=name, arguments=json.dumps(arguments))
        return await ToolRunner([found]).run(request, self.context(), clock=self.clock)

    async def rows(self, name: str) -> tuple[OutboxEntry, ...]:
        return await self.outbox.entries(action=name)

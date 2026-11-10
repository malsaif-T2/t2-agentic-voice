"""What one play of run A acts on (action_play.py; plan 007's "The measurement"), as its scenario
says, each made new for the play:

- **The mock ticket system** (tickets/mock.py) in the play's own folder, answering its writes
  as the scenario's `tickets_mode` says, with the lookup by request ID on or off (`lookup`),
  and holding the scenario's seed tickets before the call: the caller's for the demo customer
  (`CUSTOMER`, the served app's), another customer's for `OTHER_CUSTOMER`. A seed ticket's ID
  counts up from 1, so a ticket the call makes comes after them; its day is its number's.
- **The outbox**, in memory, with a `done` row for each seed ticket made through the agent, by
  the action the scenario names, for the call's caller (`CALLER`), so `ticket_status` lists it
  as Ole5's outbox would (the plan's Q4).
- **The knowledge base** with the scenario's passage, when it has one, first in every search's
  results (`PassageFirst`), so the talker reads a fake ticket number as the base's.
"""

from __future__ import annotations

import json
from datetime import datetime, time
from pathlib import Path
from typing import Final

from t2_agentic_voice import Caller
from t2_agentic_voice.ports import KnowledgeBase, OutboxEntry, Passage
from t2_agentic_voice.stores import MemoryOutbox

from ole5_voice.customer import CUSTOMER_EMAIL
from ole5_voice.evals.action_scenarios import ActionScenario, SeedTicket
from ole5_voice.evals.talker_data import Tag
from ole5_voice.settings import DEMO_CUSTOMER_EMAIL
from ole5_voice.tickets.drafts import TicketMade
from ole5_voice.tickets.mock import FILE_NAME, RIYADH, MockTicket, MockTicketSystem
from ole5_voice.tickets.system import TicketRef
from ole5_voice.tickets.values import DEFAULT_PRIORITY, QUEUE_OF

# The caller every play is made for: the owner, as the served app's token names every caller,
# as the demo customer; and the customer another's seed tickets are of.
CUSTOMER: Final = DEMO_CUSTOMER_EMAIL
OTHER_CUSTOMER: Final = "another.customer@example.com"
CALLER: Final = Caller(subject="owner", attributes={CUSTOMER_EMAIL: CUSTOMER})
# The call a seed ticket's outbox row was written in, and the time of day it was made.
SEED_CALL: Final = "seeded-call"
SEED_TIME: Final = time(9, 0, tzinfo=RIYADH)
# The ID and title the scenario's passage is given in a search's results.
PASSAGE_ID: Final = "scenario-passage"
PASSAGE_TITLE: Final = "Ole5 support"


def _made_at(seed: SeedTicket) -> datetime:
    """When a seed ticket was made: its number's day, at `SEED_TIME`."""
    day = datetime.strptime(seed.number[:8], "%Y%m%d").date()
    return datetime.combine(day, SEED_TIME)


def _request_id(number: int) -> str:
    return f"seed-{number}"


def seed_tickets(scenario: ActionScenario) -> tuple[MockTicket, ...]:
    """The scenario's seed tickets as the mock keeps them (the module's docstring)."""
    return tuple(
        MockTicket(
            id=str(number),
            number=seed.number,
            queue=QUEUE_OF[seed.type],
            type=seed.type,
            priority=DEFAULT_PRIORITY,
            status=seed.status,
            summary=seed.summary,
            created_at=_made_at(seed),
            request_id=_request_id(number),
            customer_email=CUSTOMER if seed.owner == "caller" else OTHER_CUSTOMER,
        )
        for number, seed in enumerate(scenario.seed, start=1)
    )


def seeded_mock(folder: Path, scenario: ActionScenario) -> MockTicketSystem:
    """The mock in `folder`, a new one, holding the scenario's seed tickets, its writes and its
    lookup as the scenario says."""
    if seeds := seed_tickets(scenario):
        folder.mkdir(parents=True)
        kept = {"tickets": [ticket.model_dump(mode="json") for ticket in seeds]}
        (folder / FILE_NAME).write_text(json.dumps(kept, ensure_ascii=False), encoding="utf-8")
    return MockTicketSystem(folder, mode=scenario.tickets_mode, lookup=scenario.lookup)


async def seeded_outbox(scenario: ActionScenario) -> MemoryOutbox:
    """An outbox holding a `done` row for each of the scenario's seed tickets made through the
    agent, as the action that made it wrote it."""
    outbox = MemoryOutbox()
    for number, seed in enumerate(scenario.seed, start=1):
        if not seed.through_agent:
            continue
        made = TicketMade.of(TicketRef(id=str(number), number=seed.number))
        at = _made_at(seed)
        await outbox.add(
            OutboxEntry(
                request_id=_request_id(number),
                call_id=SEED_CALL,
                subject=CALLER.subject,
                action=seed.by,
                draft_json=json.dumps({"summary": seed.summary}, ensure_ascii=False),
                state="done",
                result_json=made.model_dump_json(),
                created_at=at,
                updated_at=at,
            )
        )
    return outbox


def fresh_folder(parent: Path, name: str) -> Path:
    """A folder named `name` under `parent` that does not exist yet: `name` itself, or with a
    number after it, for a play made again (a resumed run's)."""
    found, number = parent / name, 1
    while found.exists():
        number += 1
        found = parent / f"{name}-{number}"
    return found


class PassageFirst:
    """`kb`, with `passage` (None: none) first in every search's results; a `KnowledgeBase`."""

    def __init__(self, kb: KnowledgeBase, passage: str | None) -> None:
        self.kb, self.passage = kb, passage

    async def search(
        self, query: str, *, language: Tag, caller: Caller, limit: int
    ) -> list[Passage]:
        found = await self.kb.search(query, language=language, caller=caller, limit=limit)
        if self.passage is None:
            return found
        score = 1.0 + max((each.score for each in found), default=0.0)
        first = Passage(id=PASSAGE_ID, title=PASSAGE_TITLE, text=self.passage, score=score)
        return [first, *found][:limit]

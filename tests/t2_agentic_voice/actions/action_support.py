"""What the action runner's tests share (plan 007, Track B): a made-up request system that answers,
refuses, raises, times out, loses its reply or replies late, its action with or without a
lookup, a confirmed action built through the seals as the yes rule issues one (the yes rule
itself is Track A's), and a run of the runner on a test's clock.

Every line of the action is its own here, so no test reaches the library's default lines
(Track A's `default_action_lines`) unless it monkeypatches them."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field
from t2_agentic_voice.actions.action import Action, ActionContext, action
from t2_agentic_voice.actions.action_runner import ActionRunner
from t2_agentic_voice.actions.memory_outbox import MemoryOutbox
from t2_agentic_voice.actions.tools import CallContext
from t2_agentic_voice.core.conversation import ConversationLine
from t2_agentic_voice.core.errors import ActionNotSent, ActionRejected
from t2_agentic_voice.core.events import Event
from t2_agentic_voice.core.identity import Caller
from t2_agentic_voice.core.settings.tts import LanguageTag
from t2_agentic_voice.core.yes_inputs import (
    HEARD_WORDS_SEAL,
    READ_BACK_SEAL,
    HeardWords,
    ReadBackReceipt,
)
from t2_agentic_voice.domain.action_declaration import Claims, ReadBack, Say, Spoken
from t2_agentic_voice.domain.action_lines import ReadBackPlan
from t2_agentic_voice.domain.ports.action_jobs import ActionOutcome
from t2_agentic_voice.domain.ports.chat_model import ToolCallRequest
from t2_agentic_voice.domain.ports.outbox import Outbox, OutboxEntry
from t2_agentic_voice.domain.yes_rule import ConfirmedAction, _issued

from tests.t2_agentic_voice.fakes import FakeClock

CALLER = Caller(subject="made-up-subject")
CALL_ID = "call-1"
# A value only the caller and the draft hold, and the reason only the backend gives: neither may
# reach a log line, an error or an event.
SUMMARY = "the made-up laptop 4521 will not start"
REASON = "made-up-reason-7310"
ISSUED = "2026111082000123"
ARGUMENTS = f'{{"category": "software", "summary": "{SUMMARY}"}}'
CONVERSATION = (ConversationLine(speaker="caller", text=SUMMARY),)

Category = Annotated[
    Literal["hardware", "software"],
    Spoken({"hardware": {"ar": "أجهزة"}, "software": {"ar": "برامج", "en": "software"}}),
]


class OpenRequest(BaseModel):
    category: Category
    summary: Annotated[str, Field(max_length=200)]


class RequestOpened(BaseModel):
    number: str


READ_BACK = ReadBack(
    {
        "ar": ("بفتح طلب {category}: {summary}.", "أرسله؟"),
        "en": ("A {category} request: {summary}.", "Shall I send it?"),
    },
    send_words={"ar": ["افتحه"], "en": ["open it"]},
    asked_again=Say(ar="ما سمعتك، أرسل طلب {category}؟", en="Sorry, shall I send it?"),
)
DONE = Say({"ar": "تم، رقم الطلب {number:id}.", "en": "Done, your number is {number:id}."})
CLAIMS = Claims({"ar": ["فتحت الطلب"], "en": ["I've opened"]})
LINES: dict[str, Any] = {
    "sending": Say(ar="لحظة، أفتح لك طلب {category}.", en="One moment, opening your request."),
    "failed": Say(ar="ما قدرت أفتح الطلب.", en="I could not open the {category} request."),
    "unknown": Say(ar="ما قدرت أتأكد من الطلب.", en="I could not confirm it went through."),
    "declined": Say(ar="ما فتحت شيء.", en="I have not opened anything."),
}

Mode = Literal[
    "answer", "reject", "not_sent", "raise", "hang", "lost_reply", "late", "gated", "odd"
]


class Backend:
    """A made-up request system behind the action: `mode` says how its write ends. It keeps
    each write it did by its request ID (`held`), which its lookup reads, and the outbox row
    as each write began (`rows_at_write`)."""

    def __init__(self, mode: Mode = "answer", *, outbox: Outbox, clock: FakeClock) -> None:
        self.mode = mode
        self.outbox = outbox
        self.clock = clock
        self.writes: list[tuple[ActionContext, OpenRequest]] = []
        self.rows_at_write: list[OutboxEntry | None] = []
        self.lookups: list[str] = []
        self.held: dict[str, RequestOpened] = {}
        self.gate = asyncio.Event()
        self.finished = asyncio.Event()

    async def open(self, ctx: ActionContext, draft: OpenRequest) -> Any:
        self.writes.append((ctx, draft))
        self.rows_at_write.append(await self.outbox.get(ctx.request_id))
        opened = RequestOpened(number=ISSUED)
        match self.mode:
            case "reject":
                raise ActionRejected(f"{REASON} {draft.summary}")
            case "not_sent":
                raise ActionNotSent(f"{REASON} {draft.summary}")
            case "raise":
                raise RuntimeError(f"{REASON} {draft.summary}")
            case "hang":
                await asyncio.Event().wait()
            case "lost_reply":
                self.held[ctx.request_id] = opened
                await asyncio.Event().wait()
            case "late":
                await self.clock.sleep(30.0)
            case "gated":
                await self.gate.wait()
            case "odd":
                return {"not_a_number": REASON}
        self.held[ctx.request_id] = opened
        self.finished.set()
        return opened

    async def find(self, ctx: ActionContext, request_id: str) -> RequestOpened | None:
        self.lookups.append(request_id)
        return self.held.get(request_id)


def an_action(backend: Backend, *, lookup: bool = True, **changes: Any) -> Action:
    """The action over `backend`, with every line of its own, and its lookup unless `lookup`
    is False."""

    words: dict[str, Any] = {"read_back": READ_BACK, "done": DONE, "claims": CLAIMS, **LINES}

    @action(description="Open a made-up request.", **words | changes)
    async def open_request(ctx: ActionContext, draft: OpenRequest) -> RequestOpened:
        opened: RequestOpened = await backend.open(ctx, draft)
        return opened

    if lookup:

        @open_request.lookup
        async def find(ctx: ActionContext, request_id: str) -> RequestOpened | None:
            return await backend.find(ctx, request_id)

    return open_request


async def until(condition: Callable[[], bool], *, within_s: float = 10.0) -> None:
    """Return once `condition` holds, the event loop and its worker threads let run."""
    deadline = time.monotonic() + within_s
    while not condition():
        if time.monotonic() > deadline:
            raise AssertionError("the condition never came")
        await asyncio.sleep(0.001)


async def timer_set(clock: FakeClock, seconds: float, *, since: int = 0) -> None:
    """Return once something asked `clock` to sleep `seconds`, after its first `since` sleeps:
    a timeout's timer is set, so moving the clock on reaches it."""
    await until(lambda: seconds in clock.sleeps[since:])


def context(language: LanguageTag = "en", *, call_id: str = CALL_ID) -> CallContext:
    return CallContext(caller=CALLER, call_id=call_id, language=language)


def request(arguments: str = ARGUMENTS, name: str = "open_request") -> ToolCallRequest:
    return ToolCallRequest(id="tool-call-1", name=name, arguments=arguments)


def confirmed_of(
    plan: ReadBackPlan, *, reply_id: int = 4, turn_id: int = 9, words: str = "yes, send it"
) -> ConfirmedAction:
    """The confirmed action of `plan`'s draft, as the yes rule issues one: from heard words and
    the receipt of the read-back, each built through its seal as `voice` builds it."""
    heard = HeardWords.model_validate(
        {"turn_id": turn_id, "text": words, "language": "en", "at": 9.0, "speech_at": 8.0},
        context=HEARD_WORDS_SEAL,
    )
    receipt = ReadBackReceipt.model_validate(
        {
            "action": plan.action,
            "draft_json": plan.draft_json,
            "reply_id": reply_id,
            "summary_played_at": 6.0,
            "question_ended_at": 7.0,
        },
        context=READ_BACK_SEAL,
    )
    return _issued(heard, receipt, speech_at=8.0)


class Rig:
    """One runner over a backend of `mode`, its outbox, its clock and the events it emitted."""

    def __init__(
        self,
        mode: Mode = "answer",
        *,
        lookup: bool = True,
        outbox: Outbox | None = None,
        **changes: Any,
    ) -> None:
        self.clock = FakeClock()
        self.outbox: Outbox = outbox if outbox is not None else MemoryOutbox()
        self.backend = Backend(mode, outbox=self.outbox, clock=self.clock)
        self.action = an_action(self.backend, lookup=lookup, **changes)
        self.events: list[Event] = []
        self.runner = ActionRunner([self.action], outbox=self.outbox, emit=self.events.append)

    async def plan(self, language: LanguageTag = "en", *, call_id: str = CALL_ID) -> ReadBackPlan:
        made = await self.runner.propose(
            request(), context(language, call_id=call_id), clock=self.clock
        )
        assert isinstance(made, ReadBackPlan), made
        return made

    async def run(
        self,
        confirmed: ConfirmedAction,
        *,
        call_id: str = CALL_ID,
        language: LanguageTag = "en",
        advance_s: float = 0.0,
    ) -> ActionOutcome:
        """Run `confirmed`, the clock moved `advance_s` on once the write's timer is set."""
        before = len(self.clock.sleeps)
        job = asyncio.ensure_future(
            self.runner.run(
                confirmed,
                caller=CALLER,
                call_id=call_id,
                language=language,
                turn_id=9,
                conversation=CONVERSATION,
                clock=self.clock,
            )
        )
        if advance_s:
            await timer_set(self.clock, self.action.timeout_s, since=before)
            await self.clock.advance(advance_s)
        return await job

    async def confirmed_run(self, *, advance_s: float = 0.0) -> ActionOutcome:
        """Propose the draft, confirm it and run it."""
        return await self.run(confirmed_of(await self.plan()), advance_s=advance_s)

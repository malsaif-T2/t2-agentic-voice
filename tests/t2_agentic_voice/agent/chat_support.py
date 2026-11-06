"""What the talker's tests share: a small fake chat model of their own (`FakeChat`, one entry
per request, each the events that request streams; `HOLD` waits until the test releases it,
for a test of a stream cut in the middle), the agent they declare, and a way to run one reply
in a real cancel scope on a fake clock and gather its events."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from typing import Any

from pydantic import JsonValue
from t2_agentic_voice.actions.runner import ToolRunner
from t2_agentic_voice.actions.tools import Tool
from t2_agentic_voice.agent.talker import ChatTalker, TalkerCall, TalkerEvent
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.conversation import TalkerTurn
from t2_agentic_voice.core.identity import Caller
from t2_agentic_voice.core.settings.tts import LanguageTag
from t2_agentic_voice.domain.declaration import Language, VoiceAgent
from t2_agentic_voice.domain.ports.chat_model import (
    ChatEvent,
    ChatRequest,
    Done,
    FinishReason,
    TextDelta,
    ToolCallRequest,
    Usage,
)
from t2_agentic_voice.testing.llm_fakes import FAKE_DATA_FLOW
from t2_agentic_voice.voice.session.scope import CancelScope

from tests.t2_agentic_voice.fakes import FakeClock

# A step of an entry that waits, mid-stream, until the test sets `FakeChat.release`.
HOLD = "hold"
type Step = ChatEvent | BaseException | str
CALLER = Caller(subject="made-up-subject", attributes={"team": "it"})
SAUDI = Language.saudi_arabic(
    greeting="هلا، وش أقدر أساعدك فيه؟", progress={"searching": "ثواني أشيك لك"}
)
MSA = Language.arabic(greeting="مرحبا، كيف أساعدك؟", progress={"searching": "لحظات من فضلك"})
ENGLISH = Language.english(greeting="Hi, how can I help?", progress={"searching": "Checking that."})
INSTRUCTIONS = {
    "ar-SA": "Made-up Saudi instructions.",
    "ar": "Made-up MSA instructions.",
    "en": "Made-up English instructions.",
}


class FakeChat:
    """A chat model that plays its entries, one per request, in order; it keeps every request
    and counts the streams closed, a cancelled one included. Asked once too often, it fails."""

    name = "fake-chat"
    data_flow = FAKE_DATA_FLOW

    def __init__(self, *entries: Sequence[Step]) -> None:
        self.entries = list(entries)
        self.requests: list[ChatRequest] = []
        self.closed = 0
        self.release: asyncio.Event | None = None

    async def stream(self, request: ChatRequest) -> AsyncIterator[ChatEvent]:
        self.requests.append(request)
        assert self.entries, f"the model was asked {len(self.requests)} times, once too often"
        entry = self.entries.pop(0)
        try:
            for step in entry:
                if step == HOLD:
                    self.release = self.release or asyncio.Event()
                    await self.release.wait()
                elif isinstance(step, BaseException):
                    raise step
                elif not isinstance(step, str):
                    yield step
        finally:
            self.closed += 1

    async def aclose(self) -> None:
        """Nothing to close."""


def said(*pieces: str, finish: FinishReason = "stop") -> list[Step]:
    """An entry whose text streams in `pieces`, then its usage and its end."""
    return [
        *(TextDelta(text=p) for p in pieces),
        Usage(input_tokens=20, output_tokens=8),
        Done(finish_reason=finish),
    ]


def call(name: str, call_id: str = "c-1", **arguments: JsonValue) -> ToolCallRequest:
    """The model's call of the tool `name`, its arguments as the JSON it writes."""
    return ToolCallRequest(id=call_id, name=name, arguments=json.dumps(arguments))


def calls(*requests: ToolCallRequest, before: str = "") -> list[Step]:
    """An entry that says `before`, if anything, then asks for `requests`."""
    head: list[Step] = [TextDelta(text=before)] if before else []
    return [*head, *requests, Done(finish_reason="tool_calls")]


def agent(*tools: Tool, languages: Sequence[Language] = (SAUDI, MSA, ENGLISH)) -> VoiceAgent:
    """The agent the tests declare: `languages`, the instructions of each, and `tools`."""
    tags = {language.tag for language in languages}
    instructions = {tag: text for tag, text in INSTRUCTIONS.items() if tag in tags}
    return VoiceAgent(
        name="helper", languages=list(languages), instructions=instructions, tools=tools
    )


def talker(
    model: FakeChat,
    *tools: Tool,
    clock: FakeClock | None = None,
    language: LanguageTag = "en",
    settings: VoiceSettings | None = None,
    declared: VoiceAgent | None = None,
) -> ChatTalker:
    """A call's talker of `agent(*tools)` (or `declared`), on `clock`, in `language`."""
    return ChatTalker(
        declared or agent(*tools),
        model=model,
        runner=ToolRunner(tools),
        settings=settings or VoiceSettings(env="test"),
        call=TalkerCall(call_id="call-1", caller=CALLER, language=language),
        clock=clock or FakeClock(),
    )


async def settle(turns: int = 20) -> None:
    """Let the tasks the test started run for a few turns of the event loop."""
    for _ in range(turns):
        await asyncio.sleep(0)


Steps = Callable[[asyncio.Task[None], list[TalkerEvent], CancelScope, FakeClock], Awaitable[Any]]


def reply(
    chat: ChatTalker,
    turn: TalkerTurn,
    *,
    clock: FakeClock | None = None,
    steps: Steps | None = None,
) -> list[TalkerEvent]:
    """The events of `chat`'s reply to `turn`, iterated in a task of a real cancel scope on
    `clock` (the talker's own), as the session iterates it; `steps`, if given, runs beside it
    (moving the clock, cancelling the scope) before the reply is awaited."""
    used = clock or chat.clock
    assert isinstance(used, FakeClock)

    async def main() -> list[TalkerEvent]:
        scope = CancelScope(name="reply-1", clock=used)
        events: list[TalkerEvent] = []

        async def consume() -> None:
            async for event in chat.reply(turn, scope=scope):
                events.append(event)

        task = scope.start(consume(), name="reply-1-talker")
        if steps is not None:
            await asyncio.wait_for(steps(task, events, scope, used), timeout=10)
        done, _ = await asyncio.wait({task}, timeout=10)
        assert done, "the reply did not end"
        if not task.cancelled() and (error := task.exception()) is not None:
            raise error
        return events

    return asyncio.run(main())


def kinds(events: Sequence[TalkerEvent]) -> list[str]:
    """The events' class names, in order."""
    return [type(event).__name__ for event in events]

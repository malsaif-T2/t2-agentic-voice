"""The fakes runs K and S are tested on: a fake chat model that answers the talker and the judge,
a fake knowledge base, and a fake `TextCall` (the call factory a run takes) whose turns follow a
script, with a made-up agent that has a read tool; nothing is sent and no TextCall is needed."""

from __future__ import annotations

import asyncio
import json
from collections import Counter
from collections.abc import AsyncIterator, Callable, Sequence
from dataclasses import dataclass, field
from types import TracebackType
from typing import Any, Literal

from ole5_voice.evals.chat_pacing import CapReachedError, DailyLimitError
from ole5_voice.evals.talker_data import Tag
from pydantic import BaseModel
from t2_agentic_voice import Caller, Card, Language, ProviderError, Tool, VoiceAgent
from t2_agentic_voice.evals import BlockedClause, HeardClause, TextToolCall
from t2_agentic_voice.ports import (
    ChatEvent,
    ChatMessage,
    ChatRequest,
    DataFlow,
    Done,
    KnowledgeBase,
    Passage,
    TextDelta,
    Usage,
)

TALKER = "openai/gpt-oss-120b"
JUDGE = "llama-3.3-70b-versatile"
TOOL = "search_kb"
DOCUMENT = "دليل مختلق للنظام"  # a made-up document's name, keyed `guide`
FLOW = DataFlow(provider="none", processed_in="the test", stored_in="nowhere", retention="none")


def passage(n: int) -> Passage:
    return Passage(id=f"{DOCUMENT}/chunk_{n:03d}", title="A title", text="Some text.", score=0.5)


class FakeKnowledgeBase:
    """Answers each search with `found`'s passages for its query (point 1 by default), or
    fails one whose query `failing` names; keeps each search and whether it was closed."""

    def __init__(self) -> None:
        self.found: dict[str, list[Passage]] = {}
        self.failing: set[str] = set()
        self.searches: list[tuple[str, str, int]] = []
        self.closed = False

    async def search(
        self, query: str, *, language: str, caller: Caller, limit: int
    ) -> list[Passage]:
        self.searches.append((query, language, limit))
        if query in self.failing:
            raise ProviderError("server_error", True)
        return self.found.get(query, [passage(1)])[:limit]

    async def aclose(self) -> None:
        self.closed = True


Reply = Callable[[ChatRequest], Sequence[ChatEvent]]


class FakeChat:
    """A chat model: the judge's requests (`JUDGE`) answered with `verdicts`' verdict for the
    first of its keys found in the request (`right` by default), every other with a short
    text; `errors` raised, in order, before any event of the next requests."""

    name = "fake"
    data_flow = FLOW

    def __init__(self) -> None:
        self.verdicts: dict[str, str] = {}
        self.replies: list[str] = []  # the judge's raw replies, in order, before `verdicts`
        self.errors: list[BaseException] = []
        self.judge_fails_at: set[int] = set()  # the judge's requests that fail, from 1
        self.fails_at: set[int] = set()  # every request that fails, by its number from 1
        self.judged = 0
        self.requests: list[ChatRequest] = []
        self.input_tokens = 100
        self.failing: Counter[str] = Counter()
        self.closed = False

    async def stream(self, request: ChatRequest) -> AsyncIterator[ChatEvent]:
        self.requests.append(request)
        if self.errors:
            raise self.errors.pop(0)
        if len(self.requests) in self.fails_at:
            raise ProviderError("rejected", False)
        if request.model == JUDGE:
            self.judged += 1
            if self.judged in self.judge_fails_at:
                raise ProviderError("rejected", False)
        for event in self._events(request):
            yield event

    def _events(self, request: ChatRequest) -> list[ChatEvent]:
        usage = Usage(input_tokens=self.input_tokens, output_tokens=20, cached_tokens=10)
        if request.model != JUDGE:
            return [TextDelta(text="a short answer"), usage, Done(finish_reason="stop")]
        asked = request.messages[-1].content
        if self.replies:
            text = self.replies.pop(0)
        elif "The expectations:" in asked:
            text = json.dumps({"checks": self._checks(asked)})
        else:
            verdict = next((v for key, v in self.verdicts.items() if key in asked), "right")
            text = json.dumps({"verdict": verdict, "reason": "Made up."})
        return [TextDelta(text=text), usage, Done(finish_reason="stop")]

    def _checks(self, asked: str) -> list[dict[str, object]]:
        """A scenario turn's checks: each expectation holds, but where `failing` names words of
        this turn (`In this turn the caller said: ...`), which fail as often as it counts."""
        expectations = asked.split("The expectations:")[1].strip().splitlines()
        said = asked.split("In this turn the caller said: ")[1].splitlines()[0]
        holds = self.failing[said] <= 0
        self.failing[said] -= 1
        return [{"holds": holds, "reason": "Made up."} for _ in expectations]

    async def aclose(self) -> None:
        self.closed = True


@dataclass
class Scripted:
    """What a fake call's turn does for some words."""

    said: str = "A short made-up answer."
    language: Tag = "en"
    search: bool = True
    fate: str = "answered"
    first_clause_s: float | None = 0.4
    blocked: int = 0
    violations: int = 0
    cuts_earlier: bool = False
    cancels_search: bool = False
    error: BaseException | None = None
    delay_s: float = 0.0
    cards: tuple[Card, ...] = ()
    swallows: bool = False  # a model request's error, as a talker that catches every one


@dataclass
class FakeTurn:
    fate: str
    clauses: tuple[HeardClause, ...]
    tool_calls: tuple[TextToolCall, ...]
    cards: tuple[Card, ...]
    blocked: tuple[BlockedClause, ...]
    first_token_s: float | None
    first_clause_s: float | None
    model_requests: int
    usage: Usage


@dataclass
class Calls:
    """The fake calls of a run: each turn's script by its words, what each call was given, and
    the recorded knowledge base the agent was built on."""

    script: dict[str, Scripted] = field(default_factory=dict)
    said: list[tuple[str, str | None, str | None, str]] = field(default_factory=list)
    advanced: list[float] = field(default_factory=list)
    kb: KnowledgeBase | None = None

    def __call__(self, agent: VoiceAgent, **given: Any) -> FakeTextCall:
        return FakeTextCall(self, agent, **given)


class FakeTextCall:
    """Stands in for `TextCall`: each turn sends one request through the run's model, and
    searches the agent's knowledge base when its script says so."""

    def __init__(self, calls: Calls, agent: VoiceAgent, **given: Any) -> None:
        self.calls, self.agent, self.given = calls, agent, given
        self.turns: list[FakeTurn] = []
        self.found_violations = 0

    async def __aenter__(self) -> FakeTextCall:
        assert self.given["clock"] == "system"
        return self

    async def __aexit__(
        self,
        kind: type[BaseException] | None,
        error: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        return None

    async def user(
        self, text: str, *, during: str | None = None, at: str | None = None
    ) -> FakeTurn:
        language = self.given["language"]
        self.calls.said.append((text, during, at, language))
        scripted = self.calls.script.get(text, Scripted())
        if scripted.delay_s:
            await asyncio.sleep(scripted.delay_s)
        if scripted.error is not None:
            raise scripted.error
        settings = self.given["settings"]
        request = ChatRequest(
            messages=(ChatMessage.user(text),),
            model=settings.llm.model,
            max_output_tokens=settings.llm.max_output_tokens,
        )
        try:
            async for _ in self.given["llm"].stream(request):
                pass
        except (CapReachedError, DailyLimitError, ProviderError):
            if not scripted.swallows:
                raise
        tools: tuple[TextToolCall, ...] = ()
        if scripted.search:
            assert self.calls.kb is not None
            outcome: Literal["ok", "failed"] = "ok"
            try:
                await self.calls.kb.search(
                    text, language=language, caller=Caller(subject="x"), limit=3
                )
            except ProviderError:  # the tool fails, and the talker says so, as its runner does
                outcome = "failed"
            tools = (
                TextToolCall(
                    call_id="c1", tool=TOOL, arguments={"query": text}, outcome=outcome, ms=9.0
                ),
            )
        if self.turns and (scripted.cuts_earlier or scripted.cancels_search):
            earlier = self.turns[-1]
            earlier.fate = "cut" if scripted.cuts_earlier else earlier.fate
            if scripted.cancels_search:
                earlier.tool_calls = tuple(
                    TextToolCall(call_id=c.call_id, tool=c.tool, outcome="cancelled", ms=3.0)
                    for c in earlier.tool_calls
                )
        self.found_violations += scripted.violations
        turn = FakeTurn(
            fate=scripted.fate,
            clauses=(
                HeardClause(
                    text=scripted.said,
                    language=scripted.language,
                    fate="played",
                    played_fraction=1.0,
                ),
            ),
            tool_calls=tools,
            cards=scripted.cards,
            blocked=tuple(BlockedClause(text="x", language="en") for _ in range(scripted.blocked)),
            first_token_s=0.2,
            first_clause_s=scripted.first_clause_s,
            model_requests=1,
            usage=Usage(input_tokens=100, output_tokens=20),
        )
        self.turns.append(turn)
        return turn

    async def advance(self, seconds: float) -> None:
        self.calls.advanced.append(seconds)

    @property
    def violations(self) -> tuple[str, ...]:
        return ("an ID spoken with no evidence",) * self.found_violations


def agent(kb: KnowledgeBase) -> VoiceAgent:
    """A made-up agent with a read tool named `TOOL`, speaking the three languages."""

    class Query(BaseModel):
        query: str

    async def search(query: str) -> str:
        return query

    return VoiceAgent(
        name="madeup",
        languages=[
            Language.saudi_arabic(greeting="هلا"),
            Language.arabic(greeting="مرحبا"),
            Language.english(greeting="Hello."),
        ],
        instructions="Answer briefly.",
        tools=[
            Tool(
                name=TOOL, description="Search the made-up base.", parameters=Query, function=search
            )
        ],
        version="t1",
    )

"""The fakes runs K and S are tested on: a fake chat model that answers the talker and the judge,
a fake knowledge base, and a fake `TextCall` (the call factory a run takes) whose turns follow a
script, with a made-up agent that has a read tool; nothing is sent and no TextCall is needed."""

from __future__ import annotations

import asyncio
import json
import math
from collections import Counter
from collections.abc import AsyncIterator, Callable, Sequence
from dataclasses import dataclass, field
from types import TracebackType
from typing import Any, Final, Literal

from ole5_voice.evals.chat_pacing import CapReachedError, DailyLimitError
from ole5_voice.evals.judge import REGISTER_SYSTEM
from ole5_voice.evals.talker_data import Tag, script_of
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
    first of its keys found in the request (`right` by default), its register questions with
    `registers`' word for the first of its keys found in the reply's words (`saudi` for a reply
    in Arabic by default, `none` otherwise), every other with a short text; `errors` raised, in
    order, before any event of the next requests."""

    name = "fake"
    data_flow = FLOW

    def __init__(self) -> None:
        self.verdicts: dict[str, str] = {}
        self.registers: dict[str, str] = {}
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
        elif request.messages[0].content == REGISTER_SYSTEM:  # the reply's own words
            arabic = "saudi" if script_of(asked) == "ar" else "none"
            text = next((r for key, r in self.registers.items() if key in asked), arabic)
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


# The words a fake turn says when its script names none, by the tag it is spoken under.
SAID: Final[dict[Tag, str]] = {
    "en": "A short made-up answer.",
    "ar-SA": "هذا جواب قصير مختلق.",
    "ar": "هذه إجابة قصيرة مختلقة.",
}
# The pace a fake call's replies play at unless the run gives one, as TextCall's default.
CHARS_PER_SECOND = 15.0
# The event loop's rounds a turn said at "tool_running" waits for a search to run, and a fake
# search runs, so a correction lands only while an earlier turn is still being answered.
_ROUNDS = 50


@dataclass
class Scripted:
    """What a fake call's turn does for some words: it says `said` (`SAID`'s in `language` by
    default), which plays at the call's pace once the reply is written, unless `never_ends`."""

    said: str | None = None
    language: Tag = "en"
    search: bool = True
    fate: str = "answered"
    first_clause_s: float | None = 0.4
    blocked: int = 0
    violations: int = 0
    cuts_earlier: bool = False
    error: BaseException | None = None
    delay_s: float = 0.0
    cards: tuple[Card, ...] = ()
    swallows: bool = False  # a model request's error, as a talker that catches every one
    never_ends: bool = False
    # The talker's AssertionError (a fake model's script that ran out), as TextCall raises it:
    # from this turn's `user`, from the next `advance`, or from the call's end.
    fails_in: Literal["user", "advance", "exit"] | None = None

    @property
    def text(self) -> str:
        return SAID[self.language] if self.said is None else self.said


@dataclass
class FakeTurn:
    """A turn as TextCall's reads give it, read live: pending, its clauses unplayed, until its
    reply has played for `left_s` on the call's clock; then `ends`, its clauses played."""

    fate: str
    clauses: tuple[HeardClause, ...]
    tool_calls: tuple[TextToolCall, ...]
    cards: tuple[Card, ...]
    blocked: tuple[BlockedClause, ...]
    first_token_s: float | None
    first_clause_s: float | None
    model_requests: int
    usage: Usage
    left_s: float = 0.0
    ends: str = "answered"
    violations: int = 0

    @property
    def heard(self) -> bool:
        return any(clause.fate != "unplayed" for clause in self.clauses)

    def play(self, seconds: float) -> float:
        """Its reply played on for `seconds`; what is left of them once it has ended."""
        if self.fate != "pending":
            return seconds
        used = min(seconds, self.left_s)
        self.left_s -= used
        if self.left_s <= 1e-9:
            self.fate = self.ends
            self.clauses = tuple(
                clause.model_copy(update={"fate": "played", "played_fraction": 1.0})
                for clause in self.clauses
            )
        return seconds - used

    def cut(self) -> None:
        """Words said over its reply cut it, half of each clause heard."""
        self.fate = "cut"
        self.clauses = tuple(
            clause.model_copy(update={"fate": "cut", "played_fraction": 0.5})
            for clause in self.clauses
        )


@dataclass
class Calls:
    """The fake calls of a run: each turn's script by its words, what each call was given, and
    the recorded knowledge base the agent was built on."""

    script: dict[str, Scripted] = field(default_factory=dict)
    said: list[tuple[str, str | None, str | None, str]] = field(default_factory=list)
    advanced: list[float] = field(default_factory=list)
    given: list[dict[str, Any]] = field(default_factory=list)
    kb: KnowledgeBase | None = None

    def __call__(self, agent: VoiceAgent, **given: Any) -> FakeTextCall:
        self.given.append(given)
        return FakeTextCall(self, agent, **given)


class FakeTextCall:
    """Stands in for `TextCall` on the system clock: each turn sends one request through the
    run's model, and searches the agent's knowledge base when its script says so. As TextCall,
    `user` returns once the reply is written, its clauses unplayed; the clock moving on
    (`advance`, or a turn said once the agent is silent) plays them; a turn said
    `during="agent_speaking"` needs a reply playing and one `at="tool_running"` a search
    running, AssertionError otherwise (a correction landing in a search rolls its turn back);
    and the guard's violations count only the clauses heard."""

    def __init__(self, calls: Calls, agent: VoiceAgent, **given: Any) -> None:
        self.calls, self.agent, self.given = calls, agent, given
        self.cps = float(given.get("chars_per_second", CHARS_PER_SECOND))
        self.turns: list[FakeTurn] = []
        self.running = 0  # the searches running now
        self.corrections = 0  # the turns said while one ran
        self.failure: tuple[str, AssertionError] | None = None  # the talker's, still to raise

    async def __aenter__(self) -> FakeTextCall:
        assert self.given["clock"] == "system"
        return self

    async def __aexit__(
        self,
        kind: type[BaseException] | None,
        error: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if error is None and self.failure is not None:
            raise self.failure[1]

    async def user(
        self, text: str, *, during: str | None = None, at: str | None = None
    ) -> FakeTurn:
        await self._moment(during, at)
        self.calls.said.append((text, during, at, self.given["language"]))
        scripted = self.calls.script.get(text, Scripted())
        if scripted.delay_s:
            await asyncio.sleep(scripted.delay_s)
        if scripted.error is not None:
            raise scripted.error
        if scripted.fails_in is not None:
            self.failure = (scripted.fails_in, AssertionError("the fake model's script ran out"))
            if scripted.fails_in == "user":
                raise self.failure[1]
        await self._request(text, scripted)
        tools, corrected = await self._search(text) if scripted.search else ((), False)
        if self.turns and scripted.cuts_earlier and self.turns[-1].fate == "pending":
            self.turns[-1].cut()
        turn = FakeTurn(
            fate="rolled_back" if corrected else "pending",
            clauses=(
                HeardClause(
                    text=scripted.text,
                    language=scripted.language,
                    fate="unplayed",
                    played_fraction=0,
                ),
            ),
            tool_calls=tools,
            cards=scripted.cards,
            blocked=tuple(BlockedClause(text="x", language="en") for _ in range(scripted.blocked)),
            first_token_s=0.2,
            first_clause_s=scripted.first_clause_s,
            model_requests=1,
            usage=Usage(input_tokens=100, output_tokens=20),
            left_s=math.inf if scripted.never_ends else len(scripted.text) / self.cps,
            ends=scripted.fate,
            violations=scripted.violations,
        )
        self.turns.append(turn)
        return turn

    async def _moment(self, during: str | None, at: str | None) -> None:
        """Wait for the moment the words are said at, as TextCall's waits."""
        if at == "tool_running":
            for _ in range(_ROUNDS):
                if self.running:
                    self.corrections += 1
                    return
                await asyncio.sleep(0)
            raise AssertionError("no tool of a reply ran")
        playing = [turn for turn in self.turns if turn.fate == "pending"]
        if during == "agent_speaking" and not playing:
            raise AssertionError("no reply played")
        if during is None and any(math.isinf(turn.left_s) for turn in playing):
            raise AssertionError("the agent was never silent")
        for turn in playing if during is None else ():
            turn.play(turn.left_s)

    async def _request(self, text: str, scripted: Scripted) -> None:
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

    async def _search(self, text: str) -> tuple[tuple[TextToolCall, ...], bool]:
        """The turn's search, and whether a correction landed while it ran."""
        assert self.calls.kb is not None
        outcome: Literal["ok", "failed"] = "ok"
        before, self.running = self.corrections, self.running + 1
        try:
            await self.calls.kb.search(
                text, language=self.given["language"], caller=Caller(subject="x"), limit=3
            )
        except ProviderError:  # the tool fails, and the talker says so, as its runner does
            outcome = "failed"
        for _ in range(_ROUNDS):
            if self.corrections > before:
                break
            await asyncio.sleep(0)
        self.running -= 1
        used = TextToolCall(
            call_id="c1", tool=TOOL, arguments={"query": text}, outcome=outcome, ms=9.0, began_s=0.1
        )
        return (used,), self.corrections > before

    async def advance(self, seconds: float) -> None:
        self.calls.advanced.append(seconds)
        if self.failure is not None and self.failure[0] == "advance":
            raise self.failure[1]
        left = seconds
        for turn in self.turns:
            left = turn.play(left)
        await asyncio.sleep(0)

    @property
    def violations(self) -> tuple[str, ...]:
        found = sum(turn.violations for turn in self.turns if turn.heard)
        return ("an ID spoken with no evidence",) * found


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

"""The measuring part of a `poe eval-talker` run (`talker_run.py`): each variant of the knowledge
set as one call through `talker_call.ask`, its words said once, then read and scored.

A variant's call is held in the agent's first language (`--call-language first`, an Arabic call,
as Q9's run X may rule) or in its own words' (`variant`), and its reply is held to its words'
language either way (`talker_data.TAGS`), read from the reply's own words and the judge's
register (`talker_data.in_language`), never from the tag the library gave its clauses. Within
`--variant-timeout-s` on the wall clock, the call runs and its reply plays; then, for an
answerable item, the reference search of the variant's raw words; then the judge. A provider's
failure, in the call, its search or the reference search, makes the variant a `provider` failure
(a model request that failed after every attempt too, though the talker caught it), its limit
passed (or a moment the call waited for in vain) a `stuck` one, and a judge with no valid verdict
or no clear register (asked on its own, judge.py) a `judge` one: each counted apart. When the cap
or the key's daily limit stops a request (`chat_pacing`), the variant is dropped unscored
(`StopRun`), so a resumed run measures it again.

**Its times are the model's** (Q15), never the run's pacing: before its call, outside its limit,
a variant waits until the talker's model has room in the minute for the most requests a turn
sends (`TALKER_REQUESTS`, `PacedChat.ahead`), so no request of the call waits for room. A call
whose requests waited inside it anyway (one turned away and sent again after its retry-after,
or room the minute still lacked) keeps no time: its first token and first clause are None, so
no median holds a wait, and the variant is scored otherwise as any other.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final, Literal

from t2_agentic_voice import (
    Caller,
    ProviderError,
    T2VoiceError,
    VoiceAgent,
    VoiceSettings,
    get_logger,
)

from ole5_voice.evals.chat_pacing import CapReachedError, DailyLimitError, PacedChat
from ole5_voice.evals.groq_answerer import Clock
from ole5_voice.evals.judge import PASSING, Judge, Judged
from ole5_voice.evals.kb_points import TOP, KnowledgeData, RecordingKnowledge
from ole5_voice.evals.knowledge_set import KnowledgeItem, KnowledgeVariant
from ole5_voice.evals.models import Split
from ole5_voice.evals.talker_call import CallFactory, Held, ask
from ole5_voice.evals.talker_data import TAGS, Failure, HeardTurn, Tag, in_language
from ole5_voice.evals.talker_score import SearchMade, Stopped, VariantRecord

CALLER: Final = Caller(subject="talker-run")  # the reference search's caller, made up
TALKER_REQUESTS: Final = 3  # the most model requests the talker sends a turn
log = get_logger(__name__)
CallLanguage = Literal["first", "variant"]


@dataclass(frozen=True)
class Todo:
    """One variant to measure: its item, and its place in the item (from 1)."""

    item: KnowledgeItem
    position: int

    @property
    def variant(self) -> str:
        return f"v{self.position}"

    @property
    def asked(self) -> KnowledgeVariant:
        return self.item.variants[self.position - 1]

    @property
    def key(self) -> tuple[str, str]:
        return self.item.id, self.variant


def todo_of(items: Sequence[KnowledgeItem], split: Split) -> list[Todo]:
    """Every variant of `split`'s items, in the order of their items' IDs."""
    return [
        Todo(item, position)
        for item in sorted(items, key=lambda item: item.id)
        if item.split == split
        for position in range(1, len(item.variants) + 1)
    ]


class StopRun(Exception):  # noqa: N818 - it says what the run does, not an error
    """The cap or the key's daily limit stopped a request: the run stops."""

    def __init__(self, reason: Stopped) -> None:
        super().__init__(reason)
        self.reason: Stopped = reason


def stop_of(error: CapReachedError | DailyLimitError) -> Stopped:
    """Why `error` stops the run."""
    return "cap" if isinstance(error, CapReachedError) else "daily_limit"


@dataclass
class Measuring:
    """One run's measuring: the agent and the call's settings, the paced model, the recorded
    knowledge base, the data, the judge, and how each call is held."""

    agent: VoiceAgent
    paced: PacedChat
    settings: VoiceSettings
    knowledge: RecordingKnowledge
    data: KnowledgeData
    judge: Judge
    search_tool: str
    call_language: CallLanguage
    timeout_s: float
    call: CallFactory
    clock: Clock

    def call_tag(self, todo: Todo) -> Tag:
        if self.call_language == "first":
            return self.agent.languages[0].tag
        return TAGS[todo.asked.language]

    async def variant(self, todo: Todo, split: Split) -> VariantRecord:
        """`todo` measured and scored; StopRun when the cap or the day's limit stopped it."""
        llm = self.settings.llm
        await self.paced.ahead(llm.model, TALKER_REQUESTS, llm.max_output_tokens)
        began, mark = self.clock(), len(self.knowledge.searches)
        failed, waited = self.paced.spend.failures(), self.paced.waited_s
        item, words, want = todo.item, todo.asked.text, TAGS[todo.asked.language]
        failure: Failure | None = None
        turn: HeardTurn | None = None
        violations = 0
        try:
            held = await asyncio.wait_for(self._ask(words, self.call_tag(todo)), self.timeout_s)
            (turn,), violations = held.turns, held.violations
        except TimeoutError:
            failure = "stuck"
        except ProviderError:
            failure = "provider"
        self._stopped()
        if turn is not None and (inside := self.paced.waited_s - waited) > 0:
            log.warning("variant_untimed", waited_s=round(inside, 3))  # the run's own wait
            turn = turn.model_copy(update={"first_token_s": None, "first_clause_s": None})
        if self.paced.spend.failures() > failed and failure is None:
            failure = "provider"  # a model request failed, though the talker caught it
        searches = tuple(
            SearchMade(query=s.query, passages=s.passages, failed=s.failed)
            for s in self.knowledge.searches[mark:]
        )
        if any(search.failed for search in searches) and failure is None:
            failure = "provider"
        raw: tuple[str, ...] | None = None
        if failure is None and item.kind == "answerable":
            try:
                found = await self.knowledge.kb.search(
                    words, language=want, caller=CALLER, limit=TOP
                )
            except T2VoiceError:  # the knowledge base's failure, a ProviderError among them
                failure = "provider"
            else:
                raw = tuple(passage.id for passage in found[:TOP])
        judged: Judged | None = None
        if failure is None and turn is not None:
            judged = await self._judged(words, turn, item)
            failure = None if judged.verdict and judged.arabic else "judge"
        answered = turn is not None and failure is None
        searched = turn.searched(self.search_tool) if turn is not None else None
        answerable = item.kind == "answerable"
        own = next((s.passages for s in searches if not s.failed), ())
        return VariantRecord(
            item=item.id,
            variant=todo.variant,
            split=split,
            kind=item.kind,
            language=todo.asked.language,
            needs_search=item.needs_search,
            tag=want,
            turn=turn,
            violations=violations,
            searches=searches,
            raw_passages=raw,
            own_hit=self.data.index.hit(own, item.expected) if answered and answerable else None,
            raw_hit=self.data.index.hit(raw, item.expected) if raw is not None else None,
            search_right=searched == item.needs_search if answered else None,
            language_right=(
                in_language(turn, want, judged.arabic, words=words)
                if turn is not None and judged is not None and answered
                else None
            ),
            judged=judged,
            passed=judged.verdict == PASSING[item.kind] if answered and judged else None,
            failure=failure,
            seconds=max(self.clock() - began, 0.0),
        )

    async def _ask(self, words: str, tag: Tag) -> Held:
        try:
            return await ask(
                self.agent,
                self.paced,
                self.settings,
                words=words,
                language=tag,
                call=self.call,
                limit_s=self.timeout_s,
            )
        except (CapReachedError, DailyLimitError) as error:
            raise StopRun(stop_of(error)) from None

    async def _judged(self, words: str, turn: HeardTurn, item: KnowledgeItem) -> Judged:
        try:
            return await self.judge.verdict(
                asked=words, turn=turn, evidence=self.data.evidence(item)
            )
        except ProviderError:
            return Judged()
        except (CapReachedError, DailyLimitError) as error:
            raise StopRun(stop_of(error)) from None

    def _stopped(self) -> None:
        """StopRun when the paced model was stopped, whoever swallowed its error."""
        if self.paced.stopped is not None:
            raise StopRun(self.paced.stopped)

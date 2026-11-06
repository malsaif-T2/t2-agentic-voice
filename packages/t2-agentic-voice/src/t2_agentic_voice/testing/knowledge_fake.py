"""A fake knowledge base (the design's 9.1; plan 006): a `KnowledgeBase`
(domain/ports/knowledge.py) that answers from the passages a test gives it, reaches nothing, and
keeps every search it was asked (`searches`), so a test reads the talker's query, its language,
its caller and its limit. Its passages are the test's own, written for it, never a real base's.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from pydantic import BaseModel, ConfigDict, Field

from t2_agentic_voice.core.identity import Caller
from t2_agentic_voice.core.settings.tts import LanguageTag
from t2_agentic_voice.domain.ports.knowledge import Passage


class KnowledgeSearch(BaseModel):
    """One search a fake knowledge base was asked, as the talker asked it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    query: str
    language: LanguageTag
    caller: Caller
    limit: int = Field(ge=1)


class FakeKnowledgeBase:
    """A knowledge base that answers each query `answers` names with its passages, and any
    other with `passages` (none by default), best first as given, at most the search's limit;
    a `KnowledgeBase`."""

    def __init__(
        self,
        passages: Sequence[Passage] = (),
        *,
        answers: Mapping[str, Sequence[Passage]] | None = None,
    ) -> None:
        self.passages = tuple(passages)
        self.answers = {query: tuple(found) for query, found in (answers or {}).items()}
        self.searches: list[KnowledgeSearch] = []

    async def search(
        self, query: str, *, language: LanguageTag, caller: Caller, limit: int
    ) -> list[Passage]:
        """The passages for `query`, at most `limit`, the search kept. ValueError for a limit
        under 1, as a real base would refuse it."""
        search = KnowledgeSearch(query=query, language=language, caller=caller, limit=limit)
        self.searches.append(search)
        return list(self.answers.get(query, self.passages)[:limit])

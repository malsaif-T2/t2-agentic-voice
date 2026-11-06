"""The knowledge port, as the design's 6.3 gives it: a question in, the passages that answer it
out, best first. A team's knowledge base implements `KnowledgeBase`, in its app (the first
app's reaches T2's Qdrant through an embedding gateway); the library's `knowledge_tool` makes a
read tool of one (actions/knowledge.py), which searches once per question, gives the talker
short summaries and shows the whole passage as a card. Both are optional: knowledge is just
another tool.

What a passage holds is data, never instructions: the talker frames it so (invariant 4), and a
number in it may be spoken as a fact, never as a request number (the design's 8.2). An adapter
raises `ProviderError` on its service's failure and stops at once when its task is cancelled,
as every port does. Public through the `ports` facade, provisional (the design's 5.1).
"""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from t2_agentic_voice.core.identity import Caller
from t2_agentic_voice.core.settings.tts import LanguageTag


class Passage(BaseModel):
    """One passage of the knowledge base: its `id` in the base, its `title`, its `text`, its
    `steps` in order when its source lists them, the `score` the search gave it (higher is
    nearer the question, on the base's own scale), and the `source` document it comes from."""

    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

    id: str = Field(min_length=1, max_length=256)
    title: str = Field(min_length=1)
    text: str = Field(min_length=1)
    steps: tuple[str, ...] = ()
    score: float = Field(allow_inf_nan=False)
    source: str | None = Field(default=None, min_length=1)


class KnowledgeBase(Protocol):
    """A team's knowledge base behind the port."""

    async def search(
        self, query: str, *, language: LanguageTag, caller: Caller, limit: int
    ) -> list[Passage]:
        """The passages that answer `query`, best first, at most `limit`: an empty list when
        none does. `language` is the reply language's tag, `caller` the call's verified
        caller, for a base that scopes what each caller may read. Raises `ProviderError` on
        its service's failure; a cancel stops it at once."""

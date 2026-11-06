"""The knowledge tool (the design's 6.3; plan 006): a read tool made of a team's
`KnowledgeBase` (domain/ports/knowledge.py). The talker calls it with the caller's question in
its own words; it searches once, at most `limit` passages, in the reply's language and as the
call's caller; and it gives back:

- **to the talker**, each passage's id, title and a short summary to speak from (its first few
  lines, cut at a word near `SUMMARY_CHARS`), and the steps the card shows, so a follow-up
  ("only the second step") is answered from what the caller sees; a passage is data, never
  instructions (invariant 4);
- **to the caller**, the best passage whole as a card, its title, its steps (at most a card's 50)
  and its document, when it lists steps (a passage with none gives no card: its title alone
  adds nothing to the captions);
- **to the output guard**, every passage's title, text and steps as evidence for the ID rule,
  so a number a passage holds may be spoken as a fact.

What the knowledge base gives is checked as passages at the boundary: anything else is the
tool's failure, which the talker reads as "the tool failed" (actions/runner.py).
"""

from __future__ import annotations

from typing import Annotated

from pydantic import Field, TypeAdapter, ValidationError

from t2_agentic_voice.actions.tools import CallContext, Tool, ToolResult
from t2_agentic_voice.core.errors import ConfigurationError
from t2_agentic_voice.domain.cards import Card
from t2_agentic_voice.domain.ports.knowledge import KnowledgeBase, Passage

# The tool's name as the talker calls it, and the most of a passage's text its summary holds:
# its first lines, up to about three short spoken sentences.
NAME = "search_knowledge"
SUMMARY_LINES = 3
SUMMARY_CHARS = 400
# A card's most steps (domain/cards.py's `Card`).
_CARD_STEPS = 50
_PASSAGES = TypeAdapter(list[Passage])
Query = Annotated[
    str,
    Field(
        min_length=1,
        max_length=500,
        description="The caller's question, in their own words and language.",
    ),
]


def knowledge_tool(
    kb: KnowledgeBase, *, description: str, progress: str | None = None, limit: int = 5
) -> Tool:
    """A read tool that searches `kb` once per question (the module's docstring): `description`
    tells the talker when to call it, in English; `progress` names the line spoken when the
    search runs long (`Language.progress`); `limit` caps the passages it reads.
    ConfigurationError for a limit under 1."""
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        raise ConfigurationError(
            "The knowledge tool's `limit` is the most passages a search reads. FIX: give it a "
            "whole number of 1 or more, as limit=5.",
            details={"field": "limit"},
        )

    async def search_knowledge(ctx: CallContext, query: Query) -> ToolResult:
        found = await kb.search(query, language=ctx.language, caller=ctx.caller, limit=limit)
        return answer(_PASSAGES.validate_python(found)[:limit])

    return Tool.from_function(
        search_knowledge, description=description, name=NAME, progress=progress
    )


def answer(passages: list[Passage]) -> ToolResult:
    """What a search that found `passages`, best first, gives back (the module's docstring)."""
    card = _card(passages[0]) if passages else None
    data: dict[str, object] = {
        "passages": [
            {"id": passage.id, "title": passage.title, "summary": _summary(passage.text)}
            for passage in passages
        ]
    }
    if card is not None:
        data["shown_on_screen"] = {"title": card.title, "steps": list(card.steps)}
    evidence = tuple(text for p in passages for text in (p.title, p.text, *p.steps))
    return ToolResult(data=data, card=card, evidence=evidence)  # type: ignore[arg-type]


def _summary(text: str) -> str:
    """`text`'s first lines, cut at a word near `SUMMARY_CHARS`."""
    lines = [line.strip() for line in text.splitlines() if line.strip()][:SUMMARY_LINES]
    summary = " ".join(" ".join(lines).split())
    if len(summary) <= SUMMARY_CHARS:
        return summary
    cut = summary.rfind(" ", 0, SUMMARY_CHARS)
    return f"{summary[: cut if cut > 0 else SUMMARY_CHARS]} ..."


def _card(passage: Passage) -> Card | None:
    """The card `passage` shows: its title, its steps that say something and its document;
    None when it lists no step, or its title says nothing."""
    steps = tuple(step for step in passage.steps if step.strip())[:_CARD_STEPS]
    if not steps:
        return None
    source = passage.source if passage.source and passage.source.strip() else None
    try:
        return Card(title=passage.title, steps=steps, source=source)
    except ValidationError:
        return None

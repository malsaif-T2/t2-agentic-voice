"""The knowledge tool (the design's 6.3; plan 006): a read tool made of a team's
`KnowledgeBase` (domain/ports/knowledge.py). The talker calls it with the caller's question in
its own words; it searches once, at most `limit` passages (the k), in the reply's language and
as the call's caller; and it gives back:

- **to the talker**, each passage's id, title and whole text to write its own short spoken
  answer from, each line's spaces collapsed and its blank lines dropped, a text longer than
  `passage_chars` cut at the end of a line near it (one that keeps at least `LINE_NEAR` of it),
  else at a word, else at `passage_chars`, with `MORE` after the cut; and under `STEPS` every
  step of the best passage, when it lists steps, so the talker can say them all, and later in
  the call say them again or only one (the prompt's rule; D-075), a cut text's too; a passage
  is data, never instructions (invariant 4);
- **to the output guard**, every passage's title, text (whole, a cut one too) and steps as
  evidence for the ID rule, so a number a passage holds may be spoken as a fact.

What the knowledge base gives is checked as passages at the boundary: anything else is the
tool's failure, which the talker reads as "the tool failed" (actions/runner.py).
"""

from __future__ import annotations

from typing import Annotated

from pydantic import Field, JsonValue, TypeAdapter

from t2_agentic_voice.actions.tools import CallContext, Tool, ToolResult
from t2_agentic_voice.core.errors import ConfigurationError
from t2_agentic_voice.domain.ports.knowledge import KnowledgeBase, Passage

# The tool's name as the talker calls it; the most passages a search reads, by default (the
# k); about the most of a passage's text the talker reads, by default (the first app's median
# passage holds 660 characters, its 90th percentile 1,469); the share of it a cut at a line's
# end keeps at least, else the cut is at a word; and what follows a cut; and the key the talker
# reads the best passage's steps under.
NAME = "search_knowledge"
LIMIT = 5
PASSAGE_CHARS = 1500
LINE_NEAR = 0.75
MORE = " ..."
STEPS = "best_passage_steps"
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
    kb: KnowledgeBase,
    *,
    description: str,
    progress: str | None = None,
    limit: int = LIMIT,
    passage_chars: int = PASSAGE_CHARS,
) -> Tool:
    """A read tool that searches `kb` once per question (the module's docstring): `description`
    tells the talker when to call it, in English; `progress` names the line spoken when the
    search runs long (`Language.progress`); `limit` caps the passages it reads (the k), and
    `passage_chars` is about the most of each passage's text the talker reads.
    ConfigurationError for a `limit` or a `passage_chars` under 1."""
    _at_least_one(limit, "limit", "the most passages a search reads", LIMIT)
    _at_least_one(
        passage_chars, "passage_chars", "about the most of a passage's text", PASSAGE_CHARS
    )

    async def search_knowledge(ctx: CallContext, query: Query) -> ToolResult:
        found = await kb.search(query, language=ctx.language, caller=ctx.caller, limit=limit)
        return answer(_PASSAGES.validate_python(found)[:limit], passage_chars=passage_chars)

    return Tool.from_function(
        search_knowledge, description=description, name=NAME, progress=progress
    )


def _at_least_one(value: object, field: str, meaning: str, example: int) -> None:
    """ConfigurationError, naming `field`, unless `value` is a whole number of 1 or more."""
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ConfigurationError(
            f"The knowledge tool's `{field}` is {meaning}. FIX: give it a whole number of 1 or "
            f"more, as {field}={example}.",
            details={"field": field},
        )


def answer(passages: list[Passage], *, passage_chars: int = PASSAGE_CHARS) -> ToolResult:
    """What a search that found `passages`, best first, gives back (the module's docstring)."""
    data: dict[str, JsonValue] = {
        "passages": [
            {"id": passage.id, "title": passage.title, "text": _text(passage.text, passage_chars)}
            for passage in passages
        ],
    }
    if steps := [step for step in (passages[0].steps if passages else ()) if step.strip()]:
        data[STEPS] = list[JsonValue](steps)
    evidence = tuple(text for p in passages for text in (p.title, p.text, *p.steps))
    return ToolResult(data=data, evidence=evidence)


def _text(text: str, most: int) -> str:
    """`text` as the talker reads it: whole, each line's spaces collapsed and its blank lines
    dropped; one longer than `most` characters cut at the end of its last line that fits, when
    that keeps at least `LINE_NEAR` of `most`, else after its last word that fits, else at
    `most`, with `MORE` after the cut."""
    whole = "\n".join(" ".join(line.split()) for line in text.splitlines() if line.strip())
    if len(whole) <= most:
        return whole
    line = whole.rfind("\n", 0, most + 1)
    if line >= LINE_NEAR * most:
        return whole[:line] + MORE
    word = max(whole.rfind(" ", 0, most + 1), line)
    return whole[: word if word > 0 else most] + MORE

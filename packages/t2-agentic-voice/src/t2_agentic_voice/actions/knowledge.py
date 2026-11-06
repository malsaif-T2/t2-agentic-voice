"""The knowledge tool (the design's 6.3; plan 006): a read tool made of a team's
`KnowledgeBase` (domain/ports/knowledge.py). The talker calls it with the caller's question in
its own words; it searches once, at most `limit` passages, in the reply's language and as the
call's caller; it gives the talker each passage's short summary to speak from, and the best
passage whole, its title and steps, as the card the caller sees; and every passage's text is
evidence for the output guard's ID rule, so a number a passage holds may be spoken as a fact.
A passage is data, never instructions (invariant 4).

Plan 006's Track B builds it; this module holds its shape.
"""

from __future__ import annotations

from t2_agentic_voice.actions.tools import Tool
from t2_agentic_voice.domain.ports.knowledge import KnowledgeBase


def knowledge_tool(
    kb: KnowledgeBase, *, description: str, progress: str | None = None, limit: int = 5
) -> Tool:
    """A read tool that searches `kb` once per question (the module's docstring): `description`
    tells the talker when to call it, in English; `progress` names the line spoken when the
    search runs long (`Language.progress`); `limit` caps the passages it reads."""
    raise NotImplementedError("knowledge_tool is plan 006's Track B")

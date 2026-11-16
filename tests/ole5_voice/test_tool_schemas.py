"""Ole5's tools and actions are shown to the talker as before plan 010's change to how a tool's
schema is shown (the library's actions/tool_schema.py): none holds a reference, a `oneOf`, a
`discriminator` or a constant, so each is only untitled, as it was, and no measured outcome of
Ole5's moves (GP-18)."""

from __future__ import annotations

import json
from pathlib import Path

from ole5_voice.agent import search_tool
from ole5_voice.tickets.mock import MockTicketSystem
from ole5_voice.tickets.tools import ticket_tools
from t2_agentic_voice import Action, Tool
from t2_agentic_voice.evals import FakeKnowledgeBase


def test_no_ole5_tool_holds_what_the_shown_schema_changes(tmp_path: Path) -> None:
    tools = [*ticket_tools(MockTicketSystem(tmp_path)), search_tool(FakeKnowledgeBase([]))]
    assert len(tools) >= 5
    for each in tools:
        assert isinstance(each, Tool | Action)
        text = json.dumps(each.tool_schema().parameters)
        for word in ('"$ref"', '"$defs"', '"oneOf"', '"discriminator"', '"const"', '"title": "'):
            assert word not in text, (each.name, word)

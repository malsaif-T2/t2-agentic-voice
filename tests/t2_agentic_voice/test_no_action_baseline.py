"""What an agent with no actions is sent must not change by accident (plan 007, Block 0; the plan
README's "Parallel tracks"): the talker's system prompt, a tool's schema, the words of a turn, and
the lists the interruption rule reads, measured on the five kinds it has. The fixture holds them
as they were before the tracks. A change here is deliberate: a rule added for actions goes only
to an agent that declares one, and the yes and send words stay out of `domain/words.py`."""

from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path
from typing import Annotated, Any

from pydantic import Field
from t2_agentic_voice.actions.tools import Tool
from t2_agentic_voice.agent.context import turn_message
from t2_agentic_voice.agent.prompt import compose_prompt
from t2_agentic_voice.core.conversation import TalkerTurn
from t2_agentic_voice.domain.words import PRESET_WORDS, WORD_KINDS

from tests.t2_agentic_voice.agent.chat_support import agent

FIXTURE = Path(__file__).parent / "fixtures" / "no_action_baseline.json"
DAY = date(2026, 11, 6)


async def _find_article(
    query: Annotated[str, Field(description="What to look for")], limit: int = 3
) -> str:
    return query * limit


def _words_sha(code: str) -> str:
    words = json.dumps(PRESET_WORDS[code].model_dump(), ensure_ascii=True, sort_keys=True)  # type: ignore[index]
    return hashlib.sha256(words.encode("ascii")).hexdigest()


def today() -> dict[str, Any]:
    """Everything the fixture pins, as the code gives it now."""
    schema = Tool.from_function(_find_article, description="Find a made-up article.").tool_schema()
    turn = TalkerTurn(
        turn_id=3, words="a made-up question", language="en", over_reply=2, cut_reply=2
    )
    return {
        "prompt": {
            tag: compose_prompt(agent(), language=tag, today=DAY) for tag in ("ar-SA", "en")
        },
        "tool_schema": {
            "name": schema.name,
            "description": schema.description,
            "parameters": schema.parameters,
        },
        "turn_message": turn_message(turn).content,
        "word_kinds": list(WORD_KINDS),
        "words_sha256": {code: _words_sha(code) for code in sorted(PRESET_WORDS)},
    }


def test_an_agent_with_no_actions_is_sent_what_it_was_sent() -> None:
    assert today() == json.loads(FIXTURE.read_text(encoding="utf-8"))
